import requests
import pandas as pd
import io
import os

def upgrade_to_huge_dictionary():
    os.makedirs("data", exist_ok=True)
    
    # 10万語規模の機械翻訳版辞書（danbooru-machine-jp.csv）
    url = "https://raw.githubusercontent.com/boorutan/booru-japanese-tag/master/danbooru-machine-jp.csv"
    
    print(f"超巨大辞書(10万語)をダウンロード中...")
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[!] ダウンロード失敗: {e}")
        return

    # データ整形
    try:
        # このCSVは「英語タグ, 日本語訳」の形式
        df = pd.read_csv(io.StringIO(response.text), header=None, names=["english", "japanese"])
        
        aliases = []
        for _, row in df.iterrows():
            eng = str(row["english"]).strip()
            # 日本語訳が複数ある場合は分割して登録
            japs = str(row["japanese"]).split(",")
            for j in japs:
                aliases.append({"alias": j.strip(), "actual": eng})

        # 重複を削除して保存
        new_df = pd.DataFrame(aliases).drop_duplicates()
        new_df.to_csv("data/tag_aliases.csv", index=False, encoding="utf-8")
        
        print(f"成功！ {len(new_df)} 件の俗語・専門用語がインストールされました。")
        # 特定の単語が含まれているかテスト
        test_words = ["黒髪", "ロングヘア", "ニーソックス"]
        for word in test_words:
            found = new_df[new_df['alias'] == word]
            if not found.empty:
                print(f"  [確認OK]: '{word}' -> '{found.iloc[0]['actual']}'")
            else:
                print(f"  [警告]: '{word}' は見つかりませんでした。")

    except Exception as e:
        print(f"[!] データ処理失敗: {e}")

if __name__ == "__main__":
    upgrade_to_huge_dictionary()