import os
import time
import numpy as np
import faiss
from pathlib import Path
from PIL import Image
from sentence_transformers import SentenceTransformer, models
import torch
from transformers import CLIPProcessor, CLIPModel
from core.database import ImageDatabase

class VectorIndexer:
    def __init__(self, db: ImageDatabase, model_name="laion/CLIP-ViT-L-14-laion2B-s32B-b82K", index_path="data/faiss/search.index"):
        self.db = db
        self.index_path = index_path
        
        #AIモデルの読み込み
        #CPUを使用(RTX 50シリーズは対応してなかったT_T)
        print(f"AIモデル ({model_name}) をロード中...")
        self.model = CLIPModel.from_pretrained(model_name)
        self.processor = CLIPProcessor.from_pretrained(model_name)
        self.device = "cpu"
        self.model.to(self.device)
        print("モデルロード完了")

        self._load_or_create_index() #FAISSインデックス(検索エンジン)の準備

    def _load_or_create_index(self):
        #既存のインデックスがあれば読み込み, なければ新規作成
        if os.path.exists(self.index_path):
            print(f"既存の検索インデックスを読み込みます: {self.index_path}")
            self.index = faiss.read_index(self.index_path)
        else:
            print("新規検索インデックスを作成します。")
            #CLIPの出力次元数(ViT-B-32は512次元)に合わせて作成
            dimension = 768
            self.index = faiss.IndexFlatIP(dimension)  #内積(コサイン類似度)で検索

    def process_all(self, batch_size=32): #バッチはまとめて一気に処理するその束の数
        #未処理の画像をバッチごとにベクトル化し, FAISSに追加・保存
        #処理対象(ベクトル化がまだ終わっていない画像)を取得
        unprocessed_rows = self.db.get_unprocessed_images('is_processed_vector')
        total_count = len(unprocessed_rows)
        
        if total_count == 0:
            print("全ての画像のベクトル化は完了しています")
            return

        print(f"ベクトル化処理を開始します(対象: {total_count}枚, バッチサイズ: {batch_size})...")

        #バッチ処理用の一時リスト
        batch_images = []
        batch_ids = []
        
        start_time = time.time()
        processed_count = 0

        for i, row in enumerate(unprocessed_rows):
            image_id = row['id']
            file_path = row['file_path']
            
            try:
                #画像を開いてリストに追加
                img = Image.open(file_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                batch_images.append(img)
                batch_ids.append(image_id)
                
            except Exception as e:
                print(f"警告: 画像を読み込めませんでした ({file_path}): {e}")
                #読み込めなくても「処理済み」にしてスキップしないと無限ループになるため, ここでは暫定的にスキップ扱い
                continue

            #バッチサイズだけ溜まったら, まとめてAIに流し込む
            if len(batch_images) >= batch_size or (i == total_count - 1): #(i == total_count - 1)は最後の画像かどうか
                if not batch_images:
                    continue
                
                #AI処理のコア部分
                inputs = self.processor(images=batch_images, return_tensors="pt", padding=True)
                with torch.no_grad():
                    # 画像の特徴（ベクトル）を直接抽出
                    image_features = self.model.get_image_features(**inputs)

                if not torch.is_tensor(image_features):
                    # 戻り値がオブジェクトの場合、最初の要素（またはpooler_output）を取得
                    image_features = image_features[0] if isinstance(image_features, (list, tuple)) else image_features.pooler_output
                
                embeddings = image_features.detach().cpu().numpy()
                faiss.normalize_L2(embeddings)
                self.index.add(embeddings)
                
                #dbのフラグを「完了」に更新
                for pid in batch_ids:
                    self.db.update_vector_status(pid)
                
                processed_count += len(batch_images)
                
                #メモリ解放
                batch_images = []
                batch_ids = []
                
                #進捗表示
                elapsed = time.time() - start_time
                speed = processed_count / elapsed
                print(f"  ...{processed_count}/{total_count}枚 完了(速度: {speed:.1f}枚/秒)")

        print("ベクトル化処理が完了しました")

        # --- ここを追加：インデックスをファイルに保存 ---
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        faiss.write_index(self.index, self.index_path)
        print(f"インデックスを保存しました: {self.index_path}")

# --- 単体テスト ---
if __name__ == "__main__":
    print("=== ベクトル生成プロセスを開始します ===")
    
    # データベース接続
    db = ImageDatabase()
    
    # ベクタライザー起動
    vectorizer = VectorIndexer(db)
    
    # 処理実行
    vectorizer.process_all(batch_size=32)
    
    db.close()
    print("=== 全プロセス完了 ===")