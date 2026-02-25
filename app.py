import flet as ft
import asyncio
from core.tag_search import TagSearch

async def main(page: ft.Page):
    page.title = "Step 2.8 - Sync Update"
    page.theme_mode = "dark"

    #最初に表示する部品
    status_text = ft.Text("Loading: 準備中...", color="yellow", size=20)

    #画面に「Loading」を出す
    page.add(status_text)
    
    page.update() 
    
    #Pythonが一時停止してブラウザが描画する時間を稼ぐ
    await asyncio.sleep(0.1)

    print("AIモデルを読み込んでいます...")
    # 4. 重いロード作業
    searcher = TagSearch() 

    #ロードが終わった後の部品
    search_input = ft.TextField(hint_text="タグを入力して検索", width=400)

    #ボタンが押された時の動作
    async def on_search(e):
        query = search_input.value
        results = searcher.search(query)
        status_text.value = f"ヒット: {len(results)}件"
        page.update()

    search_btn = ft.FilledButton("検索", on_click=on_search)

    #UIを更新
    status_text.value = "Ready! ロード完了。"
    status_text.color = "green"
    
    page.add(
        ft.Row([search_input, search_btn]),
    )
    
    page.update()

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=8000)