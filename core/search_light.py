import re
from fastapi import HTTPException
from core.tag_search_light import TagSearchLight
from core.database import ImageDatabase

class SearchManagerLight:
    """
    検索全体のオーケストレーター（軽量版）
    絵柄検索エンジンを排除し、タグ検索エンジン（軽量版）のみを使用する
    """
    def __init__(self, db_path="data/db/index.db"):
        print("  [SearchManagerLight] 初期化中...")
        self.db = ImageDatabase(db_path)
        
        # タグ検索エンジン(軽量版)を初期化
        self.tag_searcher = TagSearchLight(db_path)
        
        # 軽量版のため絵柄検索エンジンはロードしない
        self.style_engine = None

    def get_suggestions(self, query_text, limit=10):
        if not query_text: return []

        normalized_query = query_text.replace('　', ' ')
        parts = normalized_query.split(' ')
        current_word = parts[-1]
        
        if not current_word:
            return []

        base_query = " ".join(parts[:-1]) + " " if len(parts) > 1 else ""

        # 絵柄検索(style:)のサジェスト処理（軽量モードでもDBから取得可能）
        if current_word.lower().startswith("style:"):
            styles = self.db.get_all_styles()
            candidates = []
            prefix = current_word.lower()
            
            for s in styles:
                style_name = s['name']
                if style_name.lower().startswith(prefix):
                    candidates.append({
                        "id": s['id'],           # DBから削除するためのID
                        "is_style": True,        # ゴミ箱ボタンを表示するかどうかのフラグ
                        "display": style_name,
                        "query": base_query + style_name,
                        "count": 0
                    })
            return candidates
            
        # 純粋なタグ検索のサジェストに丸投げ
        return self.tag_searcher.get_suggestions(query_text, limit)

    def search(self, user_query, is_bookmarked=False, sort_order="score"):
        # 絵柄タグ(style:xxx)が含まれているかチェック
        style_match = re.search(r'style:([^\s|]+)', user_query)
        style_name = None
        style_scores_map = {}
        style_results = []

        # ソートの共通処理用の内部関数
        def sort_by_order(res_list):
            if sort_order == "favorite":
                res_list.sort(key=lambda x: (x.get('is_favorite', 0), x.get('match_score', 0), x['file_mtime']), reverse=True)
            elif sort_order == "newest":
                res_list.sort(key=lambda x: (x['file_mtime'], x.get('match_score', 0)), reverse=True)
            else: # "score"
                res_list.sort(key=lambda x: (x.get('match_score', 0), x['file_mtime']), reverse=True)
            return res_list
        
        if style_match:
            style_name = style_match.group(0)
            user_query = user_query.replace(style_name, '').strip()
            
            print(f"\n{'='*60}")
            print(f" Style Search (Light Mode Cache): '{style_name}'")
            print(f"{'='*60}")
            
            # 軽量モードではDBに保存されたキャッシュリストを使用する
            style_scores_map = self.db.get_style_cache(style_name)
            
            if not style_scores_map:
                raise HTTPException(
                    status_code=400, 
                    detail=f"絵柄タグ '{style_name}' のキャッシュが見つかりません。通常モードで一度起動するかキャッシュを更新してください。"
                )
            
            print(f"  -> キャッシュから {len(style_scores_map)}件 の画像を読み込みました。")
            
            if not user_query:
                # 絵柄指定のみの場合は、キャッシュに存在するIDから画像情報を取得して返す
                # 軽量モードでは生のDBアクセスで対応
                image_ids = list(style_scores_map.keys())
                style_results = self.db.get_images_by_ids(image_ids)
                
                # スコアを当て直す
                for row in style_results:
                    row['match_score'] = style_scores_map.get(row['id'], 0)
                    row['matched_tags'] = [{
                        "is_style": True,
                        "tag": style_name,
                        "final": 0,
                        "sim": row['match_score'],
                        "base": 0,
                        "multiplier": 1.0
                    }]
                return sort_by_order(style_results)

        # タグ検索の実行
        tag_results = self.tag_searcher.search(user_query, is_bookmarked=False)

        if not style_name:
            return sort_by_order(tag_results)

        # 絵柄(キャッシュ)とタグ(FTS5)の両方が指定されている場合の結合処理
        scored_results = []
        for row in tag_results:
            if row['id'] not in style_scores_map:
                continue

            style_score = style_scores_map[row['id']]
            style_multiplier = 1.0 + max(0, (style_score - 0.98) * 100)
            base_score = max(row['match_score'], 1.0)
            final_score = base_score * style_multiplier

            row['match_score'] = final_score
            row['matched_tags'].append({
                "is_style": True,
                "tag": style_name,
                "final": final_score - base_score,
                "sim": style_score,
                "base": base_score,
                "multiplier": style_multiplier
            })
            scored_results.append(row)

        return sort_by_order(scored_results)
