import os
import time
import numpy as np
import faiss
from pathlib import Path
from PIL import Image
import torch
import torch_directml
import torchvision.transforms as transforms
from torchvision.models import vgg16, VGG16_Weights
from core.database import ImageDatabase

class StyleVectorizer:
    def __init__(self, db: ImageDatabase, index_path="data/faiss/style.index"):
        self.db = db
        self.index_path = index_path
        
        # DirectMLを使用してGPUを強制割り当て
        self.device = torch_directml.device()
        print(f"=== 起動中 (デバイス: {self.device}) ===")
        
        print("VGG16モデルをロード中...")
        self.model = vgg16(weights=VGG16_Weights.IMAGENET1K_V1).features.to(self.device)
        self.model.eval() 
        
        # グラム行列の代わりにAdaIN(平均・標準偏差)を抽出する層
        self.style_layers = [3, 8, 15, 22]
        
        # 画像の前処理ルール
        self.transform = transforms.Compose([
            transforms.Resize((256, 256)), 
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        self._load_or_create_index()

    def _load_or_create_index(self):
        # 既存のインデックスがあれば読み込み、なければ新規作成
        if os.path.exists(self.index_path):
            print(f"既存の絵柄検索インデックスを読み込みます: {self.index_path}")
            self.index = faiss.read_index(self.index_path)
        else:
            print("新規に絵柄検索インデックスを作成します。")
            # AdaINで4層から平均・標準偏差を抽出した場合の合計次元数は「1920」
            dimension = 1920 
            # データベースのID(整数の連番)とFAISSを直接リンクさせるためのIDMapを使用
            base_index = faiss.IndexFlatIP(dimension)
            self.index = faiss.IndexIDMap(base_index)

    def process_all(self, batch_size=32):
        # DBから絵柄ベクトル化がまだ終わっていない画像を取得
        unprocessed_rows = self.db.get_unprocessed_images('is_processed_vector')
        total_count = len(unprocessed_rows)
        
        if total_count == 0:
            print("全ての画像の絵柄ベクトル化は完了しています。")
            return

        print(f"絵柄ベクトル化処理を開始します(対象: {total_count}枚, バッチサイズ: {batch_size})...")

        batch_tensors = []
        batch_ids = []
        
        start_time = time.time()
        processed_count = 0

        for i, row in enumerate(unprocessed_rows):
            image_id = row['id']
            file_path = row['file_path']
            
            try:
                # 画像を開いてテンソル化
                img = Image.open(file_path).convert('RGB')
                tensor = self.transform(img)
                batch_tensors.append(tensor)
                batch_ids.append(image_id)
            except Exception as e:
                print(f"警告: 画像を読み込めませんでした ({file_path}): {e}")
                # 読み込めなくても「処理済み」にしてスキップ（無限ループ防止）
                self.db.update_vector_status(image_id)
                continue

            # バッチサイズ分溜まったら、まとめてAIに流し込む（GPU効率化）
            if len(batch_tensors) >= batch_size or (i == total_count - 1):
                if not batch_tensors:
                    continue
                
                # リストを結合してGPUへ転送：形状は (Batch, 3, 256, 256)
                x = torch.stack(batch_tensors).to(self.device)
                
                style_vectors = []
                with torch.no_grad():
                    for idx, layer in enumerate(self.model):
                        x = layer(x)
                        if idx in self.style_layers:
                            # 各バッチ・各チャンネルごとの平均と標準偏差を計算
                            mean = x.mean(dim=[2, 3]) # 形状: (Batch, Channels)
                            std = x.std(dim=[2, 3])   # 形状: (Batch, Channels)
                            style_vectors.append(mean.cpu().numpy())
                            style_vectors.append(std.cpu().numpy())
                
                # 横方向（特徴量の次元方向）に全層のデータを結合 -> 形状: (Batch, 1920)
                embeddings = np.concatenate(style_vectors, axis=1).astype(np.float32)
                
                # FAISSの検索精度を上げるためにL2正規化
                faiss.normalize_L2(embeddings)
                
                # DBのIDをint64型のNumPy配列にして、ベクトルと一緒にFAISSへ登録
                ids_array = np.array(batch_ids, dtype=np.int64)
                self.index.add_with_ids(embeddings, ids_array)
                
                # dbのフラグを「完了」に更新
                for pid in batch_ids:
                    self.db.update_vector_status(pid)
                
                processed_count += len(batch_tensors)
                
                # メモリ解放
                batch_tensors = []
                batch_ids = []
                
                # 進捗表示
                elapsed = time.time() - start_time
                speed = processed_count / elapsed
                print(f"  ...{processed_count}/{total_count}枚 完了(速度: {speed:.1f}枚/秒)")

        print("絵柄ベクトル化処理が完了しました")

        # インデックスをファイルに保存
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        faiss.write_index(self.index, str(self.index_path))
        print(f"インデックスを保存しました: {self.index_path}")

if __name__ == "__main__":
    print("=== 絵柄ベクトル生成プロセスを開始します ===")
    
    # データベース接続
    db = ImageDatabase()
    
    # ベクタライザー起動
    vectorizer = StyleVectorizer(db)
    
    # 処理実行 (RTX 50シリーズならバッチサイズ32〜64で高速に回ります)
    vectorizer.process_all(batch_size=32)
    
    db.close()
    print("=== 全プロセス完了 ===")