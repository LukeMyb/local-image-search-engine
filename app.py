import flet as ft
import asyncio
import os
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
    current_results = [] #検索結果のリスト

    #ページ全体の設定
    page.title = "Local image searcher"
    page.theme_mode = "dark"
    page.padding = 6 #余白

    #Loading
    status_text = ft.Text("Loading...", color="green", size=20)

    viewer = ImageViewer(page) #画像ビューアの初期化

    #画像クリック時の処理
    async def on_image_click(e):
        #クリックされた画像の情報(row)を取得
        row = e.control.data
        if not row: return

        #openメソッドを呼び出す
        await viewer.open(current_results, row)

    #ギャラリーの初期化
    gallery = ImageGallery(on_image_click_callback=on_image_click)

    async def on_search(query):
        nonlocal current_results

        #ステータスメッセージの更新
        status_text.value = "検索中..."
        page.update()

        #非同期で検索を実行するとUIが固まらない（今回は簡易的に同期実行）
        results, conversion_log = searcher.search(query, limit=50)

        current_results = results #検索結果をグローバル変数に保存しておく

        if not results:
            status_text.value = "見つかりませんでした。"
            gallery.update_gallery([]) #ギャラリーを空にする
        else:
            status_text.value = f"{len(results)}hit {conversion_log}"
            gallery.update_gallery(results) #ギャラリーに画像を描画させる

        page.update()

    #検索窓の初期化
    search_bar = SearchBar(on_search_callback=on_search)

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
    ft.app(
        target=main, 
        view=ft.AppView.WEB_BROWSER, 
        port=8000, 
        assets_dir="data", 
        host="0.0.0.0" 
    )