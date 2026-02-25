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
        
        # GPUが使えるなら使い、なければCPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"  [System] Device: {self.device}")

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

        # 4. 辞書ロード (10万語 + 手動修正)
        self.alias_map = self._load_all_aliases()

    def _load_all_aliases(self):
        """10万語辞書と手動辞書を統合してロード"""
        combined = {}
        # 読み込む順番: 10万語(tag_aliases) -> 手動(manual_alias)
        paths = ["data/tag_aliases.csv", "data/manual_alias.csv"]
        
        print(f"  [System] Loading dictionaries...")
        for path in paths:
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    count = 0
                    for k, v in zip(df['alias'], df['actual']):
                        # 全て小文字、スペースをアンダースコアに統一
                        key = str(k).strip().lower().replace(' ', '_')
                        val = str(v).strip().lower().replace(' ', '_')
                        combined[key] = val
                        count += 1
                    print(f"    - Loaded {count} entries from {path}")
                except Exception as e:
                    print(f"    [!] Failed to load {path}: {e}")
        return combined

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
        # 入力を正規化（小文字、スペース→アンダースコア）
        search_key = word.strip().lower().replace(' ', '_')
        
        # 1. Alias辞書チェック
        english_word = search_key
        alias_hit = False
        
        if search_key in self.alias_map:
            english_word = self.alias_map[search_key]
            print(f"  ├─ [Alias]: {search_key} -> {english_word}")
            alias_hit = True
        else:
            # 2. 翻訳 (辞書にない場合のみ)
            try:
                # 既に英単語ならそのまま
                search_key.encode('ascii')
                english_word = search_key
            except:
                english_word = self.translator.translate(word).lower()
            print(f"  ├─ [Translate]: {word} -> {english_word}")

        found_tags_map = {} 

        # 【高速化】辞書ヒット & 有効タグなら即リターン (AI計算スキップ)
        if alias_hit and english_word in self.tag_list:
            found_tags_map[english_word] = 1.0
            # 他にも部分一致するタグがあれば拾う (例: "school" -> "school_swimsuit")
            # 完全一致だけだと漏れる可能性があるため、軽いループだけ回す
            # ただし、CLIPは回さない
            return english_word, found_tags_map

        # 3. ベクトル比較 (CLIP) - 辞書になかった、またはタグリストにない場合のみ
        query_vec = self.query_to_vector(english_word)
        distances, indices = self.tag_index.search(query_vec, top_k)
        
        # 辞書で見つけた単語そのものは、確実に候補に入れる
        if english_word in self.tag_list:
            found_tags_map[english_word] = 1.0

        query_has_size = self.has_size_modifier(english_word)

        for i, idx in enumerate(indices[0]):
            score = float(distances[0][i])
            tag_name = self.tag_list[idx]
            
            if self.check_conflict(english_word, tag_name): continue
            if query_has_size and not self.has_size_modifier(tag_name): continue

            if score > 0.90:
                found_tags_map[tag_name] = max(found_tags_map.get(tag_name, 0), score)
        
        return english_word, found_tags_map

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
        return False

    def calculate_image_score_with_details(self, image_tags_str, search_groups):
        total_score = 0.0
        matched_details = []
        if not image_tags_str: return 0.0, []
        
        # タグの正規化（小文字、スペース統一）
        img_tags = [t.strip().lower().replace('_', ' ') for t in image_tags_str.split(',')]
        
        for group_map in search_groups:
            best_match_score = 0.0
            best_tag = None
            for tag, score in group_map.items():
                # 検索タグも正規化
                norm_search_tag = tag.lower().replace('_', ' ')
                
                # 完全一致だけでなく、部分一致も考慮すべきだが
                # ここでは確実性を重視して完全一致検索
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
        print(f" Query: '{user_query}'")
        print(f"{'='*60}")
        
        search_groups = [] 
        for word in words:
            final_tag, similar_tags_map = self.find_similar_tags_with_score(word)
            search_groups.append(similar_tags_map)
            print(f"  Target: '{final_tag}' -> Candidates: {len(similar_tags_map)}")

        and_conditions = []
        params = []
        for group_map in search_groups:
            or_parts = []
            for tag in group_map.keys():
                or_parts.append("tags_combined LIKE ?")
                # SQLのLIKE検索用にスペース区切りに変換
                params.append(f"%{tag.replace('_', ' ')}%")
            if or_parts:
                and_conditions.append(f"({' OR '.join(or_parts)})")

        if not and_conditions: return []

        # 件数制限を少し緩めて、スコアリング後に絞る
        full_sql = f"SELECT id, file_path, tags_combined, file_mtime FROM images WHERE {' AND '.join(and_conditions)} LIMIT ?"
        params.append(limit * 10) # 候補を多めに取ってからソート
        
        cursor = self.db.conn.cursor()
        cursor.execute(full_sql, params)
        raw_results = [dict(row) for row in cursor.fetchall()]
        
        print(f"  -> DB Hits: {len(raw_results)} (Scoring...)")

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
    # テスト: 辞書にある単語と、ない単語を混ぜる
    q = "黒髪" 
    results = searcher.search(q, limit=5)
    
    print(f"\n【Final Result】")
    print("-" * 60)
    for i, row in enumerate(results):
        print(f"Rank {i+1} [Score: {row['match_score']:.2f}]")
        print(f"  Path: {row['file_path']}")
        match_info = ", ".join([f"{t}({s:.2f})" for t, s in row['matched_tags']])
        print(f"  Matches: {match_info}")
        print("-" * 60)