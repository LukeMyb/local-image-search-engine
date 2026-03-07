import sqlite3
import os
import json
import numpy as np

class ImageDatabase:
    def __init__(self, db_path="data/db/index.db"):
        #データベースへの接続と初期化
        os.makedirs(os.path.dirname(db_path), exist_ok=True) #dbの存在を確認(無ければ生成)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row #tupleをdictのように扱えるようになる
        self._create_tables()

    def _create_tables(self):
        #テーブルと検索高速化のためのインデックスを作成
        cursor = self.conn.cursor() #SQLを送る窓口を作成
        
        #Xの差分画像クラスタリング用にfile_mtime(REAL型(小数点も含むUnix))を追加
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_mtime REAL NOT NULL,
                thumbnail_path TEXT,
                tags_combined TEXT,
                tag_scores TEXT,
                is_thumbnail_created INTEGER DEFAULT 0,
                is_processed_vector INTEGER DEFAULT 0,
                is_processed_tag INTEGER DEFAULT 0,
                is_favorite INTEGER DEFAULT 0
            )
        ''')

        #未処理画像を瞬時に見つけるためのインデックス
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unprocessed_thumb ON images(is_thumbnail_created)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unprocessed_vector ON images(is_processed_vector)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unprocessed_tag ON images(is_processed_tag)')

        # ---------------------------------------------------------
        # 以下、FTS5（全文検索）用の仮想テーブルと自動同期ロジックの追加
        # ---------------------------------------------------------
        
        # 1. 検索専用の仮想テーブル（インデックス）を作成
        # tokenize="unicode61" を指定することで、記号やスペース区切りの単語を正確に分割して索引化できる
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS images_fts USING fts5(
                id UNINDEXED, -- 画像ID（検索対象ではないが、大元のデータと紐付けるために必要）
                tags_combined, -- 検索対象となるタグ文字列
                tokenize="unicode61"
            )
        ''')

        # 2. 既存データの自動移行（初回のみ実行される）
        # imagesテーブルにはタグがあるのに、FTS5テーブルにはまだ入っていないデータを一括で流し込む
        cursor.execute('''
            INSERT INTO images_fts (id, tags_combined)
            SELECT id, tags_combined FROM images 
            WHERE tags_combined IS NOT NULL 
              AND tags_combined != ''
              AND id NOT IN (SELECT id FROM images_fts)
        ''')

        # 3. 今後、新しいタグが保存された時の自動同期トリガー
        # tagger.pyがタグを保存（UPDATE）した瞬間に、この処理が自動で発火する
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS trg_images_update_tags
            AFTER UPDATE OF tags_combined ON images
            WHEN NEW.tags_combined IS NOT NULL AND NEW.tags_combined != ''
            BEGIN
                -- 一旦古いデータを消してから新しいデータを入れる（重複防止）
                DELETE FROM images_fts WHERE id = OLD.id;
                INSERT INTO images_fts(id, tags_combined) VALUES (NEW.id, NEW.tags_combined);
            END;
        ''')
        
        # 4. 画像の削除時にFTS5からも消すトリガー（整合性を保つため）
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS trg_images_delete
            AFTER DELETE ON images
            BEGIN
                DELETE FROM images_fts WHERE id = OLD.id;
            END;
        ''')

        # ブックマーク（保存済みクエリ）管理用のテーブル
        # nameをUNIQUEにして名前の重複を禁止する
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_saved_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                query TEXT NOT NULL,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ベクトルデータ(768次元のfloat32)はBLOB型で保存する
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS style_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                vector_data BLOB NOT NULL,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 翻訳キャッシュ用のテーブルとインデックス
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS translation_cache (
                jp_text TEXT PRIMARY KEY,
                en_text TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_jp_text ON translation_cache(jp_text)')
        
        self.conn.commit()

    def register_images(self, file_data_list):
        #スキャンした画像のパスと保存日時を一括登録
        #file_data_list: [(file_path, file_mtime), (file_path, file_mtime), ...] の形式
        cursor = self.conn.cursor()
        #INSERT OR IGNOREで、新しい画像がフォルダに追加された時だけ登録(重複回避)
        cursor.executemany(
            'INSERT OR IGNORE INTO images (file_path, file_mtime) VALUES (?, ?)',
            file_data_list
        )
        self.conn.commit()

    def get_unprocessed_images(self, target_column):
        #指定した処理がまだ終わっていない画像を取得
        #例: target_column = 'is_processed_vector'
        cursor = self.conn.cursor()
        cursor.execute(f'SELECT id, file_path FROM images WHERE {target_column} = 0 ORDER BY id')
        return cursor.fetchall()

    def update_thumbnail_status(self, image_id, thumbnail_path):
        #サムネイル生成完了の記録
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE images 
            SET thumbnail_path = ?, is_thumbnail_created = 1 
            WHERE id = ?
        ''', (thumbnail_path, image_id))
        self.conn.commit()

    def update_vector_status(self, image_id):
        #CLIPベクトル解析完了の記録
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE images 
            SET is_processed_vector = 1 
            WHERE id = ?
        ''', (image_id,))
        self.conn.commit()

    def update_tags(self, image_id, tags_combined):
        #タガー解析完了と統合タグの記録
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE images 
            SET tags_combined = ?, is_processed_tag = 1 
            WHERE id = ?
        ''', (tags_combined, image_id))
        self.conn.commit()

    # アンサンブルタグ付け用の新しい保存メソッド
    def update_tags_with_scores(self, image_id, tags_combined, tag_scores_dict):
        """
        統合されたタグ名（検索用）と、信頼度スコア（ロジック計算用）を同時に保存する。
        tag_scores_dict は辞書型を受け取り、JSON文字列に変換して保存する。
        """
        cursor = self.conn.cursor()
        
        # 辞書をJSON文字列に変換
        scores_json = json.dumps(tag_scores_dict)
        
        cursor.execute('''
            UPDATE images 
            SET tags_combined = ?, tag_scores = ?, is_processed_tag = 1 
            WHERE id = ?
        ''', (tags_combined, scores_json, image_id))
        self.conn.commit()

    # お気に入りの状態を反転（0⇔1）させる関数
    def toggle_favorite(self, image_id):
        cursor = self.conn.cursor()
        # 現在の状態を取得
        cursor.execute("SELECT is_favorite FROM images WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        
        new_status = 0
        if row:
            # 現在が0なら1に、1なら0に反転させる（row[0]で値を取得）
            current_status = row[0]
            new_status = 1 if current_status == 0 else 0
            
            # データベースを更新
            cursor.execute('''
                UPDATE images 
                SET is_favorite = ? 
                WHERE id = ?
            ''', (new_status, image_id))
            self.conn.commit()
            
        # 切り替え後の状態（1か0）をUI側に返す
        return new_status

    def close(self):
        #安全に接続を閉じる
        self.conn.close()

    def get_image_by_id(self, image_id):
        #指定されたIDの画像データを取得します
        cursor = self.conn.cursor()
        #FAISSのインデックスは0開始、dbのIDは1開始のため、呼び出し側で調整するかここで調整します
        cursor.execute("SELECT * FROM images WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    # お気に入りの画像一覧を取得する関数
    def get_favorite_images(self):
        cursor = self.conn.cursor()
        # お気に入りフラグが1のものを、追加日時（更新日時）が新しい順に取得
        cursor.execute("SELECT * FROM images WHERE is_favorite = 1 ORDER BY file_mtime DESC")
        return [dict(row) for row in cursor.fetchall()]
    


    # -----ブックマーク関連メソッド-----

    def get_bookmark_by_name(self, name):
        """名前でブックマークを取得（UI側での上書き確認ポップアップ判定用）"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM user_saved_queries WHERE name = ?', (name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_bookmark(self, name, query):
        """ブックマークの保存（重複時は上書き、新規時は挿入）"""
        cursor = self.conn.cursor()
        # すでに同じ名前が存在するか確認
        cursor.execute('SELECT id FROM user_saved_queries WHERE name = ?', (name,))
        row = cursor.fetchone()
        
        if row:
            # 既存なら UPDATE (IDを維持しつつ、クエリと時刻を更新)
            cursor.execute('''
                UPDATE user_saved_queries 
                SET query = ?, last_used_at = CURRENT_TIMESTAMP 
                WHERE name = ?
            ''', (query, name))
        else:
            # 新規なら INSERT
            cursor.execute('''
                INSERT INTO user_saved_queries (name, query) 
                VALUES (?, ?)
            ''', (name, query))
        self.conn.commit()

    def get_bookmarks(self, filter_text=""):
        """ブックマーク一覧の取得（フィルターの有無でソート順を動的に変更）"""
        cursor = self.conn.cursor()
        if not filter_text:
            # フィルター空欄：直近で使ったもの（履歴順）
            cursor.execute('SELECT * FROM user_saved_queries ORDER BY last_used_at DESC')
        else:
            # フィルター入力あり：探しやすさ重視（名前順）
            cursor.execute('SELECT * FROM user_saved_queries WHERE name LIKE ? ORDER BY name ASC', (f'%{filter_text}%',))
        return [dict(row) for row in cursor.fetchall()]

    def update_bookmark_usage(self, bookmark_id):
        """検索実行時に呼び出し、使用時刻を最新に更新する"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE user_saved_queries 
            SET last_used_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (bookmark_id,))
        self.conn.commit()

    def delete_bookmark(self, bookmark_id):
        """ブックマークの削除"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM user_saved_queries WHERE id = ?', (bookmark_id,))
        self.conn.commit()

    # ----- 絵柄（スタイル）タグ関連メソッド -----

    def save_style_tag(self, name, vector):
        """絵柄タグの重心ベクトルを保存（重複時は上書き）"""
        cursor = self.conn.cursor()
        
        # NumPy配列をバイナリ(BLOB)に変換
        vector_bytes = vector.astype(np.float32).tobytes()
        
        cursor.execute('SELECT id FROM style_tags WHERE name = ?', (name,))
        row = cursor.fetchone()
        
        if row:
            # 既存なら UPDATE
            cursor.execute('''
                UPDATE style_tags 
                SET vector_data = ?, last_used_at = CURRENT_TIMESTAMP 
                WHERE name = ?
            ''', (vector_bytes, name))
        else:
            # 新規なら INSERT
            cursor.execute('''
                INSERT INTO style_tags (name, vector_data) 
                VALUES (?, ?)
            ''', (name, vector_bytes))
        self.conn.commit()

    def get_style_vector(self, name):
        """名前から絵柄タグの重心ベクトルを取得し、NumPy配列に戻す"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT vector_data FROM style_tags WHERE name = ?', (name,))
        row = cursor.fetchone()
        
        if row:
            # BLOBからNumPy配列に復元
            vector = np.frombuffer(row['vector_data'], dtype=np.float32)
            # FAISSで扱いやすいように次元を (1, 768) に整形して返す
            return vector.reshape(1, -1)
        return None

    def get_all_styles(self):
        """保存されている絵柄タグの一覧を取得（UI表示用）"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, name, last_used_at FROM style_tags ORDER BY last_used_at DESC')
        return [dict(row) for row in cursor.fetchall()]

    def delete_style_tag(self, style_id):
        """絵柄タグの削除"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM style_tags WHERE id = ?', (style_id,))
        self.conn.commit()
        
    def update_style_usage(self, name):
        """検索実行時に呼び出し、使用時刻を最新に更新する"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE style_tags 
            SET last_used_at = CURRENT_TIMESTAMP 
            WHERE name = ?
        ''', (name,))
        self.conn.commit()

    # ----- 翻訳キャッシュ関連メソッド -----

    # 翻訳キャッシュ取得
    def get_cached_translation(self, jp_text):
        cursor = self.conn.cursor()
        cursor.execute("SELECT en_text FROM translation_cache WHERE jp_text = ?", (jp_text,))
        row = cursor.fetchone()
        return row['en_text'] if row else None

    # 翻訳キャッシュ保存
    def save_translation_to_cache(self, jp_text, en_text):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO translation_cache (jp_text, en_text) VALUES (?, ?)", (jp_text, en_text))
        self.conn.commit()



# --- ここから単体テスト用コード ---
if __name__ == "__main__":
    import time
    
    print("=== データベースの単体テストを開始します ===")
    
    # 1. データベースの初期化（この瞬間に index.db が作られます）
    db = ImageDatabase(db_path="data/db/index.db")
    print("データベースに接続し、テーブルの初期化を完了しました。")

    # 2. ダミーデータの登録テスト
    # 現在のUNIXタイムスタンプを取得して、ミリ秒のズレをシミュレートします
    current_time = time.time()
    dummy_data = [
        ("C:/dummy/test_image_1.jpg", current_time),
        ("C:/dummy/test_image_2.jpg", current_time + 0.123)
    ]
    db.register_images(dummy_data)
    print(f"{len(dummy_data)}件のダミー画像を登録しました。")

    # 3. データの取得テスト（辞書型のようにアクセスできるかの確認）
    unprocessed = db.get_unprocessed_images('is_processed_vector')
    print("未処理の画像一覧（ベクトル解析待ち）:")
    for row in unprocessed:
        print(f" - ID: {row['id']}, Path: {row['file_path']}")

    # 4. 安全に閉じる
    db.close()
    print("=== テストが正常に完了しました ===")