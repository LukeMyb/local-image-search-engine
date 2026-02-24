import sqlite3
import re
from deep_translator import GoogleTranslator
from core.database import ImageDatabase

class TagSearch:
    def __init__(self, db_path="data/db/index.db"):
        self.db = ImageDatabase(db_path)
        self.translator = GoogleTranslator(source='ja', target='en')

    def is_english_only(self, text):
        #文字列が半角英数字・記号のみ(ASCII文字)で構成されているか判定
        try:
            text.encode('ascii')
            return True
        except UnicodeEncodeError:
            return False

    def get_search_tags(self, query_text):
        """
        日本語を分割してから個別に翻訳し、検索用タグリストを作成する
        例: "銀髪 ロング" -> ["silver hair", "long hair"]
        """
        # スペース（全角半角）で分割
        raw_words = re.split(r'[ \u3000,]+', query_text)
        search_tags = []

        for word in raw_words:
            if not word: continue
            
            if self.is_english_only(word):
                # 英語ならそのまま（アンダースコアをスペースに置換）
                search_tags.append(word.replace("_", " "))
            else:
                # 日本語なら単語ごとに翻訳
                try:
                    translated = self.translator.translate(word).lower()
                    # 翻訳結果が "long" なら "long hair" に補完されるよう工夫が必要な場合もあるが
                    # まずはそのまま採用
                    search_tags.append(translated)
                except:
                    search_tags.append(word)
        
        return search_tags

    def search(self, query_text, limit=100):
        # 1. 単語ごとに翻訳してタグリスト化
        tags = self.get_search_tags(query_text)
        if not tags: return []

        print(f"DEBUG: 検索タグ一覧 -> {tags}")

        # 2. SQL構築 (AND検索)
        conditions = []
        params = []
        for t in tags:
            conditions.append("tags_combined LIKE ?")
            params.append(f"%{t}%")
            
        where_clause = " AND ".join(conditions)
        sql = f"""
            SELECT id, file_path, tags_combined 
            FROM images 
            WHERE {where_clause}
            ORDER BY file_mtime DESC 
            LIMIT ?
        """
        params.append(limit)
        
        cursor = self.db.conn.cursor()
        cursor.execute(sql, params)
        results = cursor.fetchall()
        
        return [dict(row) for row in results]

if __name__ == "__main__":
    searcher = TagSearch()
    # シンプルなテスト
    # ヒットしなければベクトル検索の出番です
    res = searcher.search("銀髪 ロング") 
    print(f"結果: {len(res)}件ヒット")