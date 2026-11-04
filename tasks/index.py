import time
import datetime
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
        active_paths = set()
        count = 0

        for file_path in self.target_dir.rglob('*'): #rglob('*')はサブフォルダの中身も含めて全ファイルを探索
            #ファイルであり, かつ拡張子が対象フォーマットに一致するか確認
            if file_path.is_file() and file_path.suffix.lower() in self.valid_extensions:
                #相対パスのまま、スラッシュ区切り(/)の美しいフォーマットで取得
                rel_path = file_path.as_posix()
                
                mtime = file_path.stat().st_mtime #OSからミリ秒精度の更新日時(UNIXタイムスタンプ)を取得
                
                #DB登録用にタプルとしてリストに追加
                file_data_list.append((rel_path, mtime))
                active_paths.add(rel_path)
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

        # 3状態（data/images・data/trash・完全削除）の自動追従同期を実行
        self.sync_filesystem_states(active_paths)
        
        elapsed_time = time.time() - start_time
        print(f"スキャンと同期が完了しました！ (有効画像: {count}枚, 処理時間: {elapsed_time:.2f}秒)")

    def sync_filesystem_states(self, active_paths: set[str]):
        """
        DB内の全レコードとディスク上の実在ファイル（data/images および data/trash）を照合し、
        以下の3状態を自動同期する：
          状態① data/images に実在する -> is_deleted = 0（以前1なら自動復元）
          状態② data/trash  に実在する -> is_deleted = 1（以前0なら論理削除に更新）
          状態③ どちらにも存在しない   -> 完全削除（サムネイル・DB・FAISSから自動消去）
        """
        print("ファイルシステムとの3状態同期を実行中...")
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT id, file_path, is_deleted FROM images")
        rows = cursor.fetchall()

        restored_ids = []
        trashed_ids = []
        purged_ids = []

        for row in rows:
            img_id = row['id']
            file_path = row['file_path']
            is_deleted = row['is_deleted']

            if file_path in active_paths:
                # 状態①: data/images に存在する
                if is_deleted == 1:
                    restored_ids.append(img_id)
            else:
                # data/images に無い場合、data/trash 側にあるか確認
                trash_path = Path(self.db.get_trash_path(file_path))
                if trash_path.exists():
                    # 状態②: data/trash に存在する
                    if is_deleted == 0:
                        trashed_ids.append(img_id)
                else:
                    # 状態③: data/images にも data/trash にも存在しない（完全削除対象）
                    purged_ids.append(img_id)

        chunk_size = 900
        if restored_ids:
            for i in range(0, len(restored_ids), chunk_size):
                chunk = restored_ids[i:i + chunk_size]
                placeholders = ','.join(['?'] * len(chunk))
                cursor.execute(f"UPDATE images SET is_deleted = 0 WHERE id IN ({placeholders})", chunk)
            self.db.conn.commit()
            print(f"  -> [自動復元] data/images に戻された {len(restored_ids)}件 の画像を復元しました（再計算なし）。")

        if trashed_ids:
            for i in range(0, len(trashed_ids), chunk_size):
                chunk = trashed_ids[i:i + chunk_size]
                placeholders = ','.join(['?'] * len(chunk))
                cursor.execute(f"UPDATE images SET is_deleted = 1 WHERE id IN ({placeholders})", chunk)
            self.db.conn.commit()
            print(f"  -> [自動論理削除] data/trash に移動された {len(trashed_ids)}件 の画像をゴミ箱状態に更新しました。")

        if purged_ids:
            print(f"  -> [ゴースト・完全削除検知] どちらのフォルダにも存在しない {len(purged_ids)}件 のデータをクリーンアップします...")
            self.db.purge_images(purged_ids)

        # data/trash 内の空になったサブフォルダがあれば掃除する
        trash_root = Path("data/trash")
        if trash_root.exists():
            for sub in sorted(trash_root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                if sub.is_dir():
                    try:
                        if not any(sub.iterdir()):
                            sub.rmdir()
                    except OSError:
                        pass

        if not restored_ids and not trashed_ids and not purged_ids:
            print("  -> 状態の変更やゴーストデータはありませんでした。")



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
        start_time = time.time() # ループ開始のタイムスタンプを記録
        
        for i, row in enumerate(unprocessed_list):
            image_id = row['id']
            src_rel_path = Path(row['file_path'])
            
            # ファイル名に _thumb を付与
            folder_name = src_rel_path.parent.name
            thumb_rel_path = Path(folder_name) / f"{src_rel_path.stem}_thumb.webp"
            thumb_path = self.output_dir / thumb_rel_path

            # サブディレクトリが存在しない場合は作成
            thumb_path.parent.mkdir(parents=True, exist_ok=True)

            # 実際に重い画像を開く前に、物理ファイルが存在するかチェック
            if thumb_path.exists():
                # ファイルが既にあるなら、DBのフラグだけ「完了」にして即スキップ
                self.db.update_thumbnail_status(image_id, str(thumb_path))
                success_count += 1
            else:
                try:
                    with Image.open(src_rel_path) as img:
                        #RGB式に変換
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        #アスペクト比を維持しつつ, 中央を基準に正方形に切り抜く
                        img = ImageOps.fit(img, self.target_size, method=Image.Resampling.LANCZOS)

                        img.save(thumb_path, "WEBP", quality=80)
                    
                    self.db.update_thumbnail_status(image_id, str(thumb_path)) #dbにサムネ生成完了を記録
                    success_count += 1

                except Exception as e:
                    print(f"Error processing {src_rel_path}: {e}")
            
            # 1000件処理するごとに途中経過と予測時刻を計算して出力
            if (i + 1) % 1000 == 0:
                current_count = i + 1
                elapsed_time = time.time() - start_time
                time_per_file = elapsed_time / current_count
                remaining_time_sec = time_per_file * (total_count - current_count)
                remaining_td = datetime.timedelta(seconds=int(remaining_time_sec))
                eta_time = datetime.datetime.now() + remaining_td
                eta_str = eta_time.strftime("%H:%M:%S")

                print(f"進捗: {current_count} / {total_count} 件 ... 残り時間: 約 {remaining_td} (終了予定: {eta_str})")

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
