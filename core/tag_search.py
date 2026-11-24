import csv
import re
import os
import json
import math
from collections import Counter
from typing import Optional

from core.database import ImageDatabase
from core.heavy_worker import HeavyEngineManager
from core.text_utils import normalize_kana


# 類似画像検索（キャラ検索）で使用する髪色・目の色・除外タグ定義
VALID_HAIR_COLORS = {
    "blonde hair",
    "brown hair",
    "black hair",
    "blue hair",
    "purple hair",
    "pink hair",
    "white hair",
    "red hair",
    "grey hair",
    "gray hair",
    "green hair",
    "silver hair",
    "orange hair",
    "aqua hair",
    "light blue hair",
    "light green hair",
    "dark blue hair",
    "dark brown hair",
}

VALID_EYE_COLORS = {
    "blue eyes",
    "red eyes",
    "brown eyes",
    "green eyes",
    "purple eyes",
    "yellow eyes",
    "pink eyes",
    "black eyes",
    "aqua eyes",
    "orange eyes",
    "grey eyes",
    "gray eyes",
    "white eyes",
    "multicolored eyes",
}

MULTICOLOR_KEYWORDS = (
    "multicolored",
    "two-tone",
    "streaked",
    "colored inner",
    "split-color",
)

# 周囲画像の仲間判定およびチャームポイント選出から除外するカテゴリー・サブカテゴリー定義
NON_CHARACTER_CATEGORIES = {
    "meta",
    "expression_pose",
}

NON_CHARACTER_SUB_CATEGORIES = {
    "clothing_state",
    "underwear",
    "chest",
    "body_part",
    "physique",
    "eye_state",
    "effect",
    "scene",
}

# チャームポイント選出時に追加で除外する「家具・基本髪長・大枠の汎用衣類」タグ
SCENE_AND_GENERIC_TAGS = {
    "tatami", "futon", "pillow", "bed", "bed sheet", "bedding",
    "sliding doors", "shouji", "window", "curtains", "chair", "desk", "table", "couch", "sofa", "floor", "wooden floor",
    "long hair", "short hair", "very long hair", "medium hair", "bangs", "hair between eyes", "sidelocks", "blunt bangs", "crossed bangs", "parted bangs", "swept bangs",
    "long sleeves", "short sleeves", "wide sleeves", "sleeves past wrists", "skirt", "pleated skirt", "shirt", "white shirt", "dress", "jacket", "shoes", "gloves", "socks", "thighhighs", "jewelry", "hair ornament", "ribbon", "bow",
}


def _is_hair_color_tag(norm_tag: str) -> bool:
    return norm_tag in VALID_HAIR_COLORS or (
        norm_tag.endswith(" hair")
        and any(k in norm_tag for k in MULTICOLOR_KEYWORDS)
    )



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
        self.normalized_alias_map = {
            normalize_kana(alias): actual for alias, actual in self.alias_map.items()
        }
        self.alias_entries = [
            (alias, normalize_kana(alias), actual, actual.replace("_", " "))
            for alias, actual in self.alias_map.items()
        ]

        # タグカテゴリー辞書ロード (data/tag_categories.csv)
        self.tag_categories = self._load_tag_categories()

        # DB内タグのオンメモリ集計
        self._build_tag_counts()

    def _load_tag_categories(
        self, path: str = "data/tag_categories.csv"
    ) -> dict[str, tuple[str, str]]:
        """
        data/tag_categories.csv をロードして {スペース区切りタグ名: (category, sub_category)} の辞書を返す。
        万が一ファイルが未生成の場合は scripts.download_assets.build_tag_categories() で自動生成する。
        """
        if not os.path.exists(path):
            try:
                from scripts.download_assets import build_tag_categories

                build_tag_categories(output_path=path)
            except Exception as e:
                print(f"    [!] Failed to auto-build {path}: {e}")

        categories: dict[str, tuple[str, str]] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        t = row.get("tag")
                        cat = row.get("category")
                        sub_cat = row.get("sub_category")
                        if not t or not cat or not sub_cat:
                            continue
                        norm_tag = t.strip().lower().replace("_", " ")
                        categories[norm_tag] = (cat.strip(), sub_cat.strip())
                print(f"    - Loaded {len(categories)} tag categories from {path}")
            except Exception as e:
                print(f"    [!] Failed to load {path}: {e}")
        return categories

    def _is_non_character_tag(self, norm_tag: str) -> bool:
        """
        指定タグ（スペース区切り小文字）がポーズ・行為・表情・身体部位・メタ等の
        キャラ固有判定から除外すべきタグかどうかをカテゴリー辞書から判定する
        """
        cat_info = self.tag_categories.get(norm_tag)
        if not cat_info:
            return False
        cat, sub_cat = cat_info
        return (
            cat in NON_CHARACTER_CATEGORIES
            or sub_cat in NON_CHARACTER_SUB_CATEGORIES
        )

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

        # OR検索(|)の入力中は最後の「|」以降の単語を対象にする
        or_prefix = ""
        target_token = current_word
        if "|" in current_word:
            or_parts = current_word.split("|")
            or_prefix = "|".join(or_parts[:-1]) + "|"
            target_token = or_parts[-1]

        # 任意加点(?/？)や除外(-)のプレフィックスを分離して補完できるようにする
        modifier_prefix = ""
        if target_token.startswith(("?", "？")):
            modifier_prefix = "?"
            target_token = target_token.lstrip("?？")
        elif target_token.startswith("-"):
            modifier_prefix = "-"
            target_token = target_token.lstrip("-")

        prefix = target_token.lower().strip()
        if not prefix:
            return []
        prefix_under = prefix.replace(" ", "_")
        norm_prefix = normalize_kana(prefix)
        norm_prefix_under = norm_prefix.replace(" ", "_")
        full_base_query = base_query + or_prefix + modifier_prefix

        candidates = []

        # 1. 実際のタグ（DBに存在するタグ）からの検索
        for tag, count in self.tag_counts.items():
            underscored_tag = tag.replace(" ", "_")
            matched = prefix in tag or prefix_under in underscored_tag
            if not matched and not tag.isascii():
                norm_tag = normalize_kana(tag)
                matched = (
                    norm_prefix in norm_tag
                    or norm_prefix_under in norm_tag.replace(" ", "_")
                )
            if matched:
                candidates.append(
                    {
                        "display": f"{underscored_tag} ({count}件)",
                        "query": full_base_query + underscored_tag,
                        "count": count,
                    }
                )

        # 2. 俗語（Alias辞書）からの検索（ひらがな・カタカナを同一視）
        for alias, norm_alias, actual, norm_actual in self.alias_entries:
            if (prefix_under in alias or norm_prefix_under in norm_alias) and norm_actual in self.tag_counts:
                count = self.tag_counts[norm_actual]
                candidates.append(
                    {
                        "display": f"{alias} -> {actual} ({count}件)",
                        "query": full_base_query + alias,
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
        norm_key = normalize_kana(key).replace(" ", "_")

        # 1. Alias辞書を最優先（完全一致 -> ひらがな/カタカナ正規化一致）
        actual_tag = self.alias_map.get(key)
        if actual_tag is None:
            actual_tag = self.normalized_alias_map.get(norm_key)

        if actual_tag is not None:
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
        self,
        image_tags_str,
        search_groups,
        parsed_tag_scores,
        optional_search_groups=None,
    ):
        total_score = 0.0
        matched_by_tag = {}
        if not image_tags_str:
            return 0.0, []

        img_tags = {
            t.strip().lower().replace("_", " ") for t in image_tags_str.split(",")
        }

        group_entries = [(g, False) for g in search_groups]
        if optional_search_groups:
            group_entries.extend((g, True) for g in optional_search_groups)

        for group_map, is_optional in group_entries:
            group_max_score = 0.0
            group_matches = []

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

                    detail = {
                        "tag": norm_search_tag,
                        "final": final_word_score,
                        "sim": sim_weight,
                        "ai": ai_weight,
                        "idf": idf_weight,
                        "is_optional": is_optional,
                    }
                    group_matches.append(detail)
                    if final_word_score > group_max_score:
                        group_max_score = final_word_score

            if group_matches:
                total_score += group_max_score
                for detail in group_matches:
                    tag_key = detail["tag"]
                    prev = matched_by_tag.get(tag_key)
                    if prev is None:
                        matched_by_tag[tag_key] = detail
                    else:
                        # 必須ヒットと任意(?)ヒットが重複した場合は必須ヒット(is_optional=False)を優先
                        if prev.get("is_optional", False) and not is_optional:
                            matched_by_tag[tag_key] = detail
                        elif prev.get("is_optional", False) == is_optional and detail["final"] > prev["final"]:
                            matched_by_tag[tag_key] = detail

        matched_details = list(matched_by_tag.values())
        return total_score, matched_details

    def search(self, user_query, trash_only=False):
        query = re.sub(r"\s*\|\s*", "|", user_query)

        words = re.split(r"[ \u3000,]+", query)
        words = [w for w in words if w]
        if not words:
            return []

        positive_groups = []
        optional_groups = []
        negative_words = []
        for w in words:
            if w.startswith("-") and len(w) > 1:
                negative_words.append(w[1:])
            elif w.startswith(("?", "？")) and len(w) > 1:
                parts = [p.lstrip("?？") for p in w[1:].split("|") if p.lstrip("?？")]
                if parts:
                    optional_groups.append(parts)
            else:
                parts = [p for p in w.split("|") if p]
                if parts:
                    positive_groups.append(parts)

        if not positive_groups and not optional_groups:
            return []

        print(f"\n{'='*60}")
        print(f" Query: '{user_query}' (Mode: {'HEAVY' if self._is_heavy else 'LIGHT'})")
        print(f"{'='*60}")

        required_search_groups = []
        optional_search_groups = []

        for or_words in positive_groups:
            combined_similar_tags_map = {}
            print(f"  [OR Group (Required)] Processing: {or_words}")

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

            required_search_groups.append(combined_similar_tags_map)

        for or_words in optional_groups:
            combined_similar_tags_map = {}
            print(f"  [OR Group (Optional Boost)] Processing: {or_words}")

            for word in or_words:
                final_tag, similar_tags_map = self.find_similar_tags_with_score(word)
                print(
                    f"  Target (Optional): '{final_tag}' -> Candidates: {len(similar_tags_map)}"
                )

                for t, s in similar_tags_map.items():
                    if t not in combined_similar_tags_map or s > combined_similar_tags_map.get(
                        t, 0
                    ):
                        combined_similar_tags_map[t] = s

            optional_search_groups.append(combined_similar_tags_map)

        # スコア計算には必須グループと任意（加点）グループの両方を使用する
        search_groups = required_search_groups + optional_search_groups

        fast_lookup = {}
        for group_map in search_groups:
            for tag, score in group_map.items():
                norm_tag = tag.lower().replace("_", " ")
                if norm_tag not in fast_lookup or score > fast_lookup.get(norm_tag, 0):
                    fast_lookup[norm_tag] = score

        # FTS5の絞り込み条件を構築（必須グループがある場合は必須グループのみでAND検索し、任意グループは除外しない）
        match_groups = []
        if required_search_groups:
            for group_map in required_search_groups:
                or_parts = []
                for tag in group_map.keys():
                    norm_tag = tag.replace("_", " ")
                    or_parts.append(f'"{norm_tag}"')
                if or_parts:
                    match_groups.append(f"({' OR '.join(or_parts)})")
            if not match_groups:
                return []
            match_query = " AND ".join(match_groups)
        else:
            # 任意（?）タグのみが指定された場合は、いずれか1つ以上に一致する画像を広く取得してスコア順に並べる
            for group_map in optional_search_groups:
                or_parts = []
                for tag in group_map.keys():
                    norm_tag = tag.replace("_", " ")
                    or_parts.append(f'"{norm_tag}"')
                if or_parts:
                    match_groups.append(f"({' OR '.join(or_parts)})")
            if not match_groups:
                return []
            match_query = f"({' OR '.join(match_groups)})"

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
                row["tags_combined"],
                required_search_groups,
                row["parsed_tag_scores"],
                optional_search_groups=optional_search_groups,
            )

            row["match_score"] = score
            row["matched_tags"] = matches
            scored_results.append(row)

        scored_results.sort(
            key=lambda x: (x["match_score"], x["file_mtime"]), reverse=True
        )

        return scored_results

    def _get_tag_idf(self, norm_tag: str) -> float:
        """DB全体における指定タグのレア度（IDF）を算出する"""
        db_count = self.tag_counts.get(norm_tag, 0)
        total_imgs = max(self.total_images, 1)
        return math.log10(total_imgs / max(db_count, 10))

    def build_similar_query(self, image_id: int, use_neighbors: bool = False) -> dict:
        """
        指定画像の類似キャラ検索用クエリを構築する。
        use_neighbors=True の場合は前後±3枚の画像のタグを分析し、
        1. 共通するレアタグの重み合計から同じセット（同キャラ）の周囲画像を特定（保存日時の時間差は不問）
        2. 仲間内の髪色・目の色のブレをOR（|）で統合
        3. 緩い論理積（多数決）からDB全体でレア度（IDF）が高い上位タグをチャームポイント（?加点タグ）として抽出
        """
        target = self.db.get_image_by_id(image_id)
        if not target or not target.get("tags_combined"):
            return {
                "query": "",
                "matched_neighbor_ids": [],
                "charm_tags": [],
            }

        raw_target_tags = [
            t.strip().lower().replace("_", " ")
            for t in target["tags_combined"].split(",")
            if t.strip()
        ]
        t_tags = set(raw_target_tags)
        t_hairs = {t for t in t_tags if t in VALID_HAIR_COLORS}

        matched_neighbors = []
        if use_neighbors:
            cursor = self.db.conn.cursor()
            deleted_flag = int(target.get("is_deleted", 0))
            t_mtime = target["file_mtime"]
            t_id = target["id"]

            # 並び順（file_mtime, id）において対象画像の前後3枚ずつ（計最大6枚）を取得
            cursor.execute(
                """
                SELECT id, tags_combined
                FROM images
                WHERE is_deleted = ?
                  AND (file_mtime < ? OR (file_mtime = ? AND id < ?))
                ORDER BY file_mtime DESC, id DESC
                LIMIT 3
                """,
                (deleted_flag, t_mtime, t_mtime, t_id),
            )
            older_neighbors = [dict(r) for r in cursor.fetchall()]

            cursor.execute(
                """
                SELECT id, tags_combined
                FROM images
                WHERE is_deleted = ?
                  AND (file_mtime > ? OR (file_mtime = ? AND id > ?))
                ORDER BY file_mtime ASC, id ASC
                LIMIT 3
                """,
                (deleted_flag, t_mtime, t_mtime, t_id),
            )
            newer_neighbors = [dict(r) for r in cursor.fetchall()]

            candidates = list(reversed(older_neighbors)) + newer_neighbors
            for n in candidates:
                n_tags_str = n.get("tags_combined") or ""
                n_tags = {
                    t.strip().lower().replace("_", " ")
                    for t in n_tags_str.split(",")
                    if t.strip()
                }
                if not n_tags:
                    continue

                n_hairs = {t for t in n_tags if t in VALID_HAIR_COLORS}
                hair_overlap = bool(t_hairs & n_hairs)
                common = {
                    t for t in (t_tags & n_tags) if not self._is_non_character_tag(t)
                }
                score = sum(
                    self._get_tag_idf(t) ** 2
                    for t in common
                    if self._get_tag_idf(t) >= 0.65
                )
                threshold = 3.2 if hair_overlap else 10.0
                if score >= threshold:
                    matched_neighbors.append((n["id"], round(score, 2), n_tags))

        all_tag_sets = [t_tags] + [nt for _, _, nt in matched_neighbors]
        group_size = len(all_tag_sets)

        # --- 1. 髪色タグの抽出（対象画像＋仲間内で半数以上に出現した髪色を統合） ---
        hair_tags_ordered = [t for t in raw_target_tags if _is_hair_color_tag(t)]
        if matched_neighbors:
            hair_counter = Counter()
            for tag_set in all_tag_sets:
                for t in tag_set:
                    if _is_hair_color_tag(t):
                        hair_counter[t] += 1
            min_hair_count = max(2, math.ceil(group_size * 0.5))
            for t, cnt in hair_counter.items():
                if cnt >= min_hair_count and t not in hair_tags_ordered:
                    hair_tags_ordered.append(t)

        if not hair_tags_ordered:
            return {
                "query": "",
                "matched_neighbor_ids": [m[0] for m in matched_neighbors],
                "charm_tags": [],
            }

        multi_tags = [
            t.replace(" ", "_")
            for t in hair_tags_ordered
            if any(k in t for k in MULTICOLOR_KEYWORDS)
        ]
        normal_tags = [
            t.replace(" ", "_")
            for t in hair_tags_ordered
            if not any(k in t for k in MULTICOLOR_KEYWORDS)
        ]

        query_parts = []
        if multi_tags:
            query_parts.append("|".join(multi_tags))
        if normal_tags:
            if multi_tags:
                query_parts.append(" ".join(normal_tags))
            else:
                query_parts.append("|".join(normal_tags))

        # --- 2. 目の色タグの抽出（対象画像が目を閉じていても仲間から目の色を補完） ---
        has_closed_eyes = "closed eyes" in t_tags
        eye_tags_ordered = (
            []
            if has_closed_eyes
            else [t for t in raw_target_tags if t in VALID_EYE_COLORS]
        )
        if matched_neighbors:
            eye_counter = Counter()
            open_eye_imgs = 0
            for tag_set in all_tag_sets:
                img_eyes = [t for t in tag_set if t in VALID_EYE_COLORS]
                if img_eyes:
                    open_eye_imgs += 1
                    for t in img_eyes:
                        eye_counter[t] += 1
            min_eye_count = 1 if open_eye_imgs <= 1 else max(2, math.ceil(open_eye_imgs * 0.5))
            for t, cnt in eye_counter.items():
                if cnt >= min_eye_count and t not in eye_tags_ordered:
                    eye_tags_ordered.append(t)

        if eye_tags_ordered:
            formatted_eyes = [t.replace(" ", "_") for t in eye_tags_ordered]
            query_parts.append("|".join(["closed_eyes"] + formatted_eyes))
        elif has_closed_eyes:
            query_parts.append("closed_eyes")

        # --- 3. チャームポイントの抽出（緩い論理積 × DB全体のIDF上位） ---
        charm_tags = []
        if matched_neighbors:
            tag_counter = Counter()
            for tag_set in all_tag_sets:
                tag_counter.update(tag_set)

            # 2〜3枚のときは完全一致（論理積）、4枚以上のときは1枚の抜けまで許容（多数決）
            min_charm_count = group_size if group_size <= 3 else group_size - 1

            charm_candidates = []
            for t, cnt in tag_counter.items():
                if cnt < min_charm_count:
                    continue
                if self._is_non_character_tag(t) or t in SCENE_AND_GENERIC_TAGS:
                    continue
                if _is_hair_color_tag(t) or t in VALID_EYE_COLORS:
                    continue
                tag_idf = self._get_tag_idf(t)
                if tag_idf < 0.85:
                    continue
                charm_candidates.append((t, cnt, tag_idf))

            # 全画像一致（cnt == group_size）を最優先し、その中でレア度（IDF）が高い順にソート
            charm_candidates.sort(
                key=lambda item: (item[1] == group_size, item[2]),
                reverse=True,
            )
            charm_tags = [item[0].replace(" ", "_") for item in charm_candidates[:3]]
            for ct in charm_tags:
                query_parts.append(f"?{ct}")

        final_query = " ".join(query_parts).strip()
        return {
            "query": final_query,
            "matched_neighbor_ids": [m[0] for m in matched_neighbors],
            "charm_tags": charm_tags,
        }

