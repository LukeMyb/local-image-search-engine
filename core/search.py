import re
from fastapi import HTTPException
from core.tag_search import TagSearch
from core.database import ImageDatabase
from core.heavy_worker import HeavyEngineManager


class SearchManager:
    """
    検索全体のオーケストレーター（軽量・重量モード統合版）
    起動時は軽量モードとして高速・省メモリで立ち上がり、
    指示された時のみ HeavyEngineManager（子プロセス）を起動してAI検索・絵柄作成を有効化する。
    """

    def __init__(
        self,
        db_path: str = "data/db/index.db",
        tag_index_path: str = "data/tag_vector_index.bin",
        style_index_path: str = "data/faiss/style.index",
    ):
        print("  [SearchManager] 初期化中 (初期状態: 軽量モード)...")
        self.db = ImageDatabase(db_path)
        # 起動時にエクスプローラーで削除・移動された画像の3状態同期（ゴーストデータのクリーンアップ）を実行
        self.db.sync_filesystem_states()

        # 重量AIワーカー管理マネージャー（起動時は子プロセス未起動＝軽量状態）
        self.heavy_engine = HeavyEngineManager(
            db_path=db_path,
            tag_index_path=tag_index_path,
            style_index_path=style_index_path,
        )

        # タグ検索エンジンを初期化
        self.tag_searcher = TagSearch(
            db_path=db_path,
            tag_index_path=tag_index_path,
            db=self.db,
            heavy_engine=self.heavy_engine,
        )

    def get_mode_status(self):
        """現在のサーバーモード状態 ("light" | "starting" | "heavy") を返す"""
        return self.heavy_engine.get_status()

    def set_mode(self, target_mode: str, wait: bool = False):
        """サーバーモードを切り替える ("light" または "heavy")"""
        if target_mode == "heavy":
            return self.heavy_engine.start(wait=wait)
        elif target_mode == "light":
            return self.heavy_engine.stop()
        else:
            raise ValueError(f"Invalid mode: {target_mode}")

    def get_suggestions(self, query_text, limit=10):
        if not query_text:
            return []

        normalized_query = query_text.replace("　", " ")
        parts = normalized_query.split(" ")
        current_word = parts[-1]

        if not current_word:
            return []

        base_query = " ".join(parts[:-1]) + " " if len(parts) > 1 else ""

        # 絵柄検索(style:)のサジェスト処理（DBから直接取得できるため両モード共通で高速動作）
        if current_word.lower().startswith("style:"):
            styles = self.db.get_all_styles()
            candidates = []
            prefix = current_word.lower()

            for s in styles:
                style_name = s["name"]
                if style_name.lower().startswith(prefix):
                    candidates.append(
                        {
                            "id": s["id"],  # DBから削除するためのID
                            "is_style": True,  # ゴミ箱ボタンを表示するかどうかのフラグ
                            "display": style_name,
                            "query": base_query + style_name,
                            "count": 0,
                        }
                    )
            return candidates

        # それ以外は純粋なタグ検索のサジェストに丸投げ
        return self.tag_searcher.get_suggestions(query_text, limit)

    def search(self, user_query, sort_order="score", trash_only=False):
        self.heavy_engine.touch()
        style_match = re.search(r"style:([^\s|]+)", user_query)
        style_name = None
        style_scores_map = {}
        style_results = []
        deleted_flag = 1 if trash_only else 0

        # ソートの共通処理用の内部関数
        def sort_by_order(res_list):
            if sort_order == "newest":
                res_list.sort(
                    key=lambda x: (x["file_mtime"], x.get("match_score", 0)),
                    reverse=True,
                )
            else:  # "score"
                res_list.sort(
                    key=lambda x: (x.get("match_score", 0), x["file_mtime"]),
                    reverse=True,
                )
            return res_list

        # 絵柄検索の実行
        if style_match:
            style_name = style_match.group(0)
            user_query = user_query.replace(style_name, "").strip()

            if self.heavy_engine.is_heavy_ready:
                print(f"\n{'='*60}")
                print(f" Style Search (Heavy Mode FAISS): '{style_name}'")
                print(f"{'='*60}")

                style_results = self.heavy_engine.search_by_style_name(
                    style_name, threshold=0.98, trash_only=trash_only
                )
                style_scores_map = {
                    res["id"]: res["match_score"] for res in style_results
                }

                if not user_query:
                    return sort_by_order(style_results)

                if not style_scores_map:
                    print("  -> 絵柄に一致する画像が0件のため、検索を終了します。")
                    return []

                print(
                    f"  -> 絵柄検索で {len(style_scores_map)}件 ヒット。続けてタグ検索で絞り込みます..."
                )
            else:
                print(f"\n{'='*60}")
                print(f" Style Search (Light Mode Cache): '{style_name}'")
                print(f"{'='*60}")

                # 軽量モードではDBに保存されたキャッシュリストを使用する
                style_scores_map = self.db.get_style_cache(style_name)

                if not style_scores_map:
                    raise HTTPException(
                        status_code=400,
                        detail=f"絵柄タグ '{style_name}' のキャッシュが見つかりません。重量モードに切り替えて実行してください。",
                    )

                print(
                    f"  -> キャッシュから {len(style_scores_map)}件 の画像を読み込みました。"
                )

                if not user_query:
                    image_ids = list(style_scores_map.keys())
                    raw_style_results = self.db.get_images_by_ids(image_ids)
                    style_results = [
                        row
                        for row in raw_style_results
                        if row.get("is_deleted", 0) == deleted_flag
                    ]

                    for row in style_results:
                        row["match_score"] = style_scores_map.get(row["id"], 0)
                        row["matched_tags"] = [
                            {
                                "is_style": True,
                                "tag": style_name,
                                "final": 0,
                                "sim": row["match_score"],
                                "base": 0,
                                "multiplier": 1.0,
                            }
                        ]
                    return sort_by_order(style_results)

        # タグ検索の実行
        tag_results = self.tag_searcher.search(user_query, trash_only=trash_only)

        # 結果のAND結合と最終スコア計算
        if not style_name:
            return sort_by_order(tag_results)

        scored_results = []
        for row in tag_results:
            if row["id"] not in style_scores_map:
                continue

            style_score = style_scores_map[row["id"]]
            style_multiplier = 1.0 + max(0, (style_score - 0.98) * 100)
            base_score = max(row["match_score"], 1.0)
            final_score = base_score * style_multiplier

            row["match_score"] = final_score
            row["matched_tags"].append(
                {
                    "is_style": True,
                    "tag": style_name,
                    "final": final_score - base_score,
                    "sim": style_score,
                    "base": base_score,
                    "multiplier": style_multiplier,
                }
            )
            scored_results.append(row)

        return sort_by_order(scored_results)
