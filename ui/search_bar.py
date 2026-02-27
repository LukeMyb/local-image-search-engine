import flet as ft
import asyncio

class SearchBar:
    def __init__(self, on_search_callback):
        # 検索が実行されたときに上位(app.py)の処理を呼ぶためのコールバック
        self.on_search_callback = on_search_callback
        self._build_ui()

    def _build_ui(self):
        #検索窓
        self.search_input = ft.TextField(
            hint_text="タグを入力して検索", 
            expand=True, 
            on_submit=lambda e: asyncio.create_task(self._handle_search()) #エンターキーで検索
        )

        #ヘッダー部分(検索窓と検索ボタン)
        self.view = ft.Row(
            [
                self.search_input,
                ft.IconButton(
                    icon=ft.Icons.SEARCH, 
                    on_click=lambda e: asyncio.create_task(self._handle_search())
                ),
            ]
        )

    async def _handle_search(self):
        # 検索窓のテキストを取得
        query = self.search_input.value
        if not query: return #検索窓が空なら何もしない

        # 上位(app.py)に検索クエリを渡して処理を任せる
        await self.on_search_callback(query)