import faiss
import torch
import pandas as pd
import numpy as np
import re
from huggingface_hub import hf_hub_download
from transformers import CLIPProcessor, CLIPModel
from deep_translator import GoogleTranslator
from core.database import ImageDatabase

class TagSearch:
    def __init__(self, db_path="data/db/index.db", tag_index_path="data/tag_vector_index.bin"):
        self.db = ImageDatabase(db_path)
        self.device = "cpu"
        self.translator = GoogleTranslator(source='ja', target='en')
        
        # 1. モデルロード
        model_id = "openai/clip-vit-base-patch32"
        self.model = CLIPModel.from_pretrained(model_id).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_id)
        
        # 2. タグインデックスロード
        self.tag_index = faiss.read_index(tag_index_path)
        
        # 3. タグ名リストロード
        repo_id = "SmilingWolf/wd-v1-4-moat-tagger-v2"
        csv_path = hf_hub_download(repo_id, "selected_tags.csv")
        self.tag_list = pd.read_csv(csv_path)["name"].tolist()

    def query_to_vector(self, text):
        inputs = self.processor(text=[text], return_tensors="pt", padding=True).to(self.device)
        with torch.no_grad():
            output = self.model.get_text_features(**inputs)
        
        if isinstance(output, torch.Tensor):
            vec = output
        elif hasattr(output, "text_embeds"):
            vec = output.text_embeds
        elif hasattr(output, "pooler_output"):
            vec = output.pooler_output
        else:
            raise ValueError(f"Unknown output type: {type(output)}")

        vec = vec / vec.norm(p=2, dim=-1, keepdim=True)
        return vec.cpu().numpy().astype('float32')

    def get_size_modifiers(self):
        return ["small", "flat", "tiny", "little", "mini", "short", "low",
                "big", "large", "huge", "giant", "massive", "gigantic", "enormous", 
                "long", "tall", "high", "hyper", "absurd"]

    def has_size_modifier(self, text):
        modifiers = self.get_size_modifiers()
        return any(m in text.lower() for m in modifiers)

    def check_conflict(self, query_translated, tag_name):
        q, t = query_translated.lower(), tag_name.lower()
        big = ["big", "large", "huge", "giant", "massive", "gigantic"]
        small = ["small", "flat", "tiny", "little"]
        if any(w in q for w in big) and any(w in t for w in small): return True
        if any(w in q for w in small) and any(w in t for w in big): return True
        if "long" in q and "short" in t: return True
        if "short" in q and "long" in t: return True
        return False

    def find_similar_tags_with_score(self, word, top_k=25): 
        try:
            word.encode('ascii')
            translated = word.lower()
        except:
            translated = self.translator.translate(word).lower()
        
        found_tags_map = {} 
        query_vec = self.query_to_vector(translated)
        distances, indices = self.tag_index.search(query_vec, top_k)
        query_has_size = self.has_size_modifier(translated)

        for i, idx in enumerate(indices[0]):
            score = float(distances[0][i])
            tag_name = self.tag_list[idx]
            
            # 矛盾チェック
            if self.check_conflict(translated, tag_name): continue
            
            # サイズ指定時の具体性チェック
            if query_has_size and not self.has_size_modifier(tag_name): continue

            # 純粋にCLIPのスコアのみで判定 (リテラル・ブーストは削除)
            if score > 0.90:
                found_tags_map[tag_name] = max(found_tags_map.get(tag_name, 0), score)
        
        return translated, found_tags_map

    def calculate_image_score(self, image_tags_str, search_groups):
        total_score = 0.0
        if not image_tags_str: return 0.0
        img_tags = [t.strip().lower() for t in image_tags_str.split(',')]
        
        for group_map in search_groups:
            best_match_score = 0.0
            for tag, score in group_map.items():
                # WD14のアンダースコアをスペースにしてDBと突合
                norm_search_tag = tag.lower().replace('_', ' ')
                if norm_search_tag in img_tags:
                    best_match_score = max(best_match_score, score)
            total_score += best_match_score
        return total_score

    def search(self, user_query, limit=100):
        words = re.split(r'[ \u3000,]+', user_query)
        words = [w for w in words if w]
        if not words: return []

        print(f"\n{'='*60}")
        print(f" 検索クエリ: '{user_query}'")
        print(f"{'='*60}")
        
        search_groups = [] 

        for word in words:
            translated, similar_tags_map = self.find_similar_tags_with_score(word)
            search_groups.append(similar_tags_map)
            
            print(f"■ 単語: '{word}'")
            print(f"  └─ 翻訳結果: {translated}")
            print(f"  ▼ 採用タグ (上位5件/スコア順):")
            
            sorted_candidates = sorted(similar_tags_map.items(), key=lambda x: x[1], reverse=True)
            for tag, score in sorted_candidates[:5]:
                print(f"      - {tag:<25} (重み: {score:.4f})")
            print("")

        # SQL構築 (スペース区切りに統一)
        and_conditions = []
        params = []
        for group_map in search_groups:
            or_parts = []
            for tag in group_map.keys():
                or_parts.append("tags_combined LIKE ?")
                params.append(f"%{tag.replace('_', ' ')}%")
            if or_parts:
                and_conditions.append(f"({' OR '.join(or_parts)})")

        if not and_conditions: return []

        full_sql = f"""
            SELECT id, file_path, tags_combined, file_mtime
            FROM images WHERE { ' AND '.join(and_conditions) }
            LIMIT ?
        """
        params.append(limit * 5)
        
        cursor = self.db.conn.cursor()
        cursor.execute(full_sql, params)
        raw_results = [dict(row) for row in cursor.fetchall()]
        
        print(f"  -> DBヒット: {len(raw_results)}件 (スコアリング中...)")

        scored_results = []
        for row in raw_results:
            row['match_score'] = self.calculate_image_score(row['tags_combined'], search_groups)
            scored_results.append(row)
            
        scored_results.sort(key=lambda x: (x['match_score'], x['file_mtime']), reverse=True)
        return scored_results[:limit]

if __name__ == "__main__":
    searcher = TagSearch()
    q = "" 
    results = searcher.search(q, limit=5)
    
    print(f"\n【最終検索結果】")
    print("-" * 60)
    for i, row in enumerate(results):
        print(f"Rank {i+1} [Score: {row['match_score']:.4f}]")
        print(f"  Path: {row['file_path']}")
        print(f"  Tags: {row.get('tags_combined', '')[:80]}...") 
        print("-" * 60)