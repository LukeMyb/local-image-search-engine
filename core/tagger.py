import os
import cv2
import numpy as np
import pandas as pd
import gc
from huggingface_hub import hf_hub_download
import onnxruntime as ort
from core.database import ImageDatabase

class Tagger:
    def __init__(self, db_path="data/db/index.db", 
                 conv_model_name="wd-v1-4-convnext-tagger-v2", #属性特化用（ConvNeXt等がよく使われます）
                 moat_model_name="wd-v1-4-moat-tagger-v2",     #構図特化用
                 general_threshold=0.35, 
                 character_threshold=0.75): #キャラは間違えないように閾値高め
        
        self.db = ImageDatabase(db_path)
        self.general_threshold = general_threshold
        self.character_threshold = character_threshold

        #モデル名をそれぞれ保持
        self.conv_model_name = conv_model_name
        self.moat_model_name = moat_model_name
        
        #検索ノイズになる「背景・メタ情報・レーティング・不要な属性」を除外
        self.ignore_tags = {
            # --- レーティング ---
            "explicit", "questionable", "safe", "sensitive", "general",
            "rating:explicit", "rating:questionable", "rating:safe", 
            "rating:sensitive", "rating:general",
            
            # --- メタデータ ---
            "text", "signature", "watermark", "username", "artist name", 
            "date", "translated", "copyright name", "source", "commentary request",
            
            # --- 背景 ---
            "simple background", "white background", "transparent background",
            "black background", "grey background", "gradient background",
            "pattern background", "abstract background", 
            "indoors", "outdoors",

            # ★追加：--- 不要な肌色・ノイズ属性 ---
            "blue_skin", "purple_skin", "green_skin", "red_skin", "grey_skin"
        }
        
        print("=== Taggerを初期化しました（モデルは実行時に順次読み込みます） ===")
        print(f"設定: 一般タグ>{general_threshold}, キャラタグ>{character_threshold}")

    def _load_model(self, model_name):
        print(f"  [{model_name}] をVRAMにロード中...")
        repo_id = f"SmilingWolf/{model_name}"

        #モデルのダウンロード
        model_path = hf_hub_download(repo_id, "model.onnx")
        csv_path = hf_hub_download(repo_id, "selected_tags.csv")

        self.tags_df = pd.read_csv(csv_path)
        self.tag_names = self.tags_df["name"].tolist()
        self.tag_categories = self.tags_df["category"].tolist() # 0:General, 4:Character, 9:Rating
        
        #'CPUExecutionProvider' から 'DmlExecutionProvider' (DirectML) に変更
        self.session = ort.InferenceSession(model_path, providers=['DmlExecutionProvider', 'CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name

    #VRAMを解放
    def _unload_model(self):
        self.session = None
        gc.collect()
        print("  VRAMからモデルを解放しました。")

    def preprocess_image(self, image_path):
        #日本語パス対応の読み込み
        try:
            n = np.fromfile(image_path, np.uint8)
            img = cv2.imdecode(n, cv2.IMREAD_COLOR)
        except:
            return None
        if img is None: return None
        
        #---画像を448x448にリサイズ---
        #真っ白なキャンバスを作成
        size = 448
        h, w, _ = img.shape
        max_dim = max(h, w)
        pad_img = np.zeros((max_dim, max_dim, 3), dtype=np.uint8) + 255
        
        #画像を中央に貼り付ける
        offset_w = (max_dim - w) // 2
        offset_h = (max_dim - h) // 2
        pad_img[offset_h:offset_h+h, offset_w:offset_w+w] = img
        
        #リサイズ
        img = cv2.resize(pad_img, (size, size), interpolation=cv2.INTER_CUBIC)
        img = img.astype(np.float32)
        img = np.expand_dims(img, 0)
        return img

    def process_all(self, force_update=False):
        try:
            cursor = self.db.conn.cursor()
            if force_update:
                #全件取得して上書き
                cursor.execute("SELECT id, file_path FROM images")
            else:
                #まだタグがないものだけ取得
                cursor.execute("SELECT id, file_path FROM images WHERE is_processed_tag = 0")
                
            targets = cursor.fetchall()
        except Exception as e:
            print(f"DBエラー: {e}")
            return

        total = len(targets)
        if total == 0:
            print("処理対象の画像はありません。")
            return
        
        #ConvNeXtとMOATの結果を一時保存する辞書
        conv_results = {}
        moat_results = {}

        #--- 第1パス：ConvNeXt（属性用）スキャン ---
        self._load_model(self.conv_model_name)
        print(f"=== 第1パス: ConvNeXtスキャン開始 (対象: {total} 枚) ===")
        for i, row in enumerate(targets):
            image_id = row['id']
            file_path = row['file_path']
            
            input_tensor = self.preprocess_image(file_path) #画像をAI用のデータに変換
            if input_tensor is None: continue
                
            #約9,000種類のタグ全てに対して「確率（0.0〜1.0）」を算出
            probs = self.session.run(None, {self.input_name: input_tensor})[0][0]

            # メインメモリ節約のため、スコアが0.05以上のものだけ保持
            conv_results[image_id] = {idx: float(p) for idx, p in enumerate(probs) if p > 0.05}

            if (i+1) % 10 == 0 or (i+1) == total:
                print(f"  ...[ConvNeXt] {i+1}/{total} 枚完了")

        self._unload_model() #ConvNeXtをVRAMから解放
            
        #--- 第2パス：MOAT（構図用）スキャン ---
        self._load_model(self.moat_model_name)
        print(f"=== 第2パス: MOATスキャン開始 (対象: {total} 枚) ===")
        for i, row in enumerate(targets):
            image_id = row['id']
            file_path = row['file_path']
            
            input_tensor = self.preprocess_image(file_path)
            if input_tensor is None: continue
                
            probs = self.session.run(None, {self.input_name: input_tensor})[0][0]
            moat_results[image_id] = {idx: float(p) for idx, p in enumerate(probs) if p > 0.05}
            
            if (i+1) % 10 == 0 or (i+1) == total:
                print(f"  ...[MOAT] {i+1}/{total} 枚完了")
                
        self._unload_model() #MOATをVRAMから解放

        # --- 統合とデータベース保存 ---
        print("=== スコアのMAX統合とDB保存を開始 ===")
        success_count = 0
        for i, row in enumerate(targets):
            image_id = row['id']
            c_res = conv_results.get(image_id, {})
            m_res = moat_results.get(image_id, {})
            
            if not c_res and not m_res: continue

            # 出現した全タグのインデックスをまとめる
            all_indices = set(c_res.keys()) | set(m_res.keys())

            found_tags = []
            final_scores_dict = {}

            # 両モデルの出力結果を統合してループ
            for tag_idx in all_indices:
                category = self.tag_categories[tag_idx]
                tag_name = self.tag_names[tag_idx]
                
                if tag_name in self.ignore_tags: continue #検索に必要ないタグは除外

                # 両モデルのスコアを取得（無ければ0.0）
                c_prob = c_res.get(tag_idx, 0.0)
                m_prob = m_res.get(tag_idx, 0.0)

                # 重み付けではなく、高い方のスコアをそのまま採用（MAX方式）
                combined_prob = max(c_prob, m_prob)

                # カテゴリ4（キャラ固有名詞）のみ閾値を高く設定
                threshold = self.character_threshold if category == 4 else self.general_threshold

                # 合算スコアが閾値を超えたら採用
                if combined_prob > threshold:
                    found_tags.append(tag_name)
                    # JSON保存用にアンダースコアをスペースに置換し、小数点3桁に丸める
                    clean_tag = tag_name.replace("_", " ")
                    final_scores_dict[clean_tag] = round(combined_prob, 3)
            
            #FTS5用文字列とJSONスコア辞書の両方を保存
            tags_text = ", ".join([t.replace("_", " ") for t in found_tags])
            self.db.update_tags_with_scores(image_id, tags_text, final_scores_dict)
            
            success_count += 1

            # 統合・DB保存時100枚ごとに進捗を出力
            if (i+1) % 100 == 0 or (i+1) == total:
                print(f"  ...[統合・保存] {i+1}/{total} 枚完了")

        print(f"=== 完了 (成功: {success_count} 枚) ===")
        self.db.close()

        # テスト・診断用のメソッド
    def debug_compare_models(self, test_image_path):
        print(f"\n=== スコア診断テスト開始: {test_image_path} ===")
        
        input_tensor = self.preprocess_image(test_image_path)
        if input_tensor is None:
            print("画像の読み込みに失敗しました。")
            return

        # 1. ConvNeXtでスキャン
        self._load_model(self.conv_model_name)
        conv_probs = self.session.run(None, {self.input_name: input_tensor})[0][0]
        self._unload_model()

        # 2. MOATでスキャン
        self._load_model(self.moat_model_name)
        moat_probs = self.session.run(None, {self.input_name: input_tensor})[0][0]
        self._unload_model()

        print("\n【スコア比較結果】(※どちらかが0.2以上を出したタグのみ表示)")
        print(f"{'Tag Name':<30} | {'Cat':<3} | {'ConvNeXt':<8} | {'MOAT':<8} | {'Diff':<8}")
        print("-" * 65)

        for tag_idx in range(len(self.tag_names)):
            c_prob = float(conv_probs[tag_idx])
            m_prob = float(moat_probs[tag_idx])
            
            # どちらのモデルも自信がない（0.2未満）タグはノイズなので表示を省略
            if c_prob < 0.2 and m_prob < 0.2:
                continue
                
            tag_name = self.tag_names[tag_idx]
            category = self.tag_categories[tag_idx]
            
            # 見やすいようにカテゴリを文字列化
            cat_str = "CHR" if category == 4 else ("GEN" if category == 0 else str(category))
            diff = abs(c_prob - m_prob)
            
            print(f"{tag_name[:30]:<30} | {cat_str:<3} | {c_prob:.3f}    | {m_prob:.3f}  | {diff:.3f}")

if __name__ == "__main__":
    tagger = Tagger()
    
    # テスト実行ブロック
    #TEST_IMAGE = "data/images/185APPLE/IMG_5464.JPG"
    #tagger.debug_compare_models(TEST_IMAGE)
    
    # 本番実行ブロック
    # force_update=True にすれば、前のタグを全部消して上書きします
    tagger.process_all(force_update=True)