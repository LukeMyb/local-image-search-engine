import sqlite3
import os
import shutil
import json
from pathlib import Path
import numpy as np

class ImageDatabase:
    def __init__(self, db_path="data/db/index.db"):
        #データベースへの接続と初期化
        os.makedirs(os.path.dirname(db_path), exist_ok=True) #dbの存在を確認(無ければ生成)

        # FastAPIからのマルチスレッドアクセスを許可し、ロック待機時間を設定
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)

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
                is_favorite INTEGER DEFAULT 0,
                is_deleted INTEGER DEFAULT 0
            )
        ''')

        # 既存DBへの自動マイグレーション（is_deleted カラムが存在しない場合は追加）
        cursor.execute('PRAGMA table_info(images)')
        existing_columns = [row['name'] for row in cursor.fetchall()]
        if 'is_deleted' not in existing_columns:
            cursor.execute('ALTER TABLE images ADD COLUMN is_deleted INTEGER DEFAULT 0')

        #未処理画像を瞬時に見つけるためのインデックス
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unprocessed_thumb ON images(is_thumbnail_created)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unprocessed_vector ON images(is_processed_vector)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unprocessed_tag ON images(is_processed_tag)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_is_deleted ON images(is_deleted)')

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

        # 絵柄検索の軽量化のためのキャッシュテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS style_cache (
                style_name TEXT NOT NULL,
                image_id INTEGER NOT NULL,
                score REAL NOT NULL,
                PRIMARY KEY (style_name, image_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_style_cache_name ON style_cache(style_name)')

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
        # 名前を取得してキャッシュも削除する
        cursor.execute('SELECT name FROM style_tags WHERE id = ?', (style_id,))
        row = cursor.fetchone()
        if row:
            style_name = row['name']
            cursor.execute('DELETE FROM style_cache WHERE style_name = ?', (style_name,))
            
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

    def save_style_cache(self, style_name, results_list):
        """絵柄タグの検索結果（キャッシュ）を保存する"""
        cursor = self.conn.cursor()
        # 古いキャッシュを削除
        cursor.execute('DELETE FROM style_cache WHERE style_name = ?', (style_name,))
        
        # 新しいキャッシュを一括保存
        if results_list:
            # results_list は [{'id': 123, 'match_score': 0.99}, ...] の想定
            data_to_insert = [(style_name, res['id'], res['match_score']) for res in results_list]
            cursor.executemany('''
                INSERT INTO style_cache (style_name, image_id, score)
                VALUES (?, ?, ?)
            ''', data_to_insert)
        self.conn.commit()

    def get_style_cache(self, style_name):
        """保存された絵柄タグの検索結果（キャッシュ）を辞書として取得する"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT image_id, score FROM style_cache WHERE style_name = ?', (style_name,))
        rows = cursor.fetchall()
        # {image_id: score} の辞書を返す
        return {row['image_id']: row['score'] for row in rows}

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

    # ----- クエリキャッシュ関連メソッド -----

    # 検索履歴を保存するメソッド
    def save_search_history(self, query):
        """最新の検索クエリを1件だけ保存する"""
        cursor = self.conn.cursor()
        # 常に最新の1件だけにするため、既存の履歴を削除してから挿入
        cursor.execute("DELETE FROM search_history")
        cursor.execute("INSERT INTO search_history (query) VALUES (?)", (query,))
        self.conn.commit()

    # 前回のクエリを取得するメソッド
    def get_last_query(self):
        """前回の検索クエリを取得する"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT query FROM search_history ORDER BY executed_at DESC LIMIT 1")
        row = cursor.fetchone()
        return row['query'] if row else ""

    # 無限スクロール用 - 複数IDから画像データを一括取得するメソッド

    def get_images_by_ids(self, image_ids: list[int]):
        """
        指定されたIDリストから画像データを取得し、要求されたIDの順序を維持して返す
        """
        if not image_ids:
            return []
        
        cursor = self.conn.cursor()
        # プレースホルダー (?, ?, ?) を作成
        placeholders = ','.join(['?'] * len(image_ids))
        
        # 既存の検索処理に合わせてすべてのカラム(*)を取得
        query = f"SELECT * FROM images WHERE id IN ({placeholders})"
        cursor.execute(query, image_ids)
        rows = cursor.fetchall()
        
        # SQLiteの IN 句は順序を保証しないため、Python側で元の image_ids の順序に並べ直す
        result_dict = {row['id']: dict(row) for row in rows}
        sorted_results = [result_dict[img_id] for img_id in image_ids if img_id in result_dict]
        
        return sorted_results

    # ----- 論理削除（ゴミ箱移動）・復元関連メソッド -----

    def get_trash_path(self, file_path: str) -> str:
        """
        元画像のパス（例: data/images/202409/xxx.jpg）から、
        ディレクトリ階層を維持したゴミ箱パス（例: data/trash/202409/xxx.jpg）を返す
        """
        src_path = Path(file_path)
        try:
            rel_to_images = src_path.relative_to("data/images")
        except ValueError:
            # 万が一 data/images 配下でないパス形式の場合は親フォルダ名＋ファイル名で階層を維持
            rel_to_images = Path(src_path.parent.name) / src_path.name
        return (Path("data/trash") / rel_to_images).as_posix()

    def trash_images(self, image_ids: list[int]) -> list[int]:
        """
        指定されたIDリストの元画像を data/trash/ に階層維持で移動し、
        DBの is_deleted フラグを 1 に更新する（サムネイルとDB解析データは温存）
        """
        if not image_ids:
            return []

        cursor = self.conn.cursor()
        placeholders = ','.join(['?'] * len(image_ids))
        cursor.execute(f"SELECT id, file_path, is_deleted FROM images WHERE id IN ({placeholders})", image_ids)
        rows = cursor.fetchall()

        trashed_ids = []
        for row in rows:
            img_id = row['id']
            src_path = Path(row['file_path'])
            dst_path = Path(self.get_trash_path(row['file_path']))

            try:
                if src_path.exists():
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src_path), str(dst_path))

                if dst_path.exists():
                    cursor.execute("UPDATE images SET is_deleted = 1 WHERE id = ?", (img_id,))
                    trashed_ids.append(img_id)
                else:
                    print(f"警告: 移動対象のファイルが見つかりません (id={img_id}, path={src_path})")
            except Exception as e:
                print(f"論理削除エラー (id={img_id}): {e}")

        self.conn.commit()
        return trashed_ids

    def restore_images(self, image_ids: list[int]) -> list[int]:
        """
        指定されたIDリストの元画像を data/trash/ から data/images/ の元の階層に戻し、
        DBの is_deleted フラグを 0 に更新する
        """
        if not image_ids:
            return []

        cursor = self.conn.cursor()
        placeholders = ','.join(['?'] * len(image_ids))
        cursor.execute(f"SELECT id, file_path, is_deleted FROM images WHERE id IN ({placeholders})", image_ids)
        rows = cursor.fetchall()

        restored_ids = []
        for row in rows:
            img_id = row['id']
            dst_path = Path(row['file_path'])
            src_path = Path(self.get_trash_path(row['file_path']))

            try:
                if src_path.exists():
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src_path), str(dst_path))
                    # 移動後に data/trash/ 側のサブフォルダが空になったら片付ける
                    try:
                        if src_path.parent != Path("data/trash") and not any(src_path.parent.iterdir()):
                            src_path.parent.rmdir()
                    except OSError:
                        pass

                if dst_path.exists():
                    cursor.execute("UPDATE images SET is_deleted = 0 WHERE id = ?", (img_id,))
                    restored_ids.append(img_id)
                else:
                    print(f"警告: 復元対象のファイルが見つかりません (id={img_id}, trash_path={src_path})")
            except Exception as e:
                print(f"復元エラー (id={img_id}): {e}")

        self.conn.commit()
        return restored_ids

# --- ここから単体テスト用コード ---
if __name__ == "__main__":
    import sys

    print("=== データベースの論理削除・復元テスト ===")
    db = ImageDatabase(db_path="data/db/index.db")

    cursor = db.conn.cursor()
    cursor.execute("PRAGMA table_info(images)")
    cols = [r["name"] for r in cursor.fetchall()]
    print(f"1. imagesテーブルのカラム確認: {'is_deleted' in cols} (columns: {cols})")

    # コマンドライン引数:
    #   python -m core.database trash <id>    -> 指定IDを論理削除（data/trash へ移動）
    #   python -m core.database restore <id>  -> 指定IDを復元（data/images へ戻す）
    #   引数なし                              -> 先頭1件を使って自動で「論理削除 -> 復元」の往復テストを実行
    if len(sys.argv) >= 3 and sys.argv[1] in ("trash", "restore"):
        action = sys.argv[1]
        target_id = int(sys.argv[2])
        if action == "trash":
            res = db.trash_images([target_id])
            row = db.get_image_by_id(target_id)
            trash_p = db.get_trash_path(row["file_path"]) if row else ""
            print(f"[trash完了] ID={res}, is_deleted={row['is_deleted'] if row else None}")
            print(f"  元パス実在: {os.path.exists(row['file_path'])}, trashパス実在({trash_p}): {os.path.exists(trash_p)}")
        else:
            res = db.restore_images([target_id])
            row = db.get_image_by_id(target_id)
            trash_p = db.get_trash_path(row["file_path"]) if row else ""
            print(f"[restore完了] ID={res}, is_deleted={row['is_deleted'] if row else None}")
            print(f"  元パス実在({row['file_path']}): {os.path.exists(row['file_path'])}, trashパス実在: {os.path.exists(trash_p)}")
    else:
        cursor.execute("SELECT id, file_path FROM images WHERE is_deleted = 0 LIMIT 1")
        sample = cursor.fetchone()
        if sample:
            test_id = sample["id"]
            orig_path = sample["file_path"]
            trash_path = db.get_trash_path(orig_path)
            print(f"\n2. サンプル画像 (ID={test_id}) で往復テストを実行します")
            print(f"   元パス  : {orig_path}")
            print(f"   Trash先 : {trash_path}")

            # 論理削除
            db.trash_images([test_id])
            after_trash = db.get_image_by_id(test_id)
            print(f"\n[Step A: trash_images 実行後]")
            print(f"   DB is_deleted       : {after_trash['is_deleted']}")
            print(f"   data/images に存在? : {os.path.exists(orig_path)}")
            print(f"   data/trash  に存在? : {os.path.exists(trash_path)}")
            print(f"   サムネイル温存?     : {os.path.exists(after_trash['thumbnail_path'])}")

            # 復元
            db.restore_images([test_id])
            after_restore = db.get_image_by_id(test_id)
            print(f"\n[Step B: restore_images 実行後]")
            print(f"   DB is_deleted       : {after_restore['is_deleted']}")
            print(f"   data/images に存在? : {os.path.exists(orig_path)}")
            print(f"   data/trash  に存在? : {os.path.exists(trash_path)}")
            print(f"   タグ情報の温存確認  : {bool(after_restore['tags_combined'])}")
        else:
            print("テスト対象の画像がDBに登録されていません。")

    db.close()
    print("\n=== テストが正常に完了しました ===")
