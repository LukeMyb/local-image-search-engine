import base64
import io
import os
import zlib
import pandas as pd
import requests
from huggingface_hub import hf_hub_download

# WD14 selected_tags.csv (全9,083行) の各行に対応する (category, sub_category) のテーブル定義
# リポジトリ内に具体的なタグ名を一切含めず、行番号とカテゴリーIDの対応のみで再現性を担保する
TAG_CATEGORY_TABLE: tuple[tuple[str, str], ...] = (
    ("body", "body_part"),
    ("body", "chest"),
    ("body", "physique"),
    ("body", "skin"),
    ("character", "character_name"),
    ("character", "trait"),
    ("clothing", "accessory"),
    ("clothing", "bottom"),
    ("clothing", "clothing_state"),
    ("clothing", "legwear"),
    ("clothing", "outfit"),
    ("clothing", "top"),
    ("clothing", "underwear"),
    ("expression_pose", "action"),
    ("expression_pose", "expression"),
    ("expression_pose", "gaze"),
    ("expression_pose", "pose"),
    ("hair_eyes", "eye_color"),
    ("hair_eyes", "eye_state"),
    ("hair_eyes", "hair_color"),
    ("hair_eyes", "hair_style"),
    ("meta", "background"),
    ("meta", "composition"),
    ("meta", "count"),
    ("meta", "meta"),
    ("meta", "rating"),
    ("other", "effect"),
    ("other", "object"),
    ("other", "scene"),
)

# selected_tags.csv の行順序 (0..9082) に対応するカテゴリーID配列 (uint8, zlib + base64圧縮)
_COMPRESSED_CATEGORY_IDS = (
    "eNrtmGt67CjPrrG9kTkYQhzK5kXMf5z7VvUUvp+ruq/uJOUDSM9J/O9///vf+/btp9Ze++97/m2f"
    "v/wnv1HyK58k4trrtx76r2yt12tLv3/t113Zj/Tc8pufrn9/ruvof7m+Mv7eGXty19/fc5wiW1xt"
    "pJpvTX9v8OKXi3I651J+kyznJYp4fjuy/Jw64lreV2lDjreV/JZ65t5Ezv7rcvpMCU76COOZkl1s"
    "F0+tyfur14dNpN80chqtSOy9bT2L257x95tHHCkkObrqGtmd8S/n7Nxxe/n1LXyaunTk/qP5N2iK"
    "6W6pR0lXctNlv39OCddzj1tft8LMzdaUX21X7Ww5HZrTJs7/BSmPk/aMLLu7WGIdfVupa3qeR6Sm"
    "UHyf6azXPFWPzEpFn1fW23+b5qr8Spmjd+N50sf1S6hZaqd+Wmk/Y8lwNdawX01Sb82x0vCjpzvT"
    "JaHLE4qWlGqr3u3rbk8KUesso3V1H5F4XIUllyQ+/+XWbjl96iXHJO1SDfX1XpbW3rKm1aa2ecqe"
    "0jak/0gLWeiIFtE3tVy9Smle3MGmQlnxSbvVxZdbW35rLpJn1U8Nk6eyDfZ3eh2XP9+ZYswzpWtd"
    "PfgmpWz1YvMxS/RJVWpMFMef+3k8MyhV1/QW78vTVkuXW6sWWUIVRtLG8pNrrGdP8vZ8JX+q3LNu"
    "PF3l05PPJbOF5MTdMmrNWfTju3fzL7XU9CotJK/xia6wTun+luZ9aGn2Z39D35L/rB+96U/gKe9k"
    "R02bBM1tdCriS5q7JC1nCZKqvzO7iqKacwtP21cvMwUdIS5ZvfVxrvvkD8VNXycIaq0lGnWFT0xp"
    "ZV99ggJrxiu1VzId89NfjRveDDybPupb/WwfKdJk5POJQ13Rs2c2kNzOlmuf93kLlaPnKT1ney9J"
    "97y7Wz7Pdi7dvddeGpvx5wYuBP7MI9bKNppo0pN65bF7DS1K30GBXsYAMK+l85PS2VdRhOesQpmP"
    "KlOvWhPgHmOjZukuA5yL4/azrEsPoXNcuPaVpLZ1q3a6SMlUKapLqz5/o+V7zXKvfZYGtTWklEPI"
    "pxZtA640/wyuDyxRs1YJ/tUL+mV51m0vWDDQteAWD58Nch3lU3TdUWmX9Ob8zS1+TNEwBx2saXqT"
    "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"
    "59/n3+ff59/n3+ff5//g8/8BgPK3tg=="
)


def build_tag_categories(
    output_path: str = "data/tag_categories.csv",
    model_name: str = "wd-v1-4-moat-tagger-v2",
) -> bool:
    """
    HuggingFace の selected_tags.csv のタグ名リストと、圧縮済みのカテゴリーID配列を結合して
    data/tag_categories.csv を生成する。
    """
    os.makedirs(os.path.dirname(output_path) or "data", exist_ok=True)
    print("タグカテゴリー辞書 (data/tag_categories.csv) を構築中...")

    try:
        repo_id = f"SmilingWolf/{model_name}"
        csv_path = hf_hub_download(repo_id, "selected_tags.csv")
        tags_df = pd.read_csv(csv_path)
        tag_names = tags_df["name"].tolist()

        raw_ids = zlib.decompress(base64.b64decode(_COMPRESSED_CATEGORY_IDS))
        if len(raw_ids) != len(tag_names):
            raise ValueError(
                f"タグ数({len(tag_names)})とカテゴリーID数({len(raw_ids)})が一致しません。"
            )

        rows = []
        for tag_name, cat_id in zip(tag_names, raw_ids):
            cat, sub_cat = TAG_CATEGORY_TABLE[cat_id]
            rows.append(
                {
                    "tag": tag_name,
                    "category": cat,
                    "sub_category": sub_cat,
                }
            )

        out_df = pd.DataFrame(rows)
        out_df.to_csv(output_path, index=False, encoding="utf-8")
        print(f"成功！ {len(out_df)} 件のタグカテゴリー辞書を {output_path} に保存しました。")
        return True
    except Exception as e:
        print(f"[!] タグカテゴリー辞書の構築に失敗しました: {e}")
        return False


def upgrade_to_huge_dictionary():
    os.makedirs("data", exist_ok=True)

    # 10万語規模の機械翻訳版辞書（danbooru-machine-jp.csv）
    url = "https://raw.githubusercontent.com/boorutan/booru-japanese-tag/master/danbooru-machine-jp.csv"

    print("超巨大辞書(10万語)をダウンロード中...")
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[!] ダウンロード失敗: {e}")
        return

    # データ整形
    try:
        # このCSVは「英語タグ, 日本語訳」の形式
        df = pd.read_csv(
            io.StringIO(response.text), header=None, names=["english", "japanese"]
        )

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
            found = new_df[new_df["alias"] == word]
            if not found.empty:
                print(f"  [確認OK]: '{word}' -> '{found.iloc[0]['actual']}'")
            else:
                print(f"  [警告]: '{word}' は見つかりませんでした。")

    except Exception as e:
        print(f"[!] データ処理失敗: {e}")


if __name__ == "__main__":
    upgrade_to_huge_dictionary()
    build_tag_categories()
