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
    page.padding = 6 #余白

    #Loading
    status_text = ft.Text("Loading...", color="green", size=20)

    #画像を詳細表示
    detail_image = ft.Image(
        src="",
        fit="contain", #画面に収まるように表示
        repeat="noRepeat",
        width=None,
        height=None,
        expand=True,
    )

    #ビュアーを閉じる関数
    async def close_viewer(e):
        #透明にする
        detail_view.opacity = 0
        detail_view.update()
        
        #アニメーションが終わるまで待つ
        await asyncio.sleep(0.3)
        
        #完全に非表示にする
        detail_view.visible = False
        detail_view.update()

    # ビューア本体（全画面オーバーレイ）
    detail_view = ft.Container(
        visible=False, # 最初は隠しておく
        opacity=0,          #最初は透明
        animate_opacity=300, #300ミリ秒かけて変化させる
        bgcolor="#000000", # 背景は真っ黒
        alignment=ft.Alignment(0, 0),
        expand=True,
        # Stackを使って「画像」の上に「閉じるボタン」を重ねる
        content=ft.Stack(
            [
                # 画像部分（クリックで閉じるようにする）
                ft.Container(
                    content=detail_image,
                    alignment=ft.Alignment(0, 0),
                    expand=True,
                ),
                
                # 右上の閉じるボタン
                ft.SafeArea(
                    ft.Container(
                        content=ft.IconButton(
                            icon=ft.Icons.CLOSE, 
                            icon_color="white", 
                            icon_size=30,
                            on_click=close_viewer,
                            bgcolor="#8A000000", # ボタン背景を半透明に
                        ),
                        alignment=ft.Alignment(1, -1),
                        padding=20,
                    )
                )
            ],
            expand=True,
        )
    )

    # アプリの最前面レイヤーにビューアを追加
    page.overlay.append(detail_view)

    #画像クリック時の処理
    async def on_image_click(e):
        #クリックされた画像の情報(row)を取得
        row = e.control.data
        if not row: return

        raw_path = row.get('file_path', '') #DBに入っているパス
        filename = os.path.basename(raw_path)
        high_res_src = f"/images/{filename}" 
        
        #もし元画像パスが不明なら、とりあえずサムネイルを表示する救済措置
        if not raw_path:
             high_res_src = f"/thumbnails/{os.path.basename(row.get('thumbnail_path'))}"

        #ビュアーの画像を更新して表示
        detail_image.src = high_res_src

        #まず「透明な状態」で存在させる
        detail_view.visible = True
        detail_view.opacity = 0
        detail_view.update()
        
        #透明度を1にしてフェードイン開始
        detail_view.opacity = 1
        detail_view.update()

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
        runs_count=3,            #最低5列は確保（お好みで max_extent=150 などに変更可）
        child_aspect_ratio=1.0,  #正方形 (1:1)
        spacing=5,               #タイル間の隙間
        run_spacing=5,
    )

    #ズームスライダー
    zoom_slider = ft.Slider(
        min=3,
        max=6,
        divisions=3,
        label="{value}",
        expand=True,
    )

    #ピンチ操作基準用の変数
    base_columns = 3

    #スライダーを動かした時
    def on_slider_change(e):
        nonlocal base_columns
        val = int(e.control.value)
        
        images_grid.runs_count = val
        base_columns = val #次のピンチ操作のために基準値を更新

        images_grid.update()
    zoom_slider.on_change = on_slider_change

    def on_scale_start(e):
        nonlocal base_columns
        base_columns = images_grid.runs_count #現在のグリッドの状態を基準にする

    def on_scale_update(e):
        #画像を拡大(scale > 1)したい = 列数を減らしたい -> 割り算
        #画像を縮小(scale < 1)したい = 列数を増やしたい -> 割り算
        new_cols = base_columns / e.scale
        
        #制限 (小さすぎたり大きすぎたりしないように)
        if new_cols < 3: new_cols = 3
        if new_cols > 6: new_cols = 6

        #int(切り捨て) ではなく round(四捨五入) を使う
        #これで 3.5 以上なら 4列 になるので直感と合う
        int_cols = int(round(new_cols))
        
        #列数が変わったタイミングだけ画面更新（軽量化）
        if images_grid.runs_count != int_cols:
            images_grid.runs_count = int_cols
            images_grid.update()

        #スライダーの位置は滑らかに追従させる
        zoom_slider.value = new_cols 
        zoom_slider.update()

    #ピンチ終了時の処理を追加
    #指を離した瞬間にスライダーを「整数」の位置にピタッと吸着させる
    def on_scale_end(e):
        nonlocal base_columns
        # 現在のグリッドの列数（整数）にスライダーを合わせる
        final_cols = images_grid.runs_count
        zoom_slider.value = final_cols
        zoom_slider.update()
        
        # 次の操作のために基準値を更新
        base_columns = final_cols

    #グリッドをGestureDetectorで包む
    #グリッドの上でのタッチ操作を検知できるように
    gallery_area = ft.GestureDetector(
        content=images_grid,
        on_scale_start=on_scale_start,
        on_scale_update=on_scale_update,
        on_scale_end=on_scale_end,
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
        height=30,
    )

    #レイアウト
    page.add(
        ft.Column(
            [
                status_text,
                header,
                gallery_area,
                slider_row, #スライダーを表示
            ],
            expand=True, #画面下まで広げる
            spacing=4,
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
        results = searcher.search(query, limit=5000)

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
                        #クリック時のデータを持たせる
                        data=row,
                        on_click=on_image_click, 
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