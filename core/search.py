import re
from core.tag_search import TagSearch
from core.style_search import StyleSearcher
from core.database import ImageDatabase

class SearchManager:
    """
    検索全体のオーケストレーター
    タグ検索エンジンと絵柄検索エンジンを統括し、結果を結合する
    """
    def __init__(self, db_path="data/db/index.db", tag_index_path="data/tag_vector_index.bin"):
        print("  [SearchManager] 初期化中...")
        self.db = ImageDatabase(db_path)
        
        # 各エンジンをそれぞれ独立して初期化（ここで統括する）
        self.tag_searcher = TagSearch(db_path, tag_index_path)
        
        try:
            self.style_engine = StyleSearcher(self.db)
        except Exception as e:
            print(f"  [SearchManager] 絵柄検索エンジンのロードに失敗しました: {e}")
            self.style_engine = None

    def get_suggestions(self, query_text, limit=10):
        if not query_text: return []

        normalized_query = query_text.replace('　', ' ')
        parts = normalized_query.split(' ')
        current_word = parts[-1]
        
        if not current_word:
            return []

        base_query = " ".join(parts[:-1]) + " " if len(parts) > 1 else ""

        # 絵柄検索(style:)のサジェスト処理は style_engine に任せる
        if current_word.lower().startswith("style:"):
            if self.style_engine:
                prefix = current_word.lower()
                return self.style_engine.get_style_suggestions(prefix, base_query)
            return []
            
        # それ以外は純粋なタグ検索のサジェストに丸投げ
        return self.tag_searcher.get_suggestions(query_text, limit)

    def search(self, user_query, is_bookmarked=False):
        # 絵柄タグ(style:xxx)の抽出と分離処理（tag_searchから移植）
        style_match = re.search(r'style:([^\s|]+)', user_query)
        style_name = None
        style_scores_map = {}
        style_results = []
        
        # 1. 絵柄検索の実行
        if style_match:
            style_name = style_match.group(0)
            user_query = user_query.replace(style_name, '').strip()
            
            if self.style_engine is None:
                print("エラー: 絵柄検索エンジンが起動していません。")
                return []
                
            print(f"\n{'='*60}")
            print(f" Style Search: '{style_name}'")
            print(f"{'='*60}")
            
            style_results = self.style_engine.search_by_style_name(style_name, threshold=0.98)
            style_scores_map = {res['id']: res['match_score'] for res in style_results}
            
            if not user_query:
                if is_bookmarked:
                    style_results.sort(key=lambda x: (x.get('is_favorite', 0), x['match_score'], x['file_mtime']), reverse=True)
                else:
                    style_results.sort(key=lambda x: (x['match_score'], x['file_mtime']), reverse=True)
                return style_results
                
            if not style_scores_map:
                print("  -> 絵柄に一致する画像が0件のため、検索を終了します。")
                return []
                
            print(f"  -> 絵柄検索で {len(style_scores_map)}件 ヒット。続けてタグ検索で絞り込みます...")

        # 2. タグ検索の実行
        # タグ検索エンジンには純粋なテキストクエリだけを投げる
        tag_results = self.tag_searcher.search(user_query, is_bookmarked=False) # ソートは後で行うためここではFalse

        # 3. 結果のAND結合と最終スコア計算
        if not style_name:
            # 絵柄指定がなければタグ検索の結果をそのまま返す（ソートだけ適用）
            if is_bookmarked:
                tag_results.sort(key=lambda x: (x.get('is_favorite', 0), x['match_score'], x['file_mtime']), reverse=True)
            return tag_results

        # 絵柄とタグの両方が指定されている場合の結合・倍率計算処理
        # FAISS(絵柄)とSQLite(タグ)の双方でヒットした画像だけを残し、スコアを掛け合わせて再評価する
        scored_results = []
        for row in tag_results:
            # FAISSの結果に無い画像は捨てる（AND結合）
            if row['id'] not in style_scores_map:
                continue

            style_score = style_scores_map[row['id']]
            # 絵柄の類似度(0.98〜1.0)を強調するため、0.98を超えた分を100倍して1.0に足す
            # 例: スコア0.992なら、1.0 + (0.012 * 100) = 2.2倍のボーナスがかかる
            style_multiplier = 1.0 + max(0, (style_score - 0.98) * 100)
            base_score = max(row['match_score'], 1.0)
            final_score = base_score * style_multiplier

            row['match_score'] = final_score
            # ターミナルで最終的な計算内訳を確認できるように、スコア詳細をリストに追記
            row['matched_tags'].append({
                "is_style": True,
                "tag": style_name,
                "final": final_score - base_score,
                "sim": style_score,
                "base": base_score,
                "multiplier": style_multiplier
            })
            scored_results.append(row)

        # ブックマーク済みの時だけお気に入り(is_favorite)を最優先にし、それ以外は純粋なスコア順にする
        if is_bookmarked:
            scored_results.sort(key=lambda x: (x.get('is_favorite', 0), x['match_score'], x['file_mtime']), reverse=True)
        else:
            scored_results.sort(key=lambda x: (x['match_score'], x['file_mtime']), reverse=True)

        return scored_results