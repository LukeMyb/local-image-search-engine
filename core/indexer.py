import time
from pathlib import Path
from core.database import ImageDatabase

class ImageIndexer:
    def __init__(self, db: ImageDatabase, target_dir: str):
        self.db = db
        self.target_dir = Path(target_dir) #文字列のパスを、操作が便利なPathオブジェクトに変換
        self.valid_extensions = {'.jpg', '.jpeg', '.png', '.webp'} #スキャン対象とする画像フォーマットの定義

    def scan_and_register(self):
        #指定フォルダを再帰的に巡回し, 画像パスと保存日時をDBに一括登録
        if not self.target_dir.exists():
            print(f"エラー: 指定されたディレクトリが存在しません -> {self.target_dir}")
            return

        print(f"スキャン開始: {self.target_dir}")
        start_time = time.time()
        
        file_data_list = []
        count = 0

        for file_path in self.target_dir.rglob('*'): #rglob('*')はサブフォルダの中身も含めて全ファイルを探索
            if file_path.is_file() and file_path.suffix.lower() in self.valid_extensions: #ファイルであり, かつ拡張子が対象フォーマットに一致するか確認
                abs_path = str(file_path.resolve()) #絶対パスを取得
                mtime = file_path.stat().st_mtime #OSからミリ秒精度の更新日時(UNIXタイムスタンプ)を取得
                
                #DB登録用にタプルとしてリストに追加
                file_data_list.append((abs_path, mtime))
                count += 1
                
                #1万枚ごとに進捗を表示
                if count % 10000 == 0:
                    print(f"  ...{count}枚の画像を検出しました")

        # リストに貯めたデータをDBへ一括登録
        if file_data_list:
            print(f"データベースへの一括登録を開始します(対象: {len(file_data_list)}件)...")
            #database.py で設定した「INSERT OR IGNORE」により,
            #2回目以降の実行では「新しく追加された画像だけ」が登録される
            self.db.register_images(file_data_list)
        
        elapsed_time = time.time() - start_time
        print(f"スキャンと登録が完了しました！ (合計: {count}枚, 処理時間: {elapsed_time:.2f}秒)")

# --- ここから単体テスト用コード ---
if __name__ == "__main__":
    # テスト用の画像フォルダパスを指定します
    # Windowsのパスをそのまま貼る場合、文字列の前に r を付けるとエラー（エスケープ文字の誤爆）を防げます
    TEST_DIR = r"C:\Users\Admin\Pictures\iphone"  # ※あなたの実際の画像フォルダのパスに書き換えてください

    print("=== インデクサー（スキャナー）の単体テストを開始します ===")
    
    # データベースを開く
    db = ImageDatabase()
    
    # インデクサーを準備して実行
    indexer = ImageIndexer(db, TEST_DIR)
    indexer.scan_and_register()
    
    # DBに登録されたか確認
    unprocessed = db.get_unprocessed_images('is_processed_vector')
    print(f"現在DBに登録されている処理待ち（ベクトル未解析）画像数: {len(unprocessed)}枚")
    
    db.close()