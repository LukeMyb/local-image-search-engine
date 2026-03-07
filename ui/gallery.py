import flet as ft
import os

class ImageGallery:
    def __init__(self, page, on_image_click_callback, on_style_create_callback, on_page_change_callback=None, on_swipe_right_callback=None, on_selection_change_callback=None):
        #コールバック
        self.page = page
        self.on_image_click_callback = on_image_click_callback
        self.on_style_create_callback = on_style_create_callback
        self.on_page_change_callback = on_page_change_callback
        self.on_swipe_right_callback = on_swipe_right_callback
        self.on_selection_change_callback = on_selection_change_callback
        
        self.base_columns = 3 #ピンチ操作基準用の変数

        # 選択モード用の状態管理
        self.is_selection_mode = False 
        self.selected_images = set() # 選択された画像のIDを保存
        self.current_results_ref = [] # 再描画用に保持
        self.current_page = 1
        self.total_pages = 1

        self._build_ui()

    def _build_ui(self):
        #画像を表示するグリッドビュー
        #runs_countではなくmax_extentを使うことで、PC/スマホ両方で適切な列数に
        self.images_grid = ft.GridView(
            expand=True,
            runs_count=3,            #最低5列は確保（お好みで max_extent=150 などに変更可）
            child_aspect_ratio=1.0,  #正方形 (1:1)
            spacing=5,               #タイル間の隙間
            run_spacing=5,
        )

        #ズームスライダー
        self.zoom_slider = ft.Slider(
            min=3,
            max=6,
            divisions=3,
            label="{value}",
            expand=True,
            on_change=self.on_slider_change
        )

        #グリッドをGestureDetectorで包む
        #グリッドの上でのタッチ操作を検知できるように
        self.gallery_area = ft.GestureDetector(
            content=self.images_grid,
            on_scale_start=self.on_scale_start,
            on_scale_update=self.on_scale_update,
            on_scale_end=self.on_scale_end,
            expand=True, # 画面いっぱいに広げる
        )

        #スライダー行
        self.slider_row = ft.Row(
            [
                ft.Icon("photo_size_select_small", size=16),
                self.zoom_slider,
                ft.Icon("photo_size_select_actual", size=16),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            height=30,
        )

        self.prev_btn = ft.IconButton(
            icon=ft.Icons.NAVIGATE_BEFORE, 
            on_click=self.on_prev_click,
            disabled=True
        )
        self.next_btn = ft.IconButton(
            icon=ft.Icons.NAVIGATE_NEXT, 
            on_click=self.on_next_click,
            disabled=True
        )
        self.page_text = ft.Text("1 / 1", size=16)
        
        self.pagination_row = ft.Row(
            [self.prev_btn, self.page_text, self.next_btn],
            alignment=ft.MainAxisAlignment.CENTER,
            height=40,
        )

        # app.pyに渡すために、ギャラリー部分とスライダー部分を縦にまとめたもの
        self.view = ft.Column(
            [
                self.gallery_area,
                self.pagination_row,
                # slider_row を Container で包み、下部にだけ 20px の余白を強制的に作る
                ft.Container(
                    content=self.slider_row,
                    padding=ft.padding.only(bottom=20) 
                ),
            ],
            expand=True,
            spacing=0,
        )

        # 選択モード用UI
        self.selection_mode_btn = ft.IconButton(
            icon=ft.Icons.CHECK_BOX_OUTLINE_BLANK,
            tooltip="選択モード切替",
            on_click=self.toggle_selection_mode
        )

        # 作成ボタンとバナー
        self.create_style_btn = ft.ElevatedButton(
            "この絵柄でタグを作成",
            icon=ft.Icons.BRUSH,
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE),
            on_click=self.show_style_create_dialog
        )
        self.selection_banner = ft.Container(
            content=ft.Row([
                ft.Text(value="", size=16, weight=ft.FontWeight.BOLD),
                self.create_style_btn
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor=ft.Colors.ON_SURFACE_VARIANT,
            padding=10,
            visible=False,
        )

    # ヘルパーメソッド
    def _get_selection_overlay(self, image_id):
        if not self.is_selection_mode:
            return ft.Container()
        
        if image_id in self.selected_images:
            return ft.Container(
                bgcolor=ft.Colors.with_opacity(0.4, ft.Colors.BLUE),
                border=ft.border.all(3, ft.Colors.BLUE_400),
                border_radius=8,
                content=ft.Icon(ft.Icons.CHECK_CIRCLE, color="white", size=30),
                alignment=ft.Alignment(0, 0),
            )
        else:
            return ft.Container(
                border=ft.border.all(1, ft.Colors.WHITE_54),
                border_radius=8,
            )

    def on_prev_click(self, e):
        if self.on_page_change_callback:
            self.on_page_change_callback(-1)

    def on_next_click(self, e):
        if self.on_page_change_callback:
            self.on_page_change_callback(1)

    #スライダーを動かした時
    def on_slider_change(self, e):
        val = int(e.control.value)
        
        self.images_grid.runs_count = val
        self.base_columns = val #次のピンチ操作のために基準値を更新

        self.images_grid.update()

    def on_scale_start(self, e):
        self.base_columns = self.images_grid.runs_count #現在のグリッドの状態を基準にする

    def on_scale_update(self, e):
        #画像を拡大(scale > 1)したい = 列数を減らしたい -> 割り算
        #画像を縮小(scale < 1)したい = 列数を増やしたい -> 割り算
        new_cols = self.base_columns / e.scale
        
        #制限 (小さすぎたり大きすぎたりしないように)
        if new_cols < 3: new_cols = 3
        if new_cols > 6: new_cols = 6

        #int(切り捨て) ではなく round(四捨五入) を使う
        #これで 3.5 以上なら 4列 になるので直感と合う
        int_cols = int(round(new_cols))
        
        #列数が変わったタイミングだけ画面更新（軽量化）
        if self.images_grid.runs_count != int_cols:
            self.images_grid.runs_count = int_cols
            self.images_grid.update()

        #スライダーの位置は滑らかに追従させる
        self.zoom_slider.value = new_cols 
        self.zoom_slider.update()

    #ピンチ終了時の処理を追加
    #指を離した瞬間にスライダーを「整数」の位置にピタッと吸着させる
    def on_scale_end(self, e):
        # 現在のグリッドの列数（整数）にスライダーを合わせる
        final_cols = self.images_grid.runs_count
        self.zoom_slider.value = final_cols
        self.zoom_slider.update()
        
        # 次の操作のために基準値を更新
        self.base_columns = final_cols

        # --- スワイプ検知 ---
        # X軸の速度がY軸より大きく、かつプラス方向なら右スワイプと判定
        vx = e.velocity.x
        vy = e.velocity.y

        if abs(vx) > abs(vy) and vx > 100: # 100は適度なスワイプ速度の閾値
            if self.on_swipe_right_callback:
                self.on_swipe_right_callback()

    # --- ここから選択モード関連のメソッド群 ---
    def toggle_selection_mode(self, e=None):
        self.is_selection_mode = not self.is_selection_mode
        self.selected_images.clear()
        
        self.selection_mode_btn.icon = ft.Icons.CHECK_BOX if self.is_selection_mode else ft.Icons.CHECK_BOX_OUTLINE_BLANK
        self.selection_mode_btn.icon_color = ft.Colors.BLUE if self.is_selection_mode else None
        self.selection_mode_btn.update()
        
        self.update_selection_banner()
        # 既存のコントロールを書き換えることでスクロール維持
        for control in self.images_grid.controls:
            img_id = control.data['id']
            control.content.controls[2] = self._get_selection_overlay(img_id)
        
        self.images_grid.update()

    def update_selection_banner(self):
        count = len(self.selected_images)
        if self.is_selection_mode:
            self.selection_banner.visible = True
            self.selection_banner.content.controls[0].value = f"{count}枚 選択中"
            self.create_style_btn.disabled = (count == 0)
        else:
            self.selection_banner.visible = False
        self.page.update()

    def show_style_create_dialog(self, e):
        name_input = ft.TextField(label="絵柄の名前（例: my_art）", prefix=ft.Text("style:"))
        
        def close_dlg(e):
            dlg.open = False
            self.page.update()

        def save_style(e):
            style_name = "style:" + name_input.value.strip()
            if style_name == "style:": return 
            
            # 親(app.py)に処理を委譲（名前とIDリストを渡す）
            if self.on_style_create_callback:
                self.on_style_create_callback(style_name, list(self.selected_images))
            
            self.toggle_selection_mode()
            close_dlg(e)

        dlg = ft.AlertDialog(
            title=ft.Text("絵柄タグを作成", size=16),
            content=name_input,
            actions=[
                ft.TextButton("キャンセル", on_click=close_dlg),
                ft.TextButton("作成", on_click=save_style),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    # app.pyから検索結果を受け取って画面を描画する関数
    def update_gallery(self, results, current_page=1, total_pages=1):
        # 状態を保持
        self.current_results_ref = results
        self.current_page = current_page
        self.total_pages = total_pages

        #既存のGridViewを破棄し、スクロールの記憶を持たない全く新しいGridViewを作成する
        new_grid = ft.GridView(
            expand=True,
            runs_count=self.images_grid.runs_count, # ユーザーが設定した現在の列数は引き継ぐ
            child_aspect_ratio=1.0,
            spacing=5,
            run_spacing=5,
        )

        for row in results:
            #ファイル名だけ抽出
            if row['thumbnail_path']:
                filename = os.path.basename(row['thumbnail_path'])
                web_image_src = f"/thumbnails/{filename}"

                # お気に入りアイコン
                # DBのis_favoriteが1の場合のみ、白いハートを表示する
                favorite_badge = ft.Container()
                if row.get('is_favorite') == 1:
                    favorite_badge = ft.Container(
                        content=ft.Icon(ft.Icons.FAVORITE, color="white", size=14),
                        right=5,   # 右端からの距離
                        bottom=5, # 下端からの距離
                        # アイコンを見やすくするために、背後にわずかな影（ドロップシャドウ）をつける
                        shadow=ft.BoxShadow(blur_radius=4, color="black38"), 
                    )

                # 選択モード時のチェックマークとオーバーレイ
                selection_overlay = ft.Container()
                image_id = row['id']
                is_selected = image_id in self.selected_images

                if self.is_selection_mode:
                    if is_selected:
                        # 選択中：青い半透明のフィルターとチェックマーク
                        selection_overlay = ft.Container(
                            bgcolor=ft.Colors.with_opacity(0.4, ft.Colors.BLUE),
                            border=ft.border.all(3, ft.Colors.BLUE_400),
                            border_radius=8,
                            content=ft.Icon(ft.Icons.CHECK_CIRCLE, color="white", size=30),
                            alignment=ft.Alignment(0, 0),
                        )
                    else:
                        # 未選択：薄い枠線のみ
                        selection_overlay = ft.Container(
                            border=ft.border.all(1, ft.Colors.WHITE_54),
                            border_radius=8,
                        )

                # クリックと長押しのハンドラー
                def handle_click(e, r=row):
                    if self.is_selection_mode:
                        # 選択の切り替え
                        img_id = r['id']
                        if img_id in self.selected_images:
                            self.selected_images.remove(img_id)
                        else:
                            self.selected_images.add(img_id)

                        # 選択枚数の表示（バナー）を更新
                        self.update_selection_banner()

                        # update_galleryを呼ばず、この画像(e.control)のオーバーレイだけを差し替える
                        e.control.content.controls[2] = self._get_selection_overlay(img_id)
                        e.control.update()
                        
                        # 親(app.py)に通知
                        if self.on_selection_change_callback:
                            self.on_selection_change_callback(self.selected_images)
                    else:
                        self.on_image_click_callback(e)

                def handle_long_press(e, r=row):
                    if not self.is_selection_mode:
                        # 長押しで選択モードに突入
                        self.is_selection_mode = True
                        self.selected_images.add(r['id'])

                        # 選択枚数の表示（バナー）を更新
                        self.update_selection_banner()

                        #update_gallery は呼ばず、自身だけ更新
                        e.control.content.controls[2] = self._get_selection_overlay(r['id'])
                        e.control.update()
                        
                        if self.on_selection_change_callback:
                            self.on_selection_change_callback(self.selected_images)
                
                #画像コンテナ
                img_container = ft.Container(
                    content=ft.Stack(
                        [
                            ft.Image(
                                src=web_image_src,
                                fit="cover",
                                repeat="noRepeat",
                                border_radius=ft.border_radius.all(8),
                            ),
                            favorite_badge, # お気に入りならここにハートが重なる
                            selection_overlay,
                        ]
                    ),
                    #クリック時のデータを持たせる
                    data=row,
                    on_click=handle_click, 
                    on_long_press=handle_long_press,
                )
                new_grid.controls.append(img_container)
        
        #GestureDetectorの中身を新しいGridViewに丸ごと差し替える
        self.images_grid = new_grid
        self.gallery_area.content = self.images_grid
        
        self.page_text.value = f"{current_page} / {max(1, total_pages)}"
        self.prev_btn.disabled = (current_page <= 1)
        self.next_btn.disabled = (current_page >= total_pages)

        #全体を再描画
        self.gallery_area.update()
        self.pagination_row.update()