import pandas as pd
import numpy as np
import faiss
import torch
from huggingface_hub import hf_hub_download
from transformers import CLIPProcessor, CLIPModel

class TagVectorizer:
    def __init__(self, index_path="data/tag_vector_index.bin", model_name="wd-v1-4-moat-tagger-v2"):
        self.index_path = index_path
        self.device = "cpu" # タグ数千個ならCPUで十分高速
        
        print("=== モデルとタグリストをロード中 ===")
        # CLIPモデル
        model_id = "openai/clip-vit-base-patch32"
        self.model = CLIPModel.from_pretrained(model_id).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_id)
        
        # WD14のタグリスト取得
        repo_id = f"SmilingWolf/{model_name}"
        csv_path = hf_hub_download(repo_id, "selected_tags.csv")
        df = pd.read_csv(csv_path)
        
        # タグ名を取得（アンダースコアはスペースに置換してベクトル化しやすくする）
        self.tags = df["name"].tolist()
        self.clean_tags = [t.replace("_", " ") for t in self.tags]
        
        print(f"タグ数: {len(self.tags)} 個")

    def create_index(self):
        print("タグのベクトル化を開始します...")
        
        # バッチ処理で高速化
        batch_size = 100
        all_vectors = []
        
        for i in range(0, len(self.clean_tags), batch_size):
            batch_texts = self.clean_tags[i : i + batch_size]
            
            inputs = self.processor(text=batch_texts, return_tensors="pt", padding=True).to(self.device)
            with torch.no_grad():
                output = self.model.get_text_features(**inputs)
            
            # 【修正】出力がTensorでない場合の安全対策
            if isinstance(output, torch.Tensor):
                text_features = output
            else:
                # オブジェクトなら、ベクトルが入っている場所を探して取り出す
                if hasattr(output, "text_embeds"):
                    text_features = output.text_embeds
                elif hasattr(output, "pooler_output"):
                    text_features = output.pooler_output
                else:
                    # 万が一どれもなければスキップ（通常ここには来ない）
                    print(f"Warning: 不明な出力形式です ({type(output)})")
                    continue

            # 正規化
            text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
            all_vectors.append(text_features.cpu().numpy())
            
        # 結合
        vectors = np.concatenate(all_vectors).astype('float32')
        
        # FAISSインデックス作成 (内積＝コサイン類似度)
        dimension = vectors.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(vectors)
        
        faiss.write_index(index, self.index_path)
        print(f"インデックスを保存しました: {self.index_path}")
        
        return self.tags

if __name__ == "__main__":
    tv = TagVectorizer()
    tv.create_index()