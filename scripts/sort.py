import os
import shutil # ファイルコピーおよびメタデータ維持用
import datetime
import time
import hashlib # ハッシュ値計算用
from pathlib import Path

# 元のTARGET_DIRを「読み込み元」と「保存先」に分割
SOURCE_DIR = r"data\images" # 大元のフォルダ
TARGET_DIR = r"data\sorted"     # 新しく作成してコピーする先のフォルダ
BATCH_SIZE = 1000  # 1ディレクトリあたりの最大枚数

# ファイルのハッシュ値を計算する関数（先頭8文字を使用）
def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        # メモリを節約しつつ高速に読み込むため、細かく分割して処理
        for chunk in iter(lambda: f.read(65536), b''):
            hasher.update(chunk)
    return hasher.hexdigest()[:8]

def copy_and_distribute_photos():
    source_base_path = Path(SOURCE_DIR)
    target_base_path = Path(TARGET_DIR)
    
    # 対象となる画像ファイルの拡張子
    valid_extensions = {'.jpg', '.jpeg', '.png', '.heic'}
    
    # rglob('*') を使用し、SOURCE_DIR内のすべてのサブフォルダを奥深くまで再帰的にスキャン
    files = [f for f in source_base_path.rglob('*') if f.is_file() and f.suffix.lower() in valid_extensions]

    # 全サブフォルダから集めたファイルを「更新日時」順にソート（古い順）
    files.sort(key=lambda x: x.stat().st_mtime)

    total_files = len(files) # 進捗表示のために全ファイル数を事前に取得
    success_count = 0
    start_time = time.time() # ループ開始のタイムスタンプを記録

    for i, file_path in enumerate(files):
        # 1000件処理するごとに途中経過をコンソールに出力
        if (i + 1) % 1000 == 0:
            current_count = i + 1
            elapsed_time = time.time() - start_time # 経過時間（秒）
            
            # 1件あたりの平均処理速度から、残り時間を計算
            time_per_file = elapsed_time / current_count
            remaining_files = total_files - current_count
            remaining_time_sec = time_per_file * remaining_files
            
            # 秒数を HH:MM:SS 形式に変換
            remaining_td = datetime.timedelta(seconds=int(remaining_time_sec))
            
            # 現在時刻に残り時間を足して、終了予定時刻を算出
            eta_time = datetime.datetime.now() + remaining_td
            eta_str = eta_time.strftime("%H:%M:%S")

            print(f"進捗: {current_count} / {total_files} 件 ... 残り時間: 約 {remaining_td} (終了予定: {eta_str})")

        # フォルダ番号の計算
        folder_num = (i // BATCH_SIZE) + 1
        sub_dir_name = f"{folder_num:03d}"
        dest_dir = target_base_path / sub_dir_name
        
        # フォルダがなければ作成
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 更新日時をタイムスタンプとして取得
        mtime = file_path.stat().st_mtime
        dt = datetime.datetime.fromtimestamp(mtime)
        
        # ファイル名作成
        file_hash = get_file_hash(file_path) # ハッシュ値を取得してファイル名に組み込む
        date_str = dt.strftime("%Y%m%d_%H%M%S")
        new_name = f"{date_str}_{file_hash}{file_path.suffix.lower()}"
        new_path = dest_dir / new_name

        # copy2 (メタデータを維持したコピー) 
        try:
            if not new_path.exists():
                shutil.copy2(file_path, new_path)
                success_count += 1
            else:
                print(f"重複スキップ: {new_name} は既に存在します")
        except Exception as e:
            print(f"エラー発生 ({file_path.name}): {e}")

    print(f"処理完了: {success_count} 件のファイルをコピーし、{sub_dir_name} までのフォルダに整理しました。")

if __name__ == "__main__":
    copy_and_distribute_photos()