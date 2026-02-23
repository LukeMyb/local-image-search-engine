import sqlite3
import os

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
                is_thumbnail_created INTEGER DEFAULT 0,
                is_processed_vector INTEGER DEFAULT 0,
                is_processed_tag INTEGER DEFAULT 0
            )
        ''')

        #未処理画像を瞬時に見つけるためのインデックス
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unprocessed_thumb ON images(is_thumbnail_created)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unprocessed_vector ON images(is_processed_vector)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unprocessed_tag ON images(is_processed_tag)')
        
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