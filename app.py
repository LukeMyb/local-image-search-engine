import flet as ft
import asyncio
import os
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
    page.padding = 10 #余白

    #スマホ表示時のスクロール等の挙動をネイティブに近づける
    page.scroll = "adaptive"

    #Loading
    status_text = ft.Text("Loading...", color="green", size=20)

    #検索窓
    search_input = ft.TextField(
        hint_text="タグを入力して検索", 
        expand=True, 
        on_submit=lambda e: asyncio.create_task(on_search(e)) #エンターキーで検索
    )
    
    #画像を表示するグリッドビュー
    #runs_countではなくmax_extentを使うことで、PC/スマホ両方で適切な列数に
    images_grid = ft.GridView(
        expand=True,
        runs_count=5,            #最低5列は確保（お好みで max_extent=150 などに変更可）
        max_extent=180,          #タイルの最大幅
        child_aspect_ratio=1.0,  #正方形 (1:1)
        spacing=5,               #タイル間の隙間
        run_spacing=5,
    )

    #ズームスライダー
    zoom_slider = ft.Slider(
        min=60,
        max=180,
        value=180,
        label="{value}",
        expand=True,
    )

    #スライダーを動かした時
    def on_slider_change(e):
        images_grid.max_extent = e.control.value
        images_grid.update()

    zoom_slider.on_change = on_slider_change

    #ピンチ操作開始時のサイズを一時保存
    base_scale_size = 180

    def on_scale_start(e):
        nonlocal base_scale_size
        #操作開始時点の現在のサイズを記録
        base_scale_size = images_grid.max_extent

    def on_scale_update(e):
        #e.scale: 指を広げた倍率 (1.0が基準、2.0なら2倍、0.5なら半分)
        new_size = base_scale_size * e.scale
        
        #制限 (小さすぎたり大きすぎたりしないように)
        if new_size < 60: new_size = 60
        if new_size > 180: new_size = 180
        
        #グリッドに適用して更新
        images_grid.max_extent = new_size
        images_grid.update()

    #グリッドをGestureDetectorで包む
    #グリッドの上でのタッチ操作を検知できるように
    gallery_area = ft.GestureDetector(
        content=images_grid,
        on_scale_start=on_scale_start,
        on_scale_update=on_scale_update,
        expand=True, # 画面いっぱいに広げる
    )

    #ヘッダー部分(検索窓とステータスメッセージ)
    header = ft.Row(
        [
            search_input,
            ft.IconButton(icon=ft.Icons.SEARCH, on_click=lambda e: asyncio.create_task(on_search(e))),
        ]
    )

    #スライダー行
    slider_row = ft.Row(
        [
            ft.Icon("photo_size_select_small", size=16),
            zoom_slider,
            ft.Icon("photo_size_select_actual", size=16),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )

    #レイアウト
    page.add(
        ft.Column(
            [
                status_text,
                header,
                slider_row, #スライダーを表示
                gallery_area,
            ],
            expand=True, #画面下まで広げる
        )
    )

    #ロード
    searcher = await initialize_engine(page, status_text)

    async def on_search(e):
        query = search_input.value
        if not query: return #検索窓が空なら何もしない

        #ステータスメッセージの更新
        status_text.value = "検索中..."
        page.update()

        #非同期で検索を実行するとUIが固まらない（今回は簡易的に同期実行）
        results = searcher.search(query, limit=50)

        #グリッドをクリア
        images_grid.controls.clear()

        if not results:
            status_text.value = "見つかりませんでした。"
        else:
            status_text.value = f"ヒット: {len(results)}件"

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
                            border_radius=ft.border_radius.all(8), # 角丸
                        ),
                        # クリック時のデータを持たせる
                        #data=row,
                        #on_click=on_image_click, 
                    )
                    images_grid.controls.append(img_container)

        page.update()

if __name__ == "__main__":
    ft.app(
        target=main, 
        view=ft.AppView.WEB_BROWSER, 
        port=8000, 
        assets_dir="data", 
        host="0.0.0.0" 
    )