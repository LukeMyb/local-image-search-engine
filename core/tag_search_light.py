import pandas as pd
import re
import os
import json
import math
import time

from core.database import ImageDatabase

class TagSearchLight:
    def __init__(self, db_path="data/db/index.db"):
        self.db = ImageDatabase(db_path)
        
        # 辞書ロード (10万語 + 手動修正)
        self.alias_map = self._load_all_aliases()

        # DB内タグのオンメモリ集計
        self._build_tag_counts()

    def _load_all_aliases(self):
        """10万語辞書と手動辞書を統合してロード"""
        combined = {}
        paths = ["data/tag_aliases.csv", "data/manual_alias.csv"]
        
        print(f"  [System] Loading dictionaries (Light Mode)...")
        for path in paths:
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    count = 0
                    for k, v in zip(df['alias'], df['actual']):
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

        rows = cursor.fetchall()
        self.total_images = len(rows)
        
        for row in rows:
            tags_str = row[0]
            if not tags_str: continue
            
            tags = [t.strip().lower() for t in tags_str.split(',')]
            for t in tags:
                self.tag_counts[t] = self.tag_counts.get(t, 0) + 1
                
        print(f"  [System] Cached {len(self.tag_counts)} unique tags from DB.")

    def get_suggestions(self, query_text, limit=10):
        if not query_text: return []

        normalized_query = query_text.replace('　', ' ')
        parts = normalized_query.split(' ')
        current_word = parts[-1]
        
        if not current_word:
            return []

        base_query = " ".join(parts[:-1]) + " " if len(parts) > 1 else ""
        
        prefix = current_word.lower().strip()
        prefix_under = prefix.replace(' ', '_')

        candidates = []
        
        for tag, count in self.tag_counts.items():
            underscored_tag = tag.replace(' ', '_')
            if prefix in tag or prefix_under in underscored_tag:
                candidates.append({
                    "display": f"{underscored_tag} ({count}件)",
                    "query": base_query + underscored_tag,
                    "count": count
                })
                
        for alias, actual in self.alias_map.items():
            norm_actual = actual.replace('_', ' ')
            if (prefix_under in alias) and norm_actual in self.tag_counts:
                count = self.tag_counts[norm_actual]
                candidates.append({
                    "display": f"{alias} -> {actual} ({count}件)", 
                    "query": base_query + alias, 
                    "count": count
                })
                
        unique_candidates = {}
        for c in candidates:
            key = c["display"]
            if key not in unique_candidates or unique_candidates[key]["count"] < c["count"]:
                unique_candidates[key] = c
                
        sorted_results = sorted(unique_candidates.values(), key=lambda x: x["count"], reverse=True)
        return sorted_results[:limit]

    def _check_alias_or_list(self, word):
        key = word.strip().lower().replace(' ', '_')
        
        if key in self.alias_map:
            actual_tag = self.alias_map[key]
            if actual_tag.replace('_', ' ') in self.tag_counts or actual_tag in self.tag_counts:
                return actual_tag, True
        
        if key.replace('_', ' ') in self.tag_counts or key in self.tag_counts:
            return key, True
            
        return key, False

    def find_similar_tags_with_score(self, word): 
        english_word, found = self._check_alias_or_list(word)
        if found:
            print(f"  ├─ [Direct/Alias Hit]: {word} -> {english_word}")
            return english_word, {english_word: 1.0}
        
        cached_en = self.db.get_cached_translation(word)
        if cached_en:
            print(f"  ├─ [Cache Hit]: {word} -> {cached_en}")
            english_word, found = self._check_alias_or_list(cached_en)
            if found:
                return english_word, {english_word: 1.0}
            else:
                return cached_en, {cached_en: 1.0}
        
        print(f"  ├─ [Not Found]: '{word}' (Used as is in light mode)")
        return word, {word: 1.0}

    def calculate_image_score_with_details(self, image_tags_str, search_groups, parsed_tag_scores):
        total_score = 0.0
        matched_details = []
        if not image_tags_str: return 0.0, []
        
        img_tags = {t.strip().lower().replace('_', ' ') for t in image_tags_str.split(',')}

        for group_map in search_groups:
            group_max_score = 0.0
            best_match_detail = None
        
            for search_tag, sim_score in group_map.items():
                norm_search_tag = search_tag.lower().replace('_', ' ')
                if norm_search_tag in img_tags:
                    sim_weight = sim_score ** 5
                    
                    ai_conf = parsed_tag_scores.get(norm_search_tag, 0.35)
                    ai_weight = math.sqrt(ai_conf)
                    
                    db_count = self.tag_counts.get(norm_search_tag, 0)
                    total_imgs = max(self.total_images, 1)
                    idf_weight = math.log10(total_imgs / max(db_count, 10))
                    
                    final_word_score = sim_weight * ai_weight * idf_weight

                    if final_word_score > group_max_score:
                        group_max_score = final_word_score
                        best_match_detail = {
                            "tag": norm_search_tag,
                            "final": final_word_score,
                            "sim": sim_weight,
                            "ai": ai_weight,
                            "idf": idf_weight
                        }

            if best_match_detail:
                total_score += group_max_score
                matched_details.append(best_match_detail)
                
        return total_score, matched_details

    def search(self, user_query, is_bookmarked=False):
        query = re.sub(r'\s*\|\s*', '|', user_query)

        words = re.split(r'[ \u3000,]+', query)
        words = [w for w in words if w]
        if not words: return []

        positive_groups = []
        negative_words = []
        for w in words:
            if w.startswith('-') and len(w) > 1:
                negative_words.append(w[1:])
            else:
                parts = w.split('|')
                positive_groups.append(parts)

        if not positive_groups:
            return []

        print(f"\n{'='*60}")
        print(f" Query: '{user_query}'")
        print(f"{'='*60}")
        
        search_groups = [] 

        for or_words in positive_groups:
            combined_similar_tags_map = {}
            print(f"  [OR Group] Processing: {or_words}")

            for word in or_words:
                final_tag, similar_tags_map = self.find_similar_tags_with_score(word)

                print(f"  Target: '{final_tag}' -> Candidates: {len(similar_tags_map)}")

                for t, s in similar_tags_map.items():
                    if t not in combined_similar_tags_map or s > combined_similar_tags_map.get(t, 0):
                        combined_similar_tags_map[t] = s

            search_groups.append(combined_similar_tags_map)

        match_groups = []

        fast_lookup = {}
        for group_map in search_groups:
            for tag, score in group_map.items():
                norm_tag = tag.lower().replace('_', ' ')
                if norm_tag not in fast_lookup or score > fast_lookup.get(norm_tag, 0):
                    fast_lookup[norm_tag] = score

        for group_map in search_groups:
            or_parts = []
            for tag in group_map.keys():
                norm_tag = tag.replace('_', ' ')
                or_parts.append(f'"{norm_tag}"')
            if or_parts:
                match_groups.append(f"({' OR '.join(or_parts)})")

        if not match_groups: return []

        match_query = " AND ".join(match_groups)

        if negative_words:
            negative_tags = set()
            print(f"  [Negative Search] Processing exclusions...")
            for word in negative_words:
                _, similar_tags_map = self.find_similar_tags_with_score(word)
                for tag in similar_tags_map.keys():
                    norm_tag = tag.replace('_', ' ')

                    if norm_tag not in fast_lookup:
                        negative_tags.add(f'"{norm_tag}"')
            
            if negative_tags:
                not_string = " NOT ".join(list(negative_tags))
                match_query = f"{match_query} NOT {not_string}"
                print(f"  -> Added {len(negative_tags)} tags to NOT query.")

        print(f"  [FTS5 Query] {match_query}")

        full_sql = '''
            SELECT i.id, i.file_path, i.tags_combined, i.tag_scores, i.file_mtime, i.thumbnail_path, i.is_favorite
            FROM images i
            INNER JOIN images_fts f ON i.id = f.id
            WHERE images_fts MATCH ?
        '''
        
        cursor = self.db.conn.cursor()
        cursor.execute(full_sql, (match_query,))
        raw_results = [dict(row) for row in cursor.fetchall()]
        
        print(f"  -> DB Hits: {len(raw_results)} (Scoring...)")

        scored_results = []
        for row in raw_results:
            scores_dict = {}
            if row.get('tag_scores'):
                try:
                    scores_dict = json.loads(row['tag_scores'])
                except json.JSONDecodeError:
                    pass
            row['parsed_tag_scores'] = scores_dict

            score, matches = self.calculate_image_score_with_details(row['tags_combined'], search_groups, row['parsed_tag_scores'])

            row['match_score'] = score
            row['matched_tags'] = matches
            scored_results.append(row)
            
        if is_bookmarked:
            scored_results.sort(key=lambda x: (x.get('is_favorite', 0), x['match_score'], x['file_mtime']), reverse=True)
        else:
            scored_results.sort(key=lambda x: (x['match_score'], x['file_mtime']), reverse=True)

        return scored_results

if __name__ == "__main__":
    searcher = TagSearchLight()
    q = "黒髪 ロングヘア" 
    results = searcher.search(q)
    
    print(f"\n【Final Result (Light)】")
    print("-" * 60)
    for i, row in enumerate(results[:5]):
        print(f"Rank {i+1} [Score: {row['match_score']:.3f}]")
        print(f"  Path: {row['file_path']}")
        print("  Matches:")
        for m in row['matched_tags']:
            print(f"    [{m['tag']}] {m['final']:.3f} = {m['sim']:.3f}(sim) * {m['ai']:.3f}(ai) * {m['idf']:.3f}(idf)")
        print("-" * 60)
