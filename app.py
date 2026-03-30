import flet as ft
import asyncio
import os
import webbrowser

#Hugging Faceのオンライン通信を完全に遮断し、完全オフラインモードにする
os.environ["HF_HUB_OFFLINE"] = "1"
#Transformersライブラリ側の通信も強制遮断する
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from core.database import ImageDatabase
from core.search import SearchManager

#バックグラウンド処理に必要なモジュール群
from core.index import ImageIndexer, ThumbnailGenerator
from core.tagger import Tagger
from core.vectorize_images import StyleVectorizer

from ui.search_bar import SearchBar
from ui.viewer import ImageViewer
from ui.gallery import ImageGallery
from ui.drawer import BookmarkDrawer

async def initialize_engine(page: ft.Page, status_text: ft.Text, db: ImageDatabase):
    await asyncio.sleep(0.1) #ブラウザへの描画時間を確保
    
    print("AIモデルを読み込んでいます...")
    search_manager = SearchManager() #重い処理 #重い処理

    #TagSearchが内部に持っているエンジンを共有する（二重ロード防止）
    style_searcher = search_manager.style_engine

    if style_searcher is None:
        print("  [!] 絵柄検索エンジンの統合に失敗しました。")
    
    status_text.value = "Ready" #準備完了メッセージ
    page.update()
    
    return search_manager, style_searcher

# バックグラウンドで走る自動同期プロセス
async def auto_sync_process():
    """起動時に非同期で実行され、UIを固めずに裏で画像を処理する"""
    print("  [AutoSync] バックグラウンド同期を開始します...")
    
    def run_sync():
        try:
            # SQLiteの「別スレッドからのアクセス禁止」エラーを防ぐため、同期処理専用のDB接続を作成
            sync_db = ImageDatabase()
            
            # 1. フォルダの新規スキャン
            print("  [AutoSync] フォルダをスキャンしています...")
            indexer = ImageIndexer(sync_db, "data/images")
            indexer.scan_and_register()

            # 2. サムネイル未作成の画像を処理
            unprocessed_thumbs = sync_db.get_unprocessed_images('is_thumbnail_created')
            if unprocessed_thumbs:
                print(f"  [AutoSync] {len(unprocessed_thumbs)}件のサムネイルを作成します...")
                generator = ThumbnailGenerator(sync_db)
                generator.process_all()

            # 3. タグ未付与の画像を処理 (WD1.4 Tagger)
            unprocessed_tags = sync_db.get_unprocessed_images('is_processed_tag')
            if unprocessed_tags:
                print(f"  [AutoSync] {len(unprocessed_tags)}件のタグ付けを実行します...")
                # Taggerは内部で独自のDB接続を開くため安全
                tagger = Tagger(db_path="data/db/index.db") 
                tagger.process_all(force_update=False)

            # 4. 絵柄ベクトル未処理の画像を処理
            unprocessed_vecs = sync_db.get_unprocessed_images('is_processed_vector')
            if unprocessed_vecs:
                print(f"  [AutoSync] {len(unprocessed_vecs)}件の絵柄ベクトル化を実行します...")
                vectorizer = StyleVectorizer(sync_db)
                # RTX 50シリーズを活かしたバッチサイズで高速処理
                vectorizer.process_all(batch_size=32)

            sync_db.close()
            print("  [AutoSync] 全てのバックグラウンド同期が完了しました。")
        except Exception as e:
            print(f"  [AutoSync] 同期中にエラーが発生しました: {e}")

    # UIスレッドをフリーズさせないよう、重い処理を別スレッドに投げる
    await asyncio.to_thread(run_sync)

async def main(page: ft.Page):
    all_results = [] #全検索結果のリスト
    current_results = [] #現在表示中の検索結果のリスト
    
    current_page = 1
    items_per_page = 100 # 100枚ずつの表示に変更

    #ページ全体の設定
    page.title = "Local image searcher"
    page.theme_mode = "dark"
    page.padding = 6 #余白

    #Loading
    status_text = ft.Text("Loading...", color="green", size=20)

    #初期化
    db = ImageDatabase()
    viewer = ImageViewer(page, db)

    # 選択モード管理用の変数
    selected_image_ids = set()

    #画像クリック時の処理
    def on_image_click(e):
        #クリックされた画像の情報(row)を取得
        row = e.control.data
        if not row: return

        #openメソッドを呼び出す（タスクとして非同期実行）
        asyncio.create_task(viewer.open(all_results, row))

    def render_current_page():
        nonlocal current_results
        
        start_idx = (current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        current_results = all_results[start_idx:end_idx]
        total_pages = max(1, (len(all_results) + items_per_page - 1) // items_per_page)
        
        gallery.update_gallery(current_results, current_page, total_pages)

    def on_page_change(delta):
        nonlocal current_page
        total_pages = max(1, (len(all_results) + items_per_page - 1) // items_per_page)
        
        new_page = current_page + delta
        if 1 <= new_page <= total_pages:
            current_page = new_page
            render_current_page()
            page.update()

    # ギャラリーのダイアログから送られてくる処理の受け口
    def on_style_create(style_name, selected_ids):
        status_text.value = "絵柄を解析中..."
        page.update()

        # DBから選択された画像のパスを取得
        image_paths = []
        for img_id in selected_ids:
            img_data = db.get_image_by_id(img_id)
            if img_data:
                image_paths.append(img_data['file_path'])
        
        if image_paths:
            print(f"DEBUG: [{style_name}] を {len(image_paths)}枚の画像から計算します...")
            
            # 外部モジュールを使って重心ベクトルを計算
            centroid = style_searcher.calculate_centroid(image_paths)
            
            if centroid is not None:
                # DBの style_tags テーブルに保存
                db.save_style_tag(style_name, centroid)
                print(f"[{style_name}] の保存が完了しました！")
                status_text.value = f"絵柄タグ '{style_name}' を作成しました"
            else:
                status_text.value = "絵柄の解析に失敗しました"
        
        page.update()

    #ギャラリーの初期化
    gallery = ImageGallery(
        page=page,
        on_image_click_callback=on_image_click,
        on_style_create_callback=on_style_create,
        on_page_change_callback=on_page_change,
        on_swipe_right_callback=lambda: drawer.show(),
    )

    async def on_search(query, is_bookmarked=False):
        nonlocal all_results, current_page

        #ステータスメッセージの更新
        status_text.value = "検索中..."
        page.update()

        #重い検索処理が始まる前に、画面に「検索中...」を描画させるための短い隙間（0.1秒）を作る
        await asyncio.sleep(0.1)

        #クエリが空欄（空白のみ含む）の場合はお気に入りを取得し、それ以外は検索を実行する
        if not query.strip():
            results = db.get_favorite_images()
        else:
            #検索を実行
            results = searcher.search(query, is_bookmarked)

            # ここから上位5件のスコア詳細をターミナルに出力する処理
            print(f"\n【Search Result: '{query}'】")
            print("-" * 60)
            for i, row in enumerate(results[:5]):
                # match_scoreが設定されているか確認して表示
                score = row.get('match_score', 0)
                print(f"Rank {i+1} [Score: {score:.3f}]")
                print(f"  Path: {row['file_path']}")
                print("  Matches:")
                
                # matched_tagsの内訳を展開して表示
                if 'matched_tags' in row:
                    for m in row['matched_tags']:
                        if m.get("is_style"):
                            print(f"    [{m['tag']}] {m['base']:.3f}(base) * {m['multiplier']:.3f}(sim:{m['sim']:.3f}) = {m['base'] + m['final']:.3f}")
                        else:
                            print(f"    [{m['tag']}] {m['final']:.3f} = {m['sim']:.3f}(sim) * {m['ai']:.3f}(ai) * {m['idf']:.3f}(idf)")
            print("-" * 60)

        all_results = results #検索結果をグローバル変数に保存しておく
        current_page = 1

        if not all_results:
            status_text.value = "お気に入り画像がありません。" if not query.strip() else "見つかりませんでした。"
            gallery.update_gallery([], 1, 1)
        else:
            #クエリが空（お気に入り）の時と、通常検索時で表示を分ける
            if not query.strip():
                status_text.value = f"{len(all_results)}hit （お気に入り）"
            else:
                status_text.value = f"{len(all_results)}hit"

            render_current_page()

        page.update()

    #サジェスト候補を取得する
    def on_suggest(query):
        # AIモデル(searcher)がまだロードされていない起動直後は空を返す
        if searcher is None:
            return []
        
        # tag_search.pyに処理を丸投げする
        return searcher.get_suggestions(query)

    #検索窓の初期化
    search_bar = SearchBar(
        page=page,
        db=db,
        on_search_callback=on_search, 
        on_suggest_callback=on_suggest
    )

    #ドロワーの初期化
    drawer = BookmarkDrawer(page, db, search_bar)
    # 検索窓でブックマークが保存・削除された際に、ドロワーのリストを更新するよう紐付け
    search_bar.on_bookmark_updated = drawer.refresh_list

    # ギャラリーが用意したトグルボタンを引き取って横並びにする
    status_row = ft.Row([status_text, gallery.selection_mode_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

    #レイアウト
    page.add(
        ft.Column(
            [
                status_row,
                search_bar.view,
                gallery.view,
                gallery.selection_banner,
            ],
            expand=True, #画面下まで広げる
            spacing=4,
        )
    )

    #ロード
    searcher, style_searcher = await initialize_engine(page, status_text, db)

    #エンジンロード完了直後に空クエリを投げ、初回起動時にお気に入りを表示させる
    await on_search("")

    # エンジンがロードされ、UIの表示が終わったタイミングで裏の同期タスクをキックする
    asyncio.create_task(auto_sync_process())

if __name__ == "__main__":
    #自動起動を無効化 (ダミー関数で上書き)
    webbrowser.open = lambda *args, **kwargs: None
    
    ft.run(
        main, 
        view=ft.AppView.WEB_BROWSER, 
        port=8000, 
        assets_dir="data", 
        host="0.0.0.0" 
    )