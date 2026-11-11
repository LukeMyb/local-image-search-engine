import csv
import re
import os
import json
import math
from collections import Counter
from typing import Optional

from core.database import ImageDatabase
from core.heavy_worker import HeavyEngineManager


class TagSearch:
    """
    タグ検索エンジン（軽量モード・重量モード統合版）
    起動時は辞書とDB内タグ集計のみをロードし、省メモリ・高速（約1秒）で立ち上がる。
    重量ワーカー（HeavyEngineManager）が稼働中の場合のみ、未知語の翻訳API呼び出しと
    CLIPベクトル類似タグ検索をワーカー子プロセス経由で実行する。
    """

    def __init__(
        self,
        db_path: str = "data/db/index.db",
        tag_index_path: str = "data/tag_vector_index.bin",
        db: Optional[ImageDatabase] = None,
        heavy_engine: Optional[HeavyEngineManager] = None,
    ):
        self.db = db if db is not None else ImageDatabase(db_path)
        self.heavy_engine = heavy_engine

        # 辞書ロード (10万語 + 手動修正)
        self.alias_map = self._load_all_aliases()

        # DB内タグのオンメモリ集計
        self._build_tag_counts()

    def _load_all_aliases(self):
        """10万語辞書と手動辞書を統合してロード"""
        combined = {}
        # 読み込む順番: 10万語(tag_aliases) -> 手動(manual_alias)
        paths = ["data/tag_aliases.csv", "data/manual_alias.csv"]

        print("  [System] Loading dictionaries...")
        for path in paths:
            if os.path.exists(path):
                try:
                    count = 0
                    with open(path, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            k = row.get("alias")
                            v = row.get("actual")
                            if k is None or v is None:
                                continue
                            # 全て小文字、スペースをアンダースコアに統一
                            key = k.strip().lower().replace(" ", "_")
                            val = v.strip().lower().replace(" ", "_")
                            combined[key] = val
                            count += 1
                    print(f"    - Loaded {count} entries from {path}")
                except Exception as e:
                    print(f"    [!] Failed to load {path}: {e}")
        return combined

    def _build_tag_counts(self):
        """DB内の全画像（未削除のみ）から存在するタグとその件数を集計してメモリに保持する"""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT tags_combined FROM images WHERE is_deleted = 0")

        rows = cursor.fetchall()
        self.total_images = len(rows)

        counts = Counter()
        for (tags_str,) in rows:
            if not tags_str:
                continue
            counts.update(t.strip().lower() for t in tags_str.split(",") if t.strip())

        self.tag_counts = dict(counts)
        print(f"  [System] Cached {len(self.tag_counts)} unique tags from DB.")

    def adjust_tag_counts(self, image_ids: list[int], delta: int):
        """論理削除(delta=-1)や復元(delta=+1)時に、対象画像のタグ件数のみを高速に差分更新する"""
        if not image_ids:
            return
        cursor = self.db.conn.cursor()
        placeholders = ",".join(["?"] * len(image_ids))
        cursor.execute(
            f"SELECT tags_combined FROM images WHERE id IN ({placeholders})", image_ids
        )
        rows = cursor.fetchall()
        self.total_images = max(0, self.total_images + delta * len(rows))
        for row in rows:
            tags_str = row[0]
            if not tags_str:
                continue
            tags = [t.strip().lower() for t in tags_str.split(",")]
            for t in tags:
                new_count = self.tag_counts.get(t, 0) + delta
                if new_count > 0:
                    self.tag_counts[t] = new_count
                else:
                    self.tag_counts.pop(t, None)

    def get_suggestions(self, query_text, limit=10):
        """入力された文字列からヒットするサジェスト候補を返す"""
        if not query_text:
            return []

        # 全角スペースを半角に統一してから分割
        normalized_query = query_text.replace("　", " ")
        parts = normalized_query.split(" ")
        current_word = parts[-1]

        # 末尾がスペース（新しい単語の入力待ち）ならサジェスト窓は出さない
        if not current_word:
            return []

        # サジェスト選択時に、前の単語を消さないためのベース文字列
        base_query = " ".join(parts[:-1]) + " " if len(parts) > 1 else ""

        prefix = current_word.lower().strip()
        prefix_under = prefix.replace(" ", "_")

        candidates = []

        # 1. 実際のタグ（DBに存在するタグ）からの検索
        for tag, count in self.tag_counts.items():
            underscored_tag = tag.replace(" ", "_")
            if prefix in tag or prefix_under in underscored_tag:
                candidates.append(
                    {
                        "display": f"{underscored_tag} ({count}件)",
                        "query": base_query + underscored_tag,
                        "count": count,
                    }
                )

        # 2. 俗語（Alias辞書）からの検索
        for alias, actual in self.alias_map.items():
            norm_actual = actual.replace("_", " ")
            if (prefix_under in alias) and norm_actual in self.tag_counts:
                count = self.tag_counts[norm_actual]
                candidates.append(
                    {
                        "display": f"{alias} -> {actual} ({count}件)",
                        "query": base_query + alias,
                        "count": count,
                    }
                )

        # 重複を消して、ヒット件数が多い順にソート
        unique_candidates = {}
        for c in candidates:
            key = c["display"]
            if key not in unique_candidates or unique_candidates[key]["count"] < c["count"]:
                unique_candidates[key] = c

        sorted_results = sorted(
            unique_candidates.values(), key=lambda x: x["count"], reverse=True
        )
        return sorted_results[:limit]

    def _check_alias_or_list(self, word):
        """
        単語がAlias辞書にあるか、あるいは直接DBタグに存在するかを確認する
        戻り値: (変換後のタグ名, ヒットしたかどうか)
        """
        key = word.strip().lower().replace(" ", "_")

        # 1. Alias辞書を最優先
        if key in self.alias_map:
            actual_tag = self.alias_map[key]
            if actual_tag.replace("_", " ") in self.tag_counts or actual_tag in self.tag_counts:
                return actual_tag, True
            return actual_tag, False

        # 2. 直接タグに存在するか確認
        if key.replace("_", " ") in self.tag_counts or key in self.tag_counts:
            return key, True

        return key, False

    @property
    def _is_heavy(self) -> bool:
        return self.heavy_engine is not None and self.heavy_engine.is_heavy_ready

    def find_similar_tags_with_score(self, word, top_k=25):
        # --- Step 1: 初期入力でチェック ---
        norm_word = word.strip().lower().replace(" ", "_")
        english_word, found = self._check_alias_or_list(word)
        if found:
            print(f"  ├─ [Direct/Alias Hit]: {word} -> {english_word}")
            return english_word, {english_word: 1.0}

        # Alias辞書にはあったがDB内に直接そのタグが0件だった場合（すでに英語タグ名は確定済み）
        if english_word != norm_word:
            if not self._is_heavy:
                return english_word, {english_word: 1.0}
            final_query = english_word
            print(f"  ├─ [Alias -> Vector Search]: {word} -> {final_query}")
        else:
            # --- Step 2: キャッシュの確認 ---
            cached_en = self.db.get_cached_translation(word)
            if cached_en:
                print(f"  ├─ [Cache Hit]: {word} -> {cached_en}")
                english_word, found = self._check_alias_or_list(cached_en)
                if found:
                    return english_word, {english_word: 1.0}
                if not self._is_heavy:
                    return cached_en, {cached_en: 1.0}
                final_query = cached_en
            else:
                # 軽量モード時は外部翻訳・CLIP検索を行わずそのまま返す
                if not self._is_heavy:
                    print(f"  ├─ [Not Found]: '{word}' (Used as is in light mode)")
                    return word, {word: 1.0}

                # --- 重量モード時: 子プロセス経由で翻訳APIを実行 ---
                print(f"  ├─ [API Request (Heavy)]: Translating '{word}'...")
                translated_g = ""
                # --- Step 3: Google翻訳 ---
                try:
                    translated_g = self.heavy_engine.translate(word, translator="google")
                    if translated_g:
                        self.db.save_translation_to_cache(word, translated_g)

                    english_word, found = self._check_alias_or_list(translated_g)
                    if found:
                        print(f"  ├─ [Google -> Alias/List]: {word} -> {english_word}")
                        return english_word, {english_word: 1.0}
                except Exception as e:
                    print(f"  [!] Google Translate Error: {e}")

                # --- Step 4: Bing翻訳 ---
                translated_b = ""
                try:
                    translated_b = self.heavy_engine.translate(word, translator="bing")
                    if translated_b:
                        self.db.save_translation_to_cache(word, translated_b)

                    english_word, found = self._check_alias_or_list(translated_b)
                    if found:
                        print(f"  ├─ [Bing -> Alias/List]: {word} -> {english_word}")
                        return english_word, {english_word: 1.0}
                except Exception as e:
                    print(f"  [!] Bing Translate Error: {e}")

                final_query = (
                    translated_b
                    if translated_b
                    else (translated_g if translated_g else word)
                )

        # --- Step 5: CLIPベクトル検索 (重量モードのみ・子プロセスで実行) ---
        print(f"  ├─ [Vector Search (Heavy)]: Using query '{final_query}'")
        try:
            found_tags_map = self.heavy_engine.vector_search_tags(
                final_query=final_query, english_word=english_word, top_k=top_k
            )
            return final_query, found_tags_map
        except Exception as e:
            print(f"  [!] Vector Search Error: {e}")
            return final_query, {final_query: 1.0}

    def calculate_image_score_with_details(
        self, image_tags_str, search_groups, parsed_tag_scores
    ):
        total_score = 0.0
        matched_details = []
        if not image_tags_str:
            return 0.0, []

        img_tags = {
            t.strip().lower().replace("_", " ") for t in image_tags_str.split(",")
        }

        for group_map in search_groups:
            group_max_score = 0.0
            best_match_detail = None

            for search_tag, sim_score in group_map.items():
                norm_search_tag = search_tag.lower().replace("_", " ")
                if norm_search_tag in img_tags:
                    sim_weight = sim_score**5

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
                            "idf": idf_weight,
                        }

            if best_match_detail:
                total_score += group_max_score
                matched_details.append(best_match_detail)

        return total_score, matched_details

    def search(self, user_query, trash_only=False):
        query = re.sub(r"\s*\|\s*", "|", user_query)

        words = re.split(r"[ \u3000,]+", query)
        words = [w for w in words if w]
        if not words:
            return []

        positive_groups = []
        negative_words = []
        for w in words:
            if w.startswith("-") and len(w) > 1:
                negative_words.append(w[1:])
            else:
                parts = w.split("|")
                positive_groups.append(parts)

        if not positive_groups:
            return []

        print(f"\n{'='*60}")
        print(f" Query: '{user_query}' (Mode: {'HEAVY' if self._is_heavy else 'LIGHT'})")
        print(f"{'='*60}")

        search_groups = []

        for or_words in positive_groups:
            combined_similar_tags_map = {}
            print(f"  [OR Group] Processing: {or_words}")

            for word in or_words:
                final_tag, similar_tags_map = self.find_similar_tags_with_score(word)
                print(
                    f"  Target: '{final_tag}' -> Candidates: {len(similar_tags_map)}"
                )

                for t, s in similar_tags_map.items():
                    if t not in combined_similar_tags_map or s > combined_similar_tags_map.get(
                        t, 0
                    ):
                        combined_similar_tags_map[t] = s

            search_groups.append(combined_similar_tags_map)

        match_groups = []

        fast_lookup = {}
        for group_map in search_groups:
            for tag, score in group_map.items():
                norm_tag = tag.lower().replace("_", " ")
                if norm_tag not in fast_lookup or score > fast_lookup.get(norm_tag, 0):
                    fast_lookup[norm_tag] = score

        for group_map in search_groups:
            or_parts = []
            for tag in group_map.keys():
                norm_tag = tag.replace("_", " ")
                or_parts.append(f'"{norm_tag}"')
            if or_parts:
                match_groups.append(f"({' OR '.join(or_parts)})")

        if not match_groups:
            return []

        match_query = " AND ".join(match_groups)

        if negative_words:
            negative_tags = set()
            print("  [Negative Search] Processing exclusions...")
            for word in negative_words:
                _, similar_tags_map = self.find_similar_tags_with_score(word)
                for tag in similar_tags_map.keys():
                    norm_tag = tag.replace("_", " ")
                    if norm_tag not in fast_lookup:
                        negative_tags.add(f'"{norm_tag}"')

            if negative_tags:
                not_string = " NOT ".join(list(negative_tags))
                match_query = f"{match_query} NOT {not_string}"
                print(f"  -> Added {len(negative_tags)} tags to NOT query.")

        print(f"  [FTS5 Query] {match_query}")

        deleted_flag = 1 if trash_only else 0
        full_sql = """
            SELECT i.id, i.file_path, i.tags_combined, i.tag_scores, i.file_mtime, i.thumbnail_path, i.is_favorite, i.is_deleted
            FROM images i
            INNER JOIN images_fts f ON i.id = f.id
            WHERE images_fts MATCH ? AND i.is_deleted = ?
        """

        cursor = self.db.conn.cursor()
        cursor.execute(full_sql, (match_query, deleted_flag))
        raw_results = [dict(row) for row in cursor.fetchall()]

        print(f"  -> DB Hits: {len(raw_results)} (Scoring...)")

        scored_results = []
        for row in raw_results:
            scores_dict = {}
            if row.get("tag_scores"):
                try:
                    scores_dict = json.loads(row["tag_scores"])
                except json.JSONDecodeError:
                    pass
            row["parsed_tag_scores"] = scores_dict

            score, matches = self.calculate_image_score_with_details(
                row["tags_combined"], search_groups, row["parsed_tag_scores"]
            )

            row["match_score"] = score
            row["matched_tags"] = matches
            scored_results.append(row)

        scored_results.sort(
            key=lambda x: (x["match_score"], x["file_mtime"]), reverse=True
        )

        return scored_results
