import unicodedata

# カタカナ（ァ〜ヶ、ヽ、ヾ）を対応するひらがな（ぁ〜ゖ、ゝ、ゞ）へ変換するテーブル
_KATAKANA_TO_HIRAGANA = str.maketrans(
    {
        **{chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)},
        chr(0x30FD): chr(0x309D),
        chr(0x30FE): chr(0x309E),
    }
)


def normalize_kana(text: str) -> str:
    """
    ひらがな・カタカナ（半角カナ含む）・大文字小文字の違いを吸収した検索用文字列を返す。
    NFKC正規化で半角カナや結合濁点を統一した後、カタカナをひらがなに変換して小文字化する。
    """
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text).translate(_KATAKANA_TO_HIRAGANA).lower()
