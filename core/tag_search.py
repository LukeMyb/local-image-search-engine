import faiss
import torch
import pandas as pd
import numpy as np
import re
import os
from huggingface_hub import hf_hub_download
from transformers import CLIPProcessor, CLIPModel
import translators as ts
from core.database import ImageDatabase

class TagSearch:
    def __init__(self, db_path="data/db/index.db", tag_index_path="data/tag_vector_index.bin"):
        self.db = ImageDatabase(db_path)
        
        # GPUが使えるなら使い、なければCPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"  [System] Device: {self.device}")
        
        #モデルロード
        model_id = "openai/clip-vit-base-patch32"
        self.model = CLIPModel.from_pretrained(model_id).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_id)
        
        #タグインデックスロード
        self.tag_index = faiss.read_index(tag_index_path)
        
        #タグ名リストロード
        repo_id = "SmilingWolf/wd-v1-4-moat-tagger-v2"
        csv_path = hf_hub_download(repo_id, "selected_tags.csv")
        self.tag_list = pd.read_csv(csv_path)["name"].tolist()

        #辞書ロード (10万語 + 手動修正)
        self.alias_map = self._load_all_aliases()

        #DB内タグのオンメモリ集計 (追加)
        self._build_tag_counts()

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
    
    def _build_tag_counts(self):
        """DB内の全画像から存在するタグとその件数を集計してメモリに保持する"""
        self.tag_counts = {}
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT tags_combined FROM images")
        
        for row in cursor.fetchall():
            tags_str = row[0]
            if not tags_str: continue
            
            # コンマ区切りのタグを処理してカウント
            tags = [t.strip().lower() for t in tags_str.split(',')]
            for t in tags:
                self.tag_counts[t] = self.tag_counts.get(t, 0) + 1
                
        print(f"  [System] Cached {len(self.tag_counts)} unique tags from DB.")

    def get_suggestions(self, query_text, limit=10):
        """入力された文字列からヒットするサジェスト候補を返す"""
        if not query_text: return []
        
        prefix = query_text.lower().strip()
        candidates = []
        
        # 1. 実際のタグ（DBに存在するタグ）からの検索
        for tag, count in self.tag_counts.items():
            # アンダースコアをスペースとみなしてもマッチするようにする
            norm_tag = tag.replace('_', ' ')
            if prefix in norm_tag or prefix in tag:
                candidates.append({
                    "display": f"{tag} ({count}件)", # UI表示用
                    "query": tag,                    # クリック時に検索窓に入れる文字
                    "count": count
                })
                
        # 2. 俗語（Alias辞書）からの検索
        for alias, actual in self.alias_map.items():
            norm_alias = alias.replace('_', ' ')
            norm_actual = actual.replace('_', ' ')
            
            # aliasに入力文字が含まれていて、かつ変換先の実際のタグがDBに存在する場合のみ
            if (prefix in norm_alias or prefix in alias) and norm_actual in self.tag_counts:
                count = self.tag_counts[norm_actual]
                candidates.append({
                    "display": f"{alias} -> {actual} ({count}件)", 
                    "query": alias, 
                    "count": count
                })
                
        # 重複を消して、ヒット件数が多い順にソート
        unique_candidates = {}
        for c in candidates:
            key = c["display"]
            if key not in unique_candidates or unique_candidates[key]["count"] < c["count"]:
                unique_candidates[key] = c
                
        sorted_results = sorted(unique_candidates.values(), key=lambda x: x["count"], reverse=True)
        return sorted_results[:limit]

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

    def _check_alias_or_list(self, word):
        """
        単語がAlias辞書にあるか、あるいは直接タグリストにあるかを確認する
        戻り値: (変換後のタグ名, ヒットしたかどうか)
        """
        # 正規化
        key = word.strip().lower().replace(' ', '_')
        
        # 1. Alias辞書を最優先
        if key in self.alias_map:
            actual_tag = self.alias_map[key]
            # 変換先がタグリストに存在するか確認
            if actual_tag in self.tag_list:
                return actual_tag, True
        
        # 2. 直接タグリストにあるか確認
        if key in self.tag_list:
            return key, True
            
        return key, False

    def find_similar_tags_with_score(self, word, top_k=25): 
        log_msg = ""

        # --- Step 1: 初期入力でチェック ---
        english_word, found = self._check_alias_or_list(word) #foundはAlias辞書もしくはタグリストに検索ワードが存在するか
        if found:
            log_msg = f"[Direct/Alias Hit]: {word} -> {english_word}"
            print(f"  ├─ [Direct/Alias Hit]: {word} -> {english_word}")
            return english_word, {english_word: 1.0}, log_msg

        # --- Step 2: Google翻訳 ---
        try:
            translated_g = ts.translate_text(word, translator='google', to_language='en')
            # 翻訳結果を再度Alias辞書・リストで確認
            english_word, found = self._check_alias_or_list(translated_g)
            if found:
                log_msg = f"[Google -> Alias/List]: {word} -> {english_word}"
                print(f"  ├─ [Google -> Alias/List]: {word} -> {english_word}")
                return english_word, {english_word: 1.0}, log_msg
        except Exception as e:
            print(f"  [!] Google Translate Error: {e}")

        # --- Step 3: Bing翻訳 ---
        translated_b = ""
        try:
            translated_b = ts.translate_text(word, translator='bing', to_language='en')
            #まずは辞書・リストにあるか確認
            english_word, found = self._check_alias_or_list(translated_b)
            if found:
                log_msg = f"[Bing -> Alias/List]: {word} -> {english_word}"
                print(f"  ├─ [Bing -> Alias/List]: {word} -> {english_word}")
                return english_word, {english_word: 1.0}, log_msg
        except Exception as e:
            print(f"  [!] Bing Translate Error: {e}")

        # --- Step 4: CLIPベクトル検索 (最終手段) ---
        #Bing翻訳の結果があればそれを使用し、なければGoogle翻訳や元の単語をフォールバックにする
        final_query = translated_b if translated_b else (translated_g if 'translated_g' in locals() else word)
        log_msg = f"[Vector Search]: {word} -> '{final_query}'"
        print(f"  ├─ [Vector Search]: Using query '{final_query}'")

        found_tags_map = {} 

        # ベクトル比較 (CLIP)
        query_vec = self.query_to_vector(final_query)
        distances, indices = self.tag_index.search(query_vec, top_k)
        
        #クエリ自体がもしタグリストにあるなら、スコア1.0で追加
        norm_final = final_query.lower().replace(' ', '_')
        if norm_final in self.tag_list:
            found_tags_map[norm_final] = 1.0

        query_has_size = self.has_size_modifier(final_query)

        for i, idx in enumerate(indices[0]):
            score = float(distances[0][i])
            tag_name = self.tag_list[idx]
            
            if self.check_conflict(english_word, tag_name): continue
            if query_has_size and not self.has_size_modifier(tag_name): continue

            if score > 0.90:
                found_tags_map[tag_name] = max(found_tags_map.get(tag_name, 0), score)
        
        return final_query, found_tags_map, log_msg

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
        if not words: return [], ""

        print(f"\n{'='*60}")
        print(f" Query: '{user_query}'")
        print(f"{'='*60}")
        
        search_groups = [] 
        conversion_logs = []

        for word in words:
            final_tag, similar_tags_map, log_msg = self.find_similar_tags_with_score(word)
            conversion_logs.append(log_msg)

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

        if not and_conditions: return [], ""

        # 件数制限を少し緩めて、スコアリング後に絞る
        full_sql = f"SELECT id, file_path, tags_combined, file_mtime, thumbnail_path FROM images WHERE {' AND '.join(and_conditions)} LIMIT ?"
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

        #複数単語のログを文字列として結合し、検索結果と一緒に返す
        final_log = " | ".join(conversion_logs)
        return scored_results[:limit], final_log

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