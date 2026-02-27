import flet as ft
import os

class ImageGallery:
    def __init__(self, on_image_click_callback, on_page_change_callback=None):
        # 画像がクリックされたときに上位(app.py)のビューアを開くためのコールバック
        self.on_image_click_callback = on_image_click_callback
        self.on_page_change_callback = on_page_change_callback
        
        self.base_columns = 3 #ピンチ操作基準用の変数
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
                self.slider_row, #スライダーを表示
            ],
            expand=True,
            spacing=0,
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

    # app.pyから検索結果を受け取って画面を描画する関数
    def update_gallery(self, results, current_page=1, total_pages=1):
        #グリッドをクリア
        self.images_grid.controls.clear()

        for row in results:
            #DBには絶対パスや相対パスが入っている可能性があるため、ファイル名だけ抽出
            #例: "data/thumbnails/123.webp" -> "123.webp"
            if row['thumbnail_path']:
                filename = os.path.basename(row['thumbnail_path'])
                
                #assets_dir="data" なので、Webからは "/thumbnails/filename" でアクセス
                web_image_src = f"/thumbnails/{filename}"
                
                #画像コンテナ（将来的にクリックイベントを仕込む場所）
                img_container = ft.Container(
                    content=ft.Image(
                        src=web_image_src,
                        fit="cover",
                        repeat="noRepeat",
                        border_radius=ft.border_radius.all(8),
                    ),
                    #クリック時のデータを持たせる
                    data=row,
                    on_click=self.on_image_click_callback, 
                )
                self.images_grid.controls.append(img_container)
        
        self.page_text.value = f"{current_page} / {max(1, total_pages)}"
        self.prev_btn.disabled = (current_page <= 1)
        self.next_btn.disabled = (current_page >= total_pages)