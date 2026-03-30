from core.tag_search import TagSearch

class SearchManager:
    """
    検索全体のオーケストレーター
    とりあえず既存のTagSearchへ処理を横流しするだけ
    """
    def __init__(self, db_path="data/db/index.db", tag_index_path="data/tag_vector_index.bin"):
        print("  [SearchManager] 初期化中...")
        # とりあえず既存のTagSearchをそのまま生成して保持する
        self.tag_searcher = TagSearch(db_path, tag_index_path)
        
        # app.pyとの互換性を保つため、TagSearch内部のstyle_engineへの参照を持っておく
        self.style_engine = self.tag_searcher.style_engine

    def search(self, user_query, is_bookmarked=False):
        # 既存のTagSearchのsearchメソッドに丸投げ
        return self.tag_searcher.search(user_query, is_bookmarked)

    def get_suggestions(self, query_text, limit=10):
        # 既存のTagSearchのget_suggestionsメソッドに丸投げ
        return self.tag_searcher.get_suggestions(query_text, limit)