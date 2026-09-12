import re
from fastapi import HTTPException
from core.tag_search_light import TagSearchLight
from core.database import ImageDatabase

class SearchManagerLight:
    """
    検索全体のオーケストレーター（軽量版）
    絵柄検索エンジンを排除し、タグ検索エンジン（軽量版）のみを使用する
    """
    def __init__(self, db_path="data/db/index.db"):
        print("  [SearchManagerLight] 初期化中...")
        self.db = ImageDatabase(db_path)
        
        # タグ検索エンジン(軽量版)を初期化
        self.tag_searcher = TagSearchLight(db_path)
        
        # 軽量版のため絵柄検索エンジンはロードしない
        self.style_engine = None

    def get_suggestions(self, query_text, limit=10):
        if not query_text: return []

        normalized_query = query_text.replace('　', ' ')
        parts = normalized_query.split(' ')
        current_word = parts[-1]
        
        if not current_word:
            return []

        base_query = " ".join(parts[:-1]) + " " if len(parts) > 1 else ""

        # 絵柄検索(style:)のサジェスト処理はサポートしない
        if current_word.lower().startswith("style:"):
            return []
            
        # 純粋なタグ検索のサジェストに丸投げ
        return self.tag_searcher.get_suggestions(query_text, limit)

    def search(self, user_query, is_bookmarked=False, sort_order="score"):
        # 絵柄タグ(style:xxx)が含まれているかチェック
        style_match = re.search(r'style:([^\s|]+)', user_query)

        # 軽量版では絵柄検索はサポートしないため、見つかった場合はエラーを返す
        if style_match:
            raise HTTPException(status_code=400, detail="軽量モードのため絵柄検索は使用できません")

        # ソートの共通処理用の内部関数
        def sort_by_order(res_list):
            if sort_order == "favorite":
                res_list.sort(key=lambda x: (x.get('is_favorite', 0), x.get('match_score', 0), x['file_mtime']), reverse=True)
            elif sort_order == "newest":
                res_list.sort(key=lambda x: (x['file_mtime'], x.get('match_score', 0)), reverse=True)
            else: # "score"
                res_list.sort(key=lambda x: (x.get('match_score', 0), x['file_mtime']), reverse=True)
            return res_list
        
        # タグ検索の実行
        tag_results = self.tag_searcher.search(user_query, is_bookmarked=False)

        # 結果をソートして返す
        return sort_by_order(tag_results)
