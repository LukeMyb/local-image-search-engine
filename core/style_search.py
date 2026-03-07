import os
import numpy as np
import faiss
import torch
import torch_directml
import torchvision.transforms as transforms
from torchvision.models import vgg16, VGG16_Weights
from PIL import Image
from core.database import ImageDatabase

class StyleSearcher:
    def __init__(self, db: ImageDatabase, index_path="data/faiss/style.index"):
        self.db = db
        self.index_path = index_path
        
        self.device = torch_directml.device()
        print(f"  [StyleSearch] 起動中 (デバイス: {self.device})")
        
        # VGG16モデルのロード
        self.model = vgg16(weights=VGG16_Weights.IMAGENET1K_V1).features.to(self.device)
        self.model.eval()
        
        self.style_layers = [3, 8, 15, 22]
        
        self.transform = transforms.Compose([
            transforms.Resize((256, 256)), 
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        # FAISSインデックスのロード
        try:
            self.index = faiss.read_index(str(self.index_path))
            print(f"  [StyleSearch] インデックスをロードしました (登録数: {self.index.ntotal}件)")
        except Exception as e:
            print(f"  [StyleSearch] 警告: 絵柄インデックスが見つかりません。先にベクトル化を実行してください。")
            self.index = None

    def extract_style_vector(self, image_path):
        """1枚の画像から画風ベクトル（AdaIN: 平均と標準偏差）を抽出する"""
        try:
            img = Image.open(image_path).convert('RGB')
            x = self.transform(img).unsqueeze(0).to(self.device)
        except Exception as e:
            print(f"読込エラー {image_path}: {e}")
            return None

        style_vectors = []
        with torch.no_grad():
            for i, layer in enumerate(self.model):
                x = layer(x)
                if i in self.style_layers:
                    mean = x.mean(dim=[2, 3]).view(-1)
                    std = x.std(dim=[2, 3]).view(-1)
                    style_vectors.append(mean.cpu().numpy())
                    style_vectors.append(std.cpu().numpy())
        
        return np.concatenate(style_vectors)

    def calculate_centroid(self, image_paths):
        """【機能1】ギャラリーで選択された複数画像のパスから重心ベクトルを計算する"""
        valid_vectors = []
        for path in image_paths:
            if not os.path.exists(path):
                print(f"警告: 参照画像が存在しません -> {path}")
                continue
            
            raw_vec = self.extract_style_vector(path)
            if raw_vec is not None:
                valid_vectors.append(raw_vec)
                
        if not valid_vectors:
            return None

        # 抽出した全ベクトルの平均（重心）を計算して返す
        mean_vec = np.mean(valid_vectors, axis=0)
        return mean_vec

    def search_by_style_name(self, style_name, top_k=200):
        """【機能2】DBに保存された絵柄名（style:xxx）から検索を実行する"""
        if self.index is None:
            print("エラー: 検索インデックスがロードされていません。")
            return []

        # DBから該当する名前のベクトル(BLOB)を復元して取得
        query_vector = self.db.get_style_vector(style_name)
        if query_vector is None:
            print(f"エラー: 絵柄タグ '{style_name}' が見つかりません。")
            return []

        # FAISS検索用にL2正規化
        faiss.normalize_L2(query_vector)
        
        # 検索の実行 (distances=スコア, indices=DB上の画像ID)
        distances, indices = self.index.search(query_vector, top_k)

        results = []
        for i in range(top_k):
            score = float(distances[0][i])
            image_id = int(indices[0][i])
            
            if image_id == -1: continue

            # DBからサムネイルパスなどの画像情報を取得
            image_data = self.db.get_image_by_id(image_id)
            if image_data:
                # 既存のタグ検索（tag_search.py）の結果フォーマットと互換性を持たせるため、
                # アプリ側でソートや表示に使う辞書のキーを追加しておく
                image_data['match_score'] = score
                image_data['matched_tags'] = [] # 絵柄検索は単語のスコア内訳がないため空リスト
                results.append(image_data)
                
        return results

# --- 単体テスト ---
if __name__ == "__main__":
    db = ImageDatabase()
    searcher = StyleSearcher(db)
    
    print("\n" + "="*50)
    print("絵柄検索エンジンの準備が整いました。")
    print("="*50)
    
    # DBに登録されている絵柄タグの一覧を表示
    styles = db.get_all_styles()
    if styles:
        print("【保存済みの絵柄タグ】")
        for s in styles:
            print(f" - {s['name']}")
    else:
        print("保存されている絵柄タグはまだありません。")
        
    db.close()