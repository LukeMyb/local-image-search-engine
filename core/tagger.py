import os
import cv2
import numpy as np
import pandas as pd
from huggingface_hub import hf_hub_download
import onnxruntime as ort
from core.database import ImageDatabase

class Tagger:
    def __init__(self, db_path="data/db/index.db", 
                 model_name="wd-v1-4-moat-tagger-v2", #精度が良いと噂のMoat
                 general_threshold=0.35, 
                 character_threshold=0.75): #キャラは間違えないように閾値高め
        
        self.db = ImageDatabase(db_path)
        self.general_threshold = general_threshold
        self.character_threshold = character_threshold
        self.model_name = model_name
        
        #検索ノイズになる「背景・メタ情報・レーティング」を除外
        self.ignore_tags = {
            # --- レーティング ---
            "explicit", "questionable", "safe", "sensitive", "general",
            "rating:explicit", "rating:questionable", "rating:safe", 
            "rating:sensitive", "rating:general",
            
            # --- 検閲・品質 ---
            "censored", "uncensored", "mosaic censoring", "bar censor", "blur",
            
            # --- メタデータ ---
            "text", "signature", "watermark", "username", "artist name", 
            "date", "translated", "copyright name", "source", "commentary request",
            
            # --- 背景 ---
            "simple background", "white background", "transparent background",
            "black background", "grey background", "gradient background",
            "pattern background", "abstract background", 
            "indoors", "outdoors"
        }
        
        print(f"=== Taggerモデル ({model_name}) を起動します ===")
        self._load_model()
        print(f"設定: 一般タグ>{general_threshold}, キャラタグ>{character_threshold}")

    def _load_model(self):
        repo_id = f"SmilingWolf/{self.model_name}"
        #Moatモデルのダウンロード
        model_path = hf_hub_download(repo_id, "model.onnx")
        csv_path = hf_hub_download(repo_id, "selected_tags.csv")

        self.tags_df = pd.read_csv(csv_path)
        self.tag_names = self.tags_df["name"].tolist()
        self.tag_categories = self.tags_df["category"].tolist() # 0:General, 4:Character, 9:Rating
        
        #'CPUExecutionProvider' から 'DmlExecutionProvider' (DirectML) に変更
        self.session = ort.InferenceSession(model_path, providers=['DmlExecutionProvider', 'CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name

    def preprocess_image(self, image_path):
        #日本語パス対応の読み込み
        try:
            n = np.fromfile(image_path, np.uint8)
            img = cv2.imdecode(n, cv2.IMREAD_COLOR)
        except:
            return None
        if img is None: return None
            
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) #色の順番をBGRからRGBに入れ替え
        
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

        print(f"=== スキャン開始 (対象: {total} 枚) ===")
        
        success_count = 0
        for i, row in enumerate(targets):
            image_id = row['id']
            file_path = row['file_path']
            
            input_tensor = self.preprocess_image(file_path) #画像をAI用のデータに変換
            if input_tensor is None: continue
                
            #約9,000種類のタグ全てに対して「確率（0.0〜1.0）」を算出
            probs = self.session.run(None, {self.input_name: input_tensor})[0][0]
            
            found_tags = []
            for tag_idx, prob in enumerate(probs):
                category = self.tag_categories[tag_idx]
                tag_name = self.tag_names[tag_idx]
                
                if tag_name in self.ignore_tags: continue #検索に必要ないタグは除外

                #カテゴリ別閾値判定
                if category == 4: #Character
                    if prob > self.character_threshold:
                        found_tags.append(tag_name)
                else: #General
                    if prob > self.general_threshold:
                        found_tags.append(tag_name)
            
            #保存
            tags_text = ", ".join([t.replace("_", " ") for t in found_tags])
            self.db.update_tags(image_id, tags_text)
            
            success_count += 1
            if (i+1) % 10 == 0 or (i+1) == total:
                print(f"  ...{i+1}/{total} 枚完了")

        print("=== 完了 ===")
        self.db.close()

if __name__ == "__main__":
    # force_update=True にすれば、前のConvNextのタグを全部消してMoatで上書きします
    tagger = Tagger()
    tagger.process_all(force_update=True)