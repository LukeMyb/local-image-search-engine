import flet as ft
import asyncio
import os
import webbrowser
from core.database import ImageDatabase
from core.tag_search import TagSearch
from ui.search_bar import SearchBar
from ui.viewer import ImageViewer
from ui.gallery import ImageGallery

async def initialize_engine(page: ft.Page, status_text: ft.Text):
    await asyncio.sleep(0.1) #ブラウザへの描画時間を確保
    
    print("AIモデルを読み込んでいます...")
    searcher = TagSearch() #重い処理
    
    status_text.value = "Ready" #準備完了メッセージ
    page.update()
    
    return searcher

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

    #画像クリック時の処理
    async def on_image_click(e):
        #クリックされた画像の情報(row)を取得
        row = e.control.data
        if not row: return

        #openメソッドを呼び出す
        await viewer.open(current_results, row)

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

    #ギャラリーの初期化
    gallery = ImageGallery(
        on_image_click_callback=on_image_click,
        on_page_change_callback=on_page_change
    )

    async def on_search(query):
        nonlocal all_results, current_page

        #ステータスメッセージの更新
        status_text.value = "検索中..."
        page.update()

        #非同期で検索を実行するとUIが固まらない（今回は簡易的に同期実行）
        results, conversion_log = searcher.search(query)

        all_results = results #検索結果をグローバル変数に保存しておく
        current_page = 1

        if not all_results:
            status_text.value = "見つかりませんでした。"
            gallery.update_gallery([], 1, 1) 
        else:
            status_text.value = f"{len(all_results)}hit {conversion_log}"
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
        on_search_callback=on_search, 
        on_suggest_callback=on_suggest
    )

    #レイアウト
    page.add(
        ft.Column(
            [
                status_text,
                search_bar.view,
                gallery.view,
            ],
            expand=True, #画面下まで広げる
            spacing=4,
        )
    )

    #ロード
    searcher = await initialize_engine(page, status_text)

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