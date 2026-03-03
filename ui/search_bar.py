import flet as ft
import asyncio

class SearchBar:
    def __init__(self, page, db, on_search_callback, on_suggest_callback):
        self.page = page # ダイアログ表示用
        self.db = db     # DB操作用

        # 検索が実行されたときに上位(app.py)の処理を呼ぶためのコールバック
        self.on_search_callback = on_search_callback
        # サジェスト候補を取得するためのコールバック
        self.on_suggest_callback = on_suggest_callback

        # メモリ上のブックマーク保持用（キー：クエリ、値：名前）
        self.saved_queries = {}
        self.refresh_saved_queries()

        self._build_ui()

    # DBからブックマーク一覧を取得し、メモリ（辞書）を更新するメソッド
    def refresh_saved_queries(self):
        bookmarks = self.db.get_bookmarks()
        # クエリをキーにして名前を保存（検索窓の文字と完全一致判定するため）
        self.saved_queries = {b['query']: b['name'] for b in bookmarks}

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

        #ブックマークボタンの定義
        self.bookmark_btn = ft.IconButton(
            icon=ft.Icons.BOOKMARK_ADD_OUTLINED,
            on_click=self._handle_bookmark_click,
            tooltip="検索条件を保存"
        )

        #検索ボタンを変数として定義
        self.search_btn = ft.IconButton(
            icon=ft.Icons.SEARCH, 
            on_click=lambda e: asyncio.create_task(self._handle_search())
        )

        #ヘッダー部分
        self.search_row = ft.Row(
            [
                self.search_input, #検索窓
                self.bookmark_btn, #検索ボタン
                self.search_btn, #ブックマークボタン
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

        #文字が入力されるたびにブックマーク状態をチェック
        self._update_bookmark_icon(query)
        
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

    # 現在のクエリが保存済みかどうかでアイコンを動的に切り替える
    def _update_bookmark_icon(self, query):
        if query in self.saved_queries:
            self.bookmark_btn.icon = ft.Icons.BOOKMARK_ADDED
            self.bookmark_btn.icon_color = ft.Colors.GREEN
            self.bookmark_btn.tooltip = "保存済み（クリックで管理）"
        else:
            self.bookmark_btn.icon = ft.Icons.BOOKMARK_ADD_OUTLINED
            self.bookmark_btn.icon_color = None
            self.bookmark_btn.tooltip = "検索条件を保存"
        self.bookmark_btn.update()

    # ブックマークボタンが押された時の処理
    def _handle_bookmark_click(self, e):
        query = self.search_input.value.strip()
        
        if not query: return # 空欄の場合は何もしない

        if query in self.saved_queries:
            # すでに保存済みなら、削除ダイアログを表示
            self._show_edit_dialog(query, self.saved_queries[query])
        else:
            # 未保存なら、新規保存ダイアログを表示
            self._show_save_dialog(query)

    # 新規保存ダイアログ
    def _show_save_dialog(self, query):
        name_input = ft.TextField(label="ブックマーク名", value="", autofocus=True)
        
        def close_dlg(e): #キャンセルボタン
            dlg.open = False
            self.page.update()

        def save_click(e): #保存ボタン
            name = name_input.value.strip()
            if not name:
                return
            # DBに保存し、メモリを更新
            self.db.save_bookmark(name, query)
            self.refresh_saved_queries()
            self._update_bookmark_icon(query)
            print(f"[Bookmark] '{name}' を保存しました")
            close_dlg(e)

        dlg = ft.AlertDialog(
            title=ft.Text("検索条件を保存"),
            content=name_input,
            actions=[
                ft.TextButton("キャンセル", on_click=close_dlg),
                ft.TextButton("保存", on_click=save_click),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    # 削除確認ダイアログ
    def _show_edit_dialog(self, query, current_name):

        def close_dlg(e): #キャンセルボタン
            dlg.open = False
            self.page.update()

        def delete_click(e): #削除ボタン
            bm = self.db.get_bookmark_by_name(current_name)
            if bm:
                self.db.delete_bookmark(bm['id'])
                print(f"[Bookmark] '{current_name}' を削除しました")

            self.refresh_saved_queries()
            self._update_bookmark_icon(query)
            close_dlg(e)

        dlg = ft.AlertDialog(
            title=ft.Text("ブックマークの管理"),
            content=ft.Text(f"「{current_name}」をブックマークから削除しますか？"),
            actions=[
                ft.TextButton("キャンセル", on_click=close_dlg),
                ft.TextButton("削除", on_click=delete_click, style=ft.ButtonStyle(color=ft.Colors.RED)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    async def _handle_search(self):
        #検索を実行したらサジェストは隠す
        self.suggest_container.visible = False
        self.suggest_container.update()

        # 検索窓のテキストを取得
        query = self.search_input.value

        # 検索実行時にもアイコン状態を更新（不要文字を消してEnterを押した時用）
        self._update_bookmark_icon(query)

        # 保存済みのクエリなら、DBの使用時刻（last_used_at）を更新
        if query in self.saved_queries:
            bm_name = self.saved_queries[query]
            bm = self.db.get_bookmark_by_name(bm_name)
            if bm:
                self.db.update_bookmark_usage(bm['id'])

        # 上位(app.py)に検索クエリを渡して処理を任せる
        # 万が一queryがNoneだった場合にエラーを防ぐため空文字を渡す
        await self.on_search_callback(query or "")