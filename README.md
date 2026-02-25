# Local Image Search Engine

DanbooruタグとCLIPモデル（AI）を組み合わせた、ローカル画像検索エンジン。
10万語以上のタグ辞書とベクトル検索により、日本語の俗語でも高精度に検索可能。

## 動作環境
- Python 3.10+
- PyTorch (CPU版でも動作可、GPU推奨)
- 必須ライブラリ: `torch`, `transformers`, `faiss-cpu`, `pandas`, `deep_translator`, `Pillow` 等

## セットアップ手順

### 1. 仮想環境の有効化
```bash
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

辞書データの準備（初回のみ）
以下のスクリプトを実行して、10万語規模のタグ翻訳辞書 (data/tag_aliases.csv) をダウンロードする。
python download_assets.py

テスト時の実行順番
database.pyは実行不要

index.py(データベースとサムネイルを生成)
  ├─vectorize_tags.py(moatのタグ全種類をベクトル化)
  |   ├─tagger.py(画像のタグを抽出)
  |   ├─download_assets.py(俗語の(日本語⇒タグ)対応表をダウンロード)
  |   └─tag_search.py(検索クエリを対応表でタグに変換もしくは翻訳でタグとコサイン類似度を比較して最も近いタグを複数展開⇒これらをスコアリングして出力)
  └─vectorize_images.py(画像をベクトル化)
      └─clip_search.py(検索クエリと画像のベクトルを比較して検索) ←あんまりうまくいかない