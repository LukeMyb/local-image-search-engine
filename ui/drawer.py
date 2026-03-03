import flet as ft
import asyncio

class BookmarkDrawer:
    def __init__(self, page, db, search_bar):
        self.page = page
        self.db = db
        self.search_bar = search_bar # 検索窓と連動させるために受け取る
        self.view = ft.NavigationDrawer(on_dismiss=self.on_dismiss)
        
        self.filter_input = ft.TextField(
            label="ブックマークを検索",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.on_filter_change,
            expand=True
        )
        
        self.bookmark_list_container = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
        self._build_ui()

    def _build_ui(self):
        self.view.controls = [
            ft.Container(
                padding=ft.padding.only(top=20, left=15, right=15, bottom=10),
                content=self.filter_input
            ),
            ft.Divider(thickness=1, color="white24"),
            self.bookmark_list_container
        ]

    def show(self):
        # ドロワーをページに登録する
        self.page.drawer = self.view
        self.page.update()

        # 中身を更新して開く
        self.filter_input.value = ""
        self.refresh_list()
        
        self.view.open = True
        self.page.update()

    def on_dismiss(self, e):
        pass

    def on_filter_change(self, e):
        self.refresh_list()

    def refresh_list(self):
        filter_text = self.filter_input.value or ""
        # db.pyのget_bookmarksはフィルター入力があればname順、空欄ならlast_used_at順で返します
        bookmarks = self.db.get_bookmarks(filter_text)
        
        self.bookmark_list_container.controls.clear()

        if not bookmarks:
            self.bookmark_list_container.controls.append(
                ft.Container(
                    padding=20,
                    content=ft.Text("ブックマークがありません", color="white54", text_align=ft.TextAlign.CENTER)
                )
            )
        else:
            for bm in bookmarks:
                delete_btn = ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color="red400",
                    tooltip="削除",
                    on_click=lambda e, b=bm: self.confirm_delete(b)
                )
                
                item = ft.ListTile(
                    title=ft.Text(bm['name']),
                    subtitle=ft.Text(bm['query'], size=12, color="white54", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    trailing=delete_btn,
                    on_click=lambda e, q=bm['query']: self.on_select(q)
                )
                self.bookmark_list_container.controls.append(item)
        
        self.view.update()

    def on_select(self, query):
        #現在の検索窓の内容を取得（Noneの場合は空文字にする）
        current_query = self.search_bar.search_input.value or ""

        #ドロワーを閉じる
        self.view.open = False
        self.page.drawer = None
        self.page.update()

        #選択したクエリが現在の検索窓の内容と完全に一致する場合は、検索をスキップ
        if current_query == query: return

        # SearchBarの入力欄を上書き
        self.search_bar.search_input.value = query
        # アイコンの状態も同期させる
        self.search_bar._update_bookmark_icon(query)
        self.search_bar.view.update()
        
        # _handle_search() を呼び出して検索処理＋履歴時刻の更新を走らせる
        asyncio.create_task(self.search_bar._handle_search())

    def confirm_delete(self, bm):
        def close_dlg(e):
            dlg.open = False
            self.page.update()

        def delete_click(e):
            # DBから削除
            self.db.delete_bookmark(bm['id'])
            # ドロワーの一覧を再描画
            self.refresh_list()
            # SearchBar側のメモリとアイコンも更新して同期
            self.search_bar.refresh_saved_queries()
            self.search_bar._update_bookmark_icon(self.search_bar.search_input.value)
            close_dlg(e)

        dlg = ft.AlertDialog(
            title=ft.Text("ブックマークの削除"),
            content=ft.Text(f"「{bm['name']}」を削除しますか？"),
            actions=[
                ft.TextButton("キャンセル", on_click=close_dlg),
                ft.TextButton("削除", on_click=delete_click, style=ft.ButtonStyle(color=ft.Colors.RED)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()