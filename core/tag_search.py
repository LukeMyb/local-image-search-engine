import faiss
import torch
import pandas as pd
import numpy as np
import re
import os
import json
import math
import torch_directml #DirectML用のプラグイン
from huggingface_hub import hf_hub_download
from transformers import CLIPProcessor, CLIPModel
import translators as ts
from core.database import ImageDatabase
from core.style_search import StyleSearcher

class TagSearch:
    def __init__(self, db_path="data/db/index.db", tag_index_path="data/tag_vector_index.bin"):
        self.db = ImageDatabase(db_path)
        
        #CUDA/CPUの判定を削除し、DirectMLを強制的に割り当てる
        self.device = torch_directml.device()
        print(f"  [System] Device: {self.device} (DirectML)")

        # 絵柄検索エンジンのロード（app.pyと共有してVRAM二重消費を防ぐ）
        try:
            self.style_engine = StyleSearcher(self.db)
        except Exception as e:
            print(f"  [System] 絵柄検索エンジンのロードに失敗しました: {e}")
            self.style_engine = None
        
        #モデルロード
        model_id = "openai/clip-vit-base-patch32"

        #transformersライブラリの過剰なセキュリティブロックを強制的に黙らせるパッチ
        from transformers import modeling_utils
        from transformers.utils import import_utils
        if hasattr(modeling_utils, 'check_torch_load_is_safe'):
            modeling_utils.check_torch_load_is_safe = lambda: None
        if hasattr(import_utils, 'check_torch_load_is_safe'):
            import_utils.check_torch_load_is_safe = lambda: None

        #脆弱性エラーを回避するため、安全な safetensors 形式で読み込むように指定
        self.model = CLIPModel.from_pretrained(model_id, use_safetensors=False, local_files_only=True).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_id, local_files_only=True)
        
        #タグインデックスロード
        self.tag_index = faiss.read_index(tag_index_path)
        
        #タグ名リストロード
        repo_id = "SmilingWolf/wd-v1-4-moat-tagger-v2"
        csv_path = hf_hub_download(repo_id, "selected_tags.csv", local_files_only=True)
        self.tag_list = pd.read_csv(csv_path)["name"].tolist()

        #辞書ロード (10万語 + 手動修正)
        self.alias_map = self._load_all_aliases()

        #DB内タグのオンメモリ集計 (追加)
        self._build_tag_counts()

    def _load_all_aliases(self):
        """10万語辞書と手動辞書を統合してロード"""
        combined = {}
        # 読み込む順番: 10万語(tag_aliases) -> 手動(manual_alias)
        paths = ["data/tag_aliases.csv", "data/manual_alias.csv"]
        
        print(f"  [System] Loading dictionaries...")
        for path in paths:
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    count = 0
                    for k, v in zip(df['alias'], df['actual']):
                        # 全て小文字、スペースをアンダースコアに統一
                        key = str(k).strip().lower().replace(' ', '_')
                        val = str(v).strip().lower().replace(' ', '_')
                        combined[key] = val
                        count += 1
                    print(f"    - Loaded {count} entries from {path}")
                except Exception as e:
                    print(f"    [!] Failed to load {path}: {e}")
        return combined
    
    def _build_tag_counts(self):
        """DB内の全画像から存在するタグとその件数を集計してメモリに保持する"""
        self.tag_counts = {}
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT tags_combined FROM images")

        # 全画像数をカウントして保持する
        rows = cursor.fetchall()
        self.total_images = len(rows)
        
        # 上で取得したrowsを回す
        for row in rows:
            tags_str = row[0]
            if not tags_str: continue
            
            # コンマ区切りのタグを処理してカウント
            tags = [t.strip().lower() for t in tags_str.split(',')]
            for t in tags:
                self.tag_counts[t] = self.tag_counts.get(t, 0) + 1
                
        print(f"  [System] Cached {len(self.tag_counts)} unique tags from DB.")

    def get_suggestions(self, query_text, limit=10):
        """入力された文字列からヒットするサジェスト候補を返す"""
        if not query_text: return []
        
        # 入力文字列（スペースとアンダースコア両方対応できるようにする）
        prefix = query_text.lower().strip()
        prefix_under = prefix.replace(' ', '_')

        candidates = []
        
        # 1. 実際のタグ（DBに存在するタグ）からの検索
        for tag, count in self.tag_counts.items():
            # DB内のタグ（スペース区切りの場合がある）をアンダースコア区切りに変換
            underscored_tag = tag.replace(' ', '_')
            
            # 入力文字列がスペースでもアンダースコアでもヒットするように判定
            if prefix in tag or prefix_under in underscored_tag:
                candidates.append({
                    "display": f"{underscored_tag} ({count}件)", # UI表示用(アンダースコア付き)
                    "query": underscored_tag,                    # クリック時入力(アンダースコア付き)
                    "count": count
                })
                
        # 2. 俗語（Alias辞書）からの検索
        for alias, actual in self.alias_map.items():
            norm_actual = actual.replace('_', ' ')
            
            # alias_map はすでにアンダースコア区切りになっている
            if (prefix_under in alias) and norm_actual in self.tag_counts:
                count = self.tag_counts[norm_actual]
                candidates.append({
                    "display": f"{alias} -> {actual} ({count}件)", 
                    "query": alias, 
                    "count": count
                })
                
        # 重複を消して、ヒット件数が多い順にソート
        unique_candidates = {}
        for c in candidates:
            key = c["display"]
            if key not in unique_candidates or unique_candidates[key]["count"] < c["count"]:
                unique_candidates[key] = c
                
        sorted_results = sorted(unique_candidates.values(), key=lambda x: x["count"], reverse=True)
        return sorted_results[:limit]

    def query_to_vector(self, text):
        inputs = self.processor(text=[text], return_tensors="pt", padding=True).to(self.device)
        with torch.no_grad():
            output = self.model.get_text_features(**inputs)
        
        if isinstance(output, torch.Tensor):
            vec = output
        elif hasattr(output, "text_embeds"):
            vec = output.text_embeds
        elif hasattr(output, "pooler_output"):
            vec = output.pooler_output
        else:
            raise ValueError(f"Unknown output type: {type(output)}")

        vec = vec / vec.norm(p=2, dim=-1, keepdim=True)
        return vec.cpu().numpy().astype('float32')

    def _check_alias_or_list(self, word):
        """
        単語がAlias辞書にあるか、あるいは直接タグリストにあるかを確認する
        戻り値: (変換後のタグ名, ヒットしたかどうか)
        """
        # 正規化
        key = word.strip().lower().replace(' ', '_')
        
        # 1. Alias辞書を最優先
        if key in self.alias_map:
            actual_tag = self.alias_map[key]
            # 変換先がタグリストに存在するか確認
            if actual_tag in self.tag_list:
                return actual_tag, True
        
        # 2. 直接タグリストにあるか確認
        if key in self.tag_list:
            return key, True
            
        return key, False

    def find_similar_tags_with_score(self, word, top_k=25): 
        # --- Step 1: 初期入力でチェック ---
        english_word, found = self._check_alias_or_list(word) #foundはAlias辞書もしくはタグリストに検索ワードが存在するか
        if found:
            print(f"  ├─ [Direct/Alias Hit]: {word} -> {english_word}")
            return english_word, {english_word: 1.0}

        # --- Step 2: Google翻訳 ---
        try:
            translated_g = ts.translate_text(word, translator='google', to_language='en')
            # 翻訳結果を再度Alias辞書・リストで確認
            english_word, found = self._check_alias_or_list(translated_g)
            if found:
                print(f"  ├─ [Google -> Alias/List]: {word} -> {english_word}")
                return english_word, {english_word: 1.0}
        except Exception as e:
            print(f"  [!] Google Translate Error: {e}")

        # --- Step 3: Bing翻訳 ---
        translated_b = ""
        try:
            translated_b = ts.translate_text(word, translator='bing', to_language='en')
            #まずは辞書・リストにあるか確認
            english_word, found = self._check_alias_or_list(translated_b)
            if found:
                print(f"  ├─ [Bing -> Alias/List]: {word} -> {english_word}")
                return english_word, {english_word: 1.0}
        except Exception as e:
            print(f"  [!] Bing Translate Error: {e}")

        # --- Step 4: CLIPベクトル検索 (最終手段) ---
        #Bing翻訳の結果があればそれを使用し、なければGoogle翻訳や元の単語をフォールバックにする
        final_query = translated_b if translated_b else (translated_g if 'translated_g' in locals() else word)
        print(f"  ├─ [Vector Search]: Using query '{final_query}'")

        found_tags_map = {} 

        # ★追加：翻訳された単語を使って、キャラ名_(作品名) などのタグを前方一致で直接救済する
        norm_final = final_query.lower().replace(' ', '_')
        prefix_search = f"{norm_final}_("
        text_match_count = 0

        for t in self.tag_list:
            # 完全一致、または「キャラ名_(」で始まるタグをリストから探す
            if t == norm_final or t.startswith(prefix_search):
                found_tags_map[t] = 1.0
                text_match_count += 1
                
        if text_match_count > 0:
            print(f"  ├─ [Text Match Hit]: Found {text_match_count} tags matching '{norm_final}' or '{prefix_search}...'")

        # ベクトル比較 (CLIP)
        query_vec = self.query_to_vector(final_query)
        distances, indices = self.tag_index.search(query_vec, top_k)
        
        #クエリ自体がもしタグリストにあるなら、スコア1.0で追加
        norm_final = final_query.lower().replace(' ', '_')
        if norm_final in self.tag_list:
            found_tags_map[norm_final] = 1.0

        query_has_size = self.has_size_modifier(final_query)

        for i, idx in enumerate(indices[0]):
            score = float(distances[0][i])
            tag_name = self.tag_list[idx]
            
            if self.check_conflict(english_word, tag_name): continue
            if query_has_size and not self.has_size_modifier(tag_name): continue

            if score > 0.90:
                found_tags_map[tag_name] = max(found_tags_map.get(tag_name, 0), score)
        
        return final_query, found_tags_map

    def get_size_modifiers(self):
        return ["small", "flat", "tiny", "little", "mini", "short", "low",
                "big", "large", "huge", "giant", "massive", "gigantic", "enormous", 
                "long", "tall", "high", "hyper", "absurd"]

    def has_size_modifier(self, text):
        modifiers = self.get_size_modifiers()
        return any(m in text.lower() for m in modifiers)

    def check_conflict(self, query_translated, tag_name):
        #アンダースコアをスペースに統一して、より確実に単語を比較できるようにする
        q = query_translated.lower().replace('_', ' ')
        t = tag_name.lower().replace('_', ' ')

        big = ["big", "large", "huge", "giant", "massive", "gigantic"]
        small = ["small", "flat", "tiny", "little"]
        if any(w in q for w in big) and any(w in t for w in small): return True
        if any(w in q for w in small) and any(w in t for w in big): return True

        return False

    def calculate_image_score_with_details(self, image_tags_str, search_groups, parsed_tag_scores):
        total_score = 0.0
        matched_details = []
        if not image_tags_str: return 0.0, []
        
        # タグの正規化（小文字、スペース統一）
        img_tags = {t.strip().lower().replace('_', ' ') for t in image_tags_str.split(',')}

        # ★変更: ORグループごとにループを回し、そのグループ内で一番高いスコアだけを採用する
        for group_map in search_groups:
            group_max_score = 0.0
            best_match_detail = None
        
            for search_tag, sim_score in group_map.items():
                norm_search_tag = search_tag.lower().replace('_', ' ')
                if norm_search_tag in img_tags:
                    # 要素A：類似度のペナルティ係数（5乗）
                    sim_weight = sim_score ** 5
                    
                    # 要素B：AI確信度のマイルド化（平方根）
                    # JSONからタグの確信度を取得（見つからない場合は最低閾値0.35を仮置き）
                    ai_conf = parsed_tag_scores.get(norm_search_tag, 0.35)
                    ai_weight = math.sqrt(ai_conf)
                    
                    # 要素C：希少性（IDF）の計算（常用対数＋最低10回の足切り）
                    db_count = self.tag_counts.get(norm_search_tag, 0)
                    total_imgs = max(self.total_images, 1) # 0割り防止
                    idf_weight = math.log10(total_imgs / max(db_count, 10))
                    
                    # 最終的な単語スコアを算出(クエリとタグの類似度 * タグの信頼度 * タグの希少性)
                    final_word_score = sim_weight * ai_weight * idf_weight

                    # このグループ内で過去最高のスコアであれば更新する
                    if final_word_score > group_max_score:
                        group_max_score = final_word_score
                        best_match_detail = {
                            "tag": norm_search_tag,
                            "final": final_word_score,
                            "sim": sim_weight,
                            "ai": ai_weight,
                            "idf": idf_weight
                        }

            # グループ内で最も高かった単語のスコア1つだけを加算リストに入れる
            if best_match_detail:
                total_score += group_max_score
                matched_details.append(best_match_detail)
                
        return total_score, matched_details

    def search(self, user_query, is_bookmarked=False):
        # ★追加: 絵柄タグ(style:xxx)の抽出と分離処理
        style_match = re.search(r'style:([^\s|]+)', user_query)
        style_name = None
        style_scores_map = {}
        
        if style_match:
            style_name = style_match.group(0) # 例: "style:A"
            # クエリ文字列から "style:A" を取り除いて前後の空白を消す（残りのタグを抽出）
            user_query = user_query.replace(style_name, '').strip()
            
            if self.style_engine is None:
                print("エラー: 絵柄検索エンジンが起動していません。")
                return []
                
            print(f"\n{'='*60}")
            print(f" Style Search: '{style_name}'")
            print(f"{'='*60}")
            
            # FAISSで絵柄検索を実行 (ユーザー指定の閾値0.98で足切り)
            # ※ここで style_search.py 側の search_by_style_name の threshold が機能します
            style_results = self.style_engine.search_by_style_name(style_name, threshold=0.98)
            
            # 高速なAND判定のために、見つかった画像IDとスコアを辞書(Map)にしておく
            style_scores_map = {res['id']: res['match_score'] for res in style_results}
            
            # もし「style:A」以外に何も入力されていなければ、ここで結果を返して終了（パターン1）
            if not user_query:
                if is_bookmarked:
                    style_results.sort(key=lambda x: (x.get('is_favorite', 0), x['match_score'], x['file_mtime']), reverse=True)
                else:
                    style_results.sort(key=lambda x: (x['match_score'], x['file_mtime']), reverse=True)
                return style_results
                
            # もし絵柄検索で1件もヒットしなければ、AND検索の結果も確実に0件なので即終了
            if not style_scores_map:
                print("  -> 絵柄に一致する画像が0件のため、検索を終了します。")
                return []
                
            print(f"  -> 絵柄検索で {len(style_scores_map)}件 ヒット。続けてタグ検索で絞り込みます...")
        


        # | (パイプ記号) の前後の空白を詰め、純粋な | だけに統一する
        # これにより "A | B" も "A|B" として扱われ、後続の空白分割で千切れるのを防ぐ
        query = re.sub(r'\s*\|\s*', '|', user_query)

        words = re.split(r'[ \u3000,]+', query)
        words = [w for w in words if w]
        if not words: return []

        # プラス検索とマイナス検索（除外）に単語を振り分ける
        positive_groups = []
        negative_words = []
        for w in words:
            if w.startswith('-') and len(w) > 1:
                negative_words.append(w[1:])
            else:
                # ORで繋がれた単語をリストにして追加
                parts = w.split('|')
                positive_groups.append(parts)

        # プラス検索の単語が1つもない場合はエラーを回避して空を返す（FTS5は肯定条件が必須なため）
        if not positive_groups:
            return []

        print(f"\n{'='*60}")
        print(f" Query: '{user_query}'")
        print(f"{'='*60}")
        
        search_groups = [] 

        for or_words in positive_groups:
            combined_similar_tags_map = {}
            print(f"  [OR Group] Processing: {or_words}")

            for word in or_words:
                final_tag, similar_tags_map = self.find_similar_tags_with_score(word)

                print(f"  Target: '{final_tag}' -> Candidates: {len(similar_tags_map)}")

                # 取得した類似タグ群を1つのグループに合流（重複時はスコアが高い方を優先）
                for t, s in similar_tags_map.items():
                    if t not in combined_similar_tags_map or s > combined_similar_tags_map.get(t, 0):
                        combined_similar_tags_map[t] = s

            search_groups.append(combined_similar_tags_map)

        match_groups = []

        fast_lookup = {}
        for group_map in search_groups:
            for tag, score in group_map.items():
                norm_tag = tag.lower().replace('_', ' ')
                # 重複した場合はスコアが高い方を残す
                if norm_tag not in fast_lookup or score > fast_lookup.get(norm_tag, 0):
                    fast_lookup[norm_tag] = score

        for group_map in search_groups:
            or_parts = []
            for tag in group_map.keys():
                # FTS5のMATCH構文用にフレーズをダブルクォーテーションで囲む
                norm_tag = tag.replace('_', ' ')
                or_parts.append(f'"{norm_tag}"')
            if or_parts:
                match_groups.append(f"({' OR '.join(or_parts)})")

        if not match_groups: return []

        # 複数の検索ワード(グループ)をANDで結合
        match_query = " AND ".join(match_groups)

        # ここからマイナス検索（除外）のクエリ構築処理
        if negative_words:
            negative_tags = set()
            print(f"  [Negative Search] Processing exclusions...")
            for word in negative_words:
                # 除外ワードもベクトル検索や翻訳にかけて類似タグを網羅する
                #除外検索では類似タグの網羅リストさえ手に入ればいいため, _ で受け流す
                _, similar_tags_map = self.find_similar_tags_with_score(word)
                for tag in similar_tags_map.keys():
                    norm_tag = tag.replace('_', ' ')

                    #プラス検索の対象になっているタグは絶対に除外しない（巻き込み防止）
                    if norm_tag not in fast_lookup:
                        negative_tags.add(f'"{norm_tag}"')
            
            if negative_tags:
                # FTS5の NOT 構文で除外タグをすべて繋げる
                not_string = " NOT ".join(list(negative_tags))
                match_query = f"{match_query} NOT {not_string}"
                print(f"  -> Added {len(negative_tags)} tags to NOT query.")

        # ターミナルで最終的なMATCHクエリを確認できるように出力
        print(f"  [FTS5 Query] {match_query}")

        # LIMIT句と params.append を完全に削除し、全件取得する
        # 仮想テーブル(images_fts)をMATCH検索し、元のテーブル(images)と結合してデータを取得
        full_sql = '''
            SELECT i.id, i.file_path, i.tags_combined, i.tag_scores, i.file_mtime, i.thumbnail_path, i.is_favorite
            FROM images i
            INNER JOIN images_fts f ON i.id = f.id
            WHERE images_fts MATCH ?
        '''
        
        cursor = self.db.conn.cursor()
        cursor.execute(full_sql, (match_query,))
        raw_results = [dict(row) for row in cursor.fetchall()]
        
        print(f"  -> DB Hits: {len(raw_results)} (Scoring...)")

        scored_results = []
        for row in raw_results:
            # 絵柄検索(style:)が併用されている場合、FAISSの結果に無い画像は捨てる（AND結合）
            if style_name and row['id'] not in style_scores_map:
                continue

            # JSON文字列をPythonの辞書に変換（データがない場合のエラー回避策も含む）
            scores_dict = {}
            if row.get('tag_scores'):
                try:
                    scores_dict = json.loads(row['tag_scores'])
                except json.JSONDecodeError:
                    pass
            # 次のステップ（計算ロジック）で使うために辞書データをrowに保持しておく
            row['parsed_tag_scores'] = scores_dict

            score, matches = self.calculate_image_score_with_details(row['tags_combined'], search_groups, row['parsed_tag_scores'])

            # 絵柄のスコアも合算して、ターミナルで確認できるようにする
            if style_name:
                style_score = style_scores_map[row['id']]

                # 0.98を1.0倍(基準)とし、1.00で最大3.0倍になるように係数(100)を掛ける
                style_multiplier = 1.0 + max(0, (style_score - 0.98) * 100)
                # タグの点数に倍率を掛けて最終スコアとする
                # (万が一タグスコアが0に近い場合でも絵柄が評価されるよう、最低保証点1.0を設ける)
                base_score = max(score, 1.0)
                score = base_score * style_multiplier
                
                matches.append({
                    "tag": style_name,
                    "final": style_score,
                    "sim": style_score,
                    "ai": 1.0,
                    "idf": 1.0
                })

            row['match_score'] = score
            row['matched_tags'] = matches
            scored_results.append(row)
            
        # ブックマーク済みの時だけお気に入り(is_favorite)を最優先にし、それ以外は純粋なスコア順にする
        if is_bookmarked:
            scored_results.sort(key=lambda x: (x.get('is_favorite', 0), x['match_score'], x['file_mtime']), reverse=True)
        else:
            scored_results.sort(key=lambda x: (x['match_score'], x['file_mtime']), reverse=True)

        #複検索結果を返す
        return scored_results

if __name__ == "__main__":
    searcher = TagSearch()
    # テスト: 辞書にある単語と、ない単語を混ぜる
    q = "黒髪 ロングヘア" 
    results = searcher.search(q)
    
    print(f"\n【Final Result】")
    print("-" * 60)
    # テスト時は上位5件だけ表示するようにスライス
    for i, row in enumerate(results[:5]):
        print(f"Rank {i+1} [Score: {row['match_score']:.2f}]")
        print(f"  Path: {row['file_path']}")

        # 保持しておいた係数の内訳を展開して表示
        print("  Matches:")
        for m in row['matched_tags']:
            print(f"    [{m['tag']}] {m['final']:.3f} = {m['sim']:.3f}(sim) * {m['ai']:.3f}(ai) * {m['idf']:.3f}(idf)")

        print("-" * 60)