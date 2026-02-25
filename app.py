import flet as ft
import asyncio
from core.tag_search import TagSearch

async def initialize_engine(page: ft.Page, status_text: ft.Text):
    
    await asyncio.sleep(0.1) #ブラウザへの描画時間を確保
    
    print("AIモデルを読み込んでいます...")
    searcher = TagSearch() #重い処理
    
    status_text.value = "Ready" #準備完了メッセージ
    page.update()
    
    return searcher

async def main(page: ft.Page):
    #ページ全体の設定
    page.title = "Local image searcher"
    page.theme_mode = "dark"

    #Loadingを表示
    status_text = ft.Text("Loading...", color="green", size=20)
    page.add(status_text)
    page.update()

    #ロード
    searcher = await initialize_engine(page, status_text)

    #ボタンが押された時の動作
    async def on_search(e):
        query = search_input.value
        results = searcher.search(query)
        status_text.value = f"ヒット: {len(results)}件"
        page.update()

    #検索窓と検索ボタンを表示
    search_input = ft.TextField(hint_text="タグを入力して検索", width=400) #テキストボックス
    search_btn = ft.FilledButton("検索", on_click=on_search) #ボタン
    page.add(
        ft.Row([search_input, search_btn]),
    )
    page.update()

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=8000)