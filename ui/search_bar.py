import flet as ft
import asyncio

class SearchBar:
    def __init__(self, on_search_callback, on_suggest_callback):
        # 検索が実行されたときに上位(app.py)の処理を呼ぶためのコールバック
        self.on_search_callback = on_search_callback
        # サジェスト候補を取得するためのコールバック
        self.on_suggest_callback = on_suggest_callback
        self._build_ui()

    def _build_ui(self):
        #検索窓
        self.search_input = ft.TextField(
            hint_text="タグを入力して検索", 
            expand=True, 
            on_submit=lambda e: asyncio.create_task(self._handle_search()), #エンターキーで検索
            on_change=self._handle_change, #文字が入力されるたびに呼ばれる
        )

        #サジェスト結果を表示するリストとコンテナ
        self.suggest_list = ft.ListView(spacing=0, padding=0)

        #コンテナの定義
        self.suggest_container = ft.Container(
            content=self.suggest_list,
            visible=False, # 最初は隠しておく
            bgcolor="#1E1E1E", # 背景を少し明るい黒に
            border=ft.border.all(1, "white24"),
            border_radius=4,
            padding=5,
            height=200, # リストが長くなりすぎないように高さを制限（スクロール可能）
        )

        #ヘッダー部分(検索窓と検索ボタン)
        self.search_row = ft.Row(
            [
                self.search_input,
                ft.IconButton(
                    icon=ft.Icons.SEARCH, 
                    on_click=lambda e: asyncio.create_task(self._handle_search())
                ),
            ]
        )

        #検索窓の下にサジェストコンテナを配置するためColumnで包む
        self.view = ft.Column(
            [
                self.search_row,
                self.suggest_container,
            ],
            spacing=0,
        )

    def _handle_change(self, e):
        query = self.search_input.value
        
        # 上位(app.py)にクエリを渡してサジェスト候補のリストをもらう
        suggestions = self.on_suggest_callback(query)
        
        # 一旦リストを空にする
        self.suggest_list.controls.clear()
        
        # 候補が空ならコンテナを隠して終了
        if not suggestions:
            self.suggest_container.visible = False
            self.suggest_container.update()
            return
            
        # 候補がある場合はリストに追加していく
        for s in suggestions:
            # クロージャを使ってクリック時の処理を定義
            def on_click_suggest(e, q=s["query"]):
                self.search_input.value = q # 検索窓の文字を選択した候補で上書き
                self.suggest_container.visible = False # サジェストを隠す
                self.view.update()
                asyncio.create_task(self._handle_search()) # すぐに検索を実行する
                
            item = ft.ListTile(
                title=ft.Text(s["display"], size=14),
                on_click=on_click_suggest,
                dense=True, # 行間を詰める
            )
            self.suggest_list.controls.append(item)
            
        # コンテナを表示して画面を更新
        self.suggest_container.visible = True
        self.suggest_container.update()

    async def _handle_search(self):
        #検索を実行したらサジェストは隠す
        self.suggest_container.visible = False
        self.suggest_container.update()

        # 検索窓のテキストを取得
        query = self.search_input.value
        if not query: return #検索窓が空なら何もしない

        # 上位(app.py)に検索クエリを渡して処理を任せる
        await self.on_search_callback(query)