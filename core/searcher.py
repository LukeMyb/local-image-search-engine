import faiss
import numpy as np
from sentence_transformers import SentenceTransformer, models
import torch
from transformers import CLIPProcessor, CLIPModel
from core.database import ImageDatabase

class ImageSearcher:
    def __init__(self, db: ImageDatabase, model_name="laion/CLIP-ViT-L-14-laion2B-s32B-b82K", index_path="data/faiss/search.index"):
        self.db = db
        self.index_path = index_path
        
        print("検索エンジンを起動中...")
        #検索は軽量なのでCPU固定
        self.model = CLIPModel.from_pretrained(model_name)
        self.processor = CLIPProcessor.from_pretrained(model_name)
        self.model.to("cpu")
        
        #保存したインデックスファイルを読み込む
        try:
            self.index = faiss.read_index(self.index_path)
            print(f"検索インデックスをロードしました(登録数: {self.index.ntotal}件)")
        except Exception as e:
            print(f"エラー: インデックスを読み込めませんでした。先にvectorizerを実行してください。\n{e}")
            exit()

    def search(self, query_text, top_k=5):
        #テキストで画像を検索し, 結果のリストを返す
        inputs = self.processor(text=[query_text], return_tensors="pt", padding=True)
        with torch.no_grad(): #学習モードをオフに
            text_features = self.model.get_text_features(**inputs) #テキストの特徴(ベクトル)を直接抽出

        if not torch.is_tensor(text_features): #データの整形
            text_features = text_features[0] if isinstance(text_features, (list, tuple)) else text_features.pooler_output
        
        query_vector = text_features.detach().cpu().numpy() #PyTorch(GPU上のデータ)から, FAISSが扱えるNumPy(CPU上の普通の配列)に変換
        faiss.normalize_L2(query_vector) #正規化
        
        distances, indices = self.index.search(query_vector, top_k) #スコア(distance)とベクトルの類似度順の整理番号(ibduces)
        
        results = []
        for i in range(top_k):
            #ランキングi番目の「スコア」と「FAISS上のID」
            score = distances[0][i]
            faiss_id = indices[0][i]
            
            if faiss_id == -1: continue #空の場合スキップ

            #FAISSの0番目 = dbのID1番目という前提でデータを取得
            image_data = self.db.get_image_by_id(int(faiss_id) + 1)
            
            if image_data: #格納
                print(f"DEBUG: FAISSが見つけた整理番号={faiss_id}, 取得を試みるDB_ID={int(faiss_id) + 1}")
                results.append({
                    "id": image_data["id"],
                    "path": image_data["file_path"],
                    "score": float(score),
                    "thumbnail": image_data["thumbnail_path"]
                })
        
        return results

# --- テスト用メイン処理 ---
if __name__ == "__main__":
    db = ImageDatabase()
    searcher = ImageSearcher(db)
    
    print("\n画像検索の準備ができました。")
    while True:
        print("\n" + "-"*40)
        query = input("検索したい言葉を入力してください (終了: q): ")
        if query.lower() == 'q':
            break
            
        print(f"「{query}」を解析中...")
        results = searcher.search(query, top_k=3) # 上位3件を表示
        
        print("\n【検索結果】")
        if not results:
            print("該当する画像が見つかりませんでした。")
        else:
            for res in results:
                # スコアは1.0に近いほど似ているという意味
                print(f"[スコア: {res['score']:.4f}] {res['path']}")
    
    db.close()