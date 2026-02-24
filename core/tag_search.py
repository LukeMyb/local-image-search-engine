import faiss
import torch
import pandas as pd
import numpy as np
import re
import os
from huggingface_hub import hf_hub_download
from transformers import CLIPProcessor, CLIPModel
from deep_translator import GoogleTranslator
from core.database import ImageDatabase

class TagSearch:
    def __init__(self, db_path="data/db/index.db", tag_index_path="data/tag_vector_index.bin"):
        self.db = ImageDatabase(db_path)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"  [System] 使用デバイス: {self.device}") # どちらが使われているか確認用

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

        # 4. 10万語の専門辞書 (Alias) をロード
        self.alias_map = self._load_alias_map("data/tag_aliases.csv")

    def _load_alias_map(self, path):
        """CSVを高速検索用の辞書として読み込む"""
        if os.path.exists(path):
            df = pd.read_csv(path)
            # 日本語 -> 英語タグ
            return {str(k).strip(): str(v).strip().replace(' ', '_') 
                    for k, v in zip(df['alias'], df['actual'])}
        return {}

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

    def find_similar_tags_with_score(self, word, top_k=25): 
        # 1. 日本語をCSVで変換 (Alias)
        search_key = word.strip()
        alias_hit = False
        
        if search_key in self.alias_map:
            english_word = self.alias_map[search_key]
            print(f"  ├─ [Alias適用]: {search_key} -> {english_word}")
            alias_hit = True
        else:
            # 2. 辞書にない場合のみ翻訳
            try:
                word.encode('ascii')
                english_word = word.lower()
            except:
                english_word = self.translator.translate(word).lower()
            print(f"  ├─ [翻訳適用]: {word} -> {english_word}")

        found_tags_map = {} 

        # 【高速化】辞書にヒットし、かつそのタグが有効なタグリストに存在する場合
        # 重いCLIP計算をスキップして即座に返す
        if alias_hit and english_word in self.tag_list:
            print(f"  └─ [高速検索] 辞書ヒットのためAI計算をスキップ")
            found_tags_map[english_word] = 1.0
            return english_word, found_tags_map

        # --- 以下、辞書になかった場合のみ実行される重い処理 ---
        
        # 3. ベクトル比較 (CLIP)
        query_vec = self.query_to_vector(english_word)
        distances, indices = self.tag_index.search(query_vec, top_k)
        
        # 辞書で見つけたタグ（tag_listにはないがaliasにはあった場合など）
        if english_word in self.tag_list:
            found_tags_map[english_word] = 1.0

        for i, idx in enumerate(indices[0]):
            score = float(distances[0][i])
            tag_name = self.tag_list[idx]
            if self.check_conflict(english_word, tag_name): continue
            if score > 0.90:
                found_tags_map[tag_name] = max(found_tags_map.get(tag_name, 0), score)
        
        return english_word, found_tags_map

    def check_conflict(self, query_translated, tag_name):
        q, t = query_translated.lower(), tag_name.lower()
        big = ["big", "large", "huge", "giant", "massive", "gigantic"]
        small = ["small", "flat", "tiny", "little"]
        if any(w in q for w in big) and any(w in t for w in small): return True
        if any(w in q for w in small) and any(w in t for w in big): return True
        return False

    def calculate_image_score_with_details(self, image_tags_str, search_groups):
        """スコアと「どのタグがマッチしたか」のリストを返す"""
        total_score = 0.0
        matched_details = []
        if not image_tags_str: return 0.0, []
        
        img_tags = [t.strip().lower() for t in image_tags_str.split(',')]
        
        for group_map in search_groups:
            best_match_score = 0.0
            best_tag = None
            for tag, score in group_map.items():
                norm_search_tag = tag.lower().replace('_', ' ')
                if norm_search_tag in img_tags:
                    if score > best_match_score:
                        best_match_score = score
                        best_tag = tag
            
            if best_tag:
                total_score += best_match_score
                matched_details.append((best_tag, best_match_score))
                
        return total_score, matched_details

    def search(self, user_query, limit=100):
        words = re.split(r'[ \u3000,]+', user_query)
        words = [w for w in words if w]
        if not words: return []

        print(f"\n{'='*60}")
        print(f" 検索クエリ: '{user_query}'")
        print(f"{'='*60}")
        
        search_groups = [] 
        for word in words:
            final_tag, similar_tags_map = self.find_similar_tags_with_score(word)
            search_groups.append(similar_tags_map)
            print(f"■ 単語: '{word}' -> 採用タグ候補 {len(similar_tags_map)}件\n")

        and_conditions = []
        params = []
        for group_map in search_groups:
            or_parts = [ "tags_combined LIKE ?" for _ in group_map.keys() ]
            for tag in group_map.keys():
                params.append(f"%{tag.replace('_', ' ')}%")
            if or_parts:
                and_conditions.append(f"({' OR '.join(or_parts)})")

        if not and_conditions: return []

        full_sql = f"SELECT id, file_path, tags_combined, file_mtime FROM images WHERE {' AND '.join(and_conditions)} LIMIT ?"
        params.append(limit * 5)
        
        cursor = self.db.conn.cursor()
        cursor.execute(full_sql, params)
        raw_results = [dict(row) for row in cursor.fetchall()]
        
        print(f"  -> DBヒット: {len(raw_results)}件 (詳細スコアリング中...)")

        scored_results = []
        for row in raw_results:
            score, matches = self.calculate_image_score_with_details(row['tags_combined'], search_groups)
            row['match_score'] = score
            row['matched_tags'] = matches
            scored_results.append(row)
            
        scored_results.sort(key=lambda x: (x['match_score'], x['file_mtime']), reverse=True)
        return scored_results[:limit]

if __name__ == "__main__":
    searcher = TagSearch()
    # テスト実行
    q = ""
    results = searcher.search(q, limit=5)
    
    print(f"\n【最終検索結果】")
    print("-" * 60)
    for i, row in enumerate(results):
        print(f"Rank {i+1} [Total Score: {row['match_score']:.4f}]")
        print(f"  Path: {row['file_path']}")
        
        # 採用された（マッチした）タグの内訳を表示
        match_info = ", ".join([f"{t}({s:.2f})" for t, s in row['matched_tags']])
        print(f"  Matched By: {match_info}")
        
        print(f"  Raw Tags: {row.get('tags_combined', '')[:80]}...") 
        print("-" * 60)