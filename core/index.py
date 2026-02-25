import time
from pathlib import Path
from core.database import ImageDatabase
from PIL import Image, ImageOps

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
            #ファイルであり, かつ拡張子が対象フォーマットに一致するか確認
            if file_path.is_file() and file_path.suffix.lower() in self.valid_extensions:
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



class ThumbnailGenerator:
    def __init__(self, db: ImageDatabase, output_dir="data/thumbnails", size=(360, 360)):
        self.db = db
        self.output_dir = Path(output_dir)
        self.target_size = size  #360x360の正方形
        self.output_dir.mkdir(parents=True, exist_ok=True) #ディレクトリが存在しなければ作成(親ディレクトリも含めて)

    def process_all(self):
        #dbから「サムネ未作成」の画像を検索し, 正方形のサムネイルを一括生成
        unprocessed_list = self.db.get_unprocessed_images('is_thumbnail_created')
        total_count = len(unprocessed_list)
        
        if total_count == 0:
            print("全ての画像のサムネイルは作成済みです")
            return

        print(f"サムネイルの生成を開始します(対象: {total_count}枚)...")
        
        success_count = 0
        
        for i, row in enumerate(unprocessed_list):
            image_id = row['id']
            file_path = Path(row['file_path'])
            
            thumb_filename = f"{image_id}.webp"
            thumb_path = self.output_dir / thumb_filename
            
            try:
                with Image.open(file_path) as img:
                    #RGB式に変換
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    
                    #アスペクト比を維持しつつ, 中央を基準に正方形に切り抜く
                    img = ImageOps.fit(img, self.target_size, method=Image.Resampling.LANCZOS)
                    
                    img.save(thumb_path, "WEBP", quality=80)
                
                self.db.update_thumbnail_status(image_id, str(thumb_path)) #dbにサムネ生成完了を記録
                success_count += 1

            except Exception as e:
                print(f"Error processing {file_path}: {e}")
            
            if (i + 1) % 100 == 0:
                print(f"  ...{i + 1}/{total_count}枚 完了")

        print(f"サムネイル生成完了 成功: {success_count}枚 / 失敗: {total_count - success_count}枚")

# --- ここから単体テスト用コード ---
if __name__ == "__main__":
    # スキャン設定
    TEST_DIR = r"data\images" #画像のディレクトリパス

    print("=== インデックス構築プロセスを開始します ===")
    db = ImageDatabase()
    
    # ステップ1: ファイルスキャン
    print("\n[Step 1] ファイルスキャン実行中...")
    indexer = ImageIndexer(db, TEST_DIR)
    indexer.scan_and_register()
    
    # ステップ2: サムネイル生成
    print("\n[Step 2] サムネイル生成実行中...")
    generator = ThumbnailGenerator(db)
    generator.process_all()
    
    db.close()
    print("\n=== 全プロセス完了 ===")