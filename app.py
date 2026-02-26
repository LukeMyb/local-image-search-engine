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
    ANIM_DURATION = 100 #アニメーションの設定（ミリ秒）
    current_results = [] #検索結果のリスト
    current_index = 0 #現在表示中の画像のインデックス
    is_animating = False

    #ページ全体の設定
    page.title = "Local image searcher"
    page.theme_mode = "dark"
    page.padding = 6 #余白

    #Loading
    status_text = ft.Text("Loading...", color="green", size=20)

    #ダミー画像
    dummy_src = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

    # 共通の画像設定を作成する関数
    def create_viewer_image(initial_offset_x):
        return ft.Image(
            src=dummy_src,
            fit="contain",
            expand=True,
            # 位置のアニメーション設定
            offset=ft.Offset(initial_offset_x, 0),
            animate_offset=ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
            # 閉じる時のアニメーション用
            animate_scale=ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
            animate_opacity=ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
        )

    img_prev = create_viewer_image(-1) # 左に配置
    img_curr = create_viewer_image(0)  # 中央に配置
    img_next = create_viewer_image(1)  # 右に配置

    # 2. 画像パスを取得するヘルパー関数
    def get_image_src(index):
        if 0 <= index < len(current_results):
            row = current_results[index]
            raw_path = row.get('file_path', '')
            filename = os.path.basename(raw_path)
            if raw_path:
                return f"/images/{filename}"
            else:
                return f"/thumbnails/{os.path.basename(row.get('thumbnail_path'))}"
        return dummy_src
    
    # 3. 3枚の画像をセットして位置をリセットする関数（重要）
    def reset_images_position(index):
        # アニメーションを一時的に無効化（瞬間移動させるため）
        img_prev.animate_offset = None
        img_curr.animate_offset = None
        img_next.animate_offset = None

        # 3枚の画像の中身を更新（プリロード）
        img_prev.src = get_image_src(index - 1)
        img_curr.src = get_image_src(index)
        img_next.src = get_image_src(index + 1)

        # 位置を定位置（左・中・右）に戻す
        img_prev.offset = ft.Offset(-1, 0)
        img_curr.offset = ft.Offset(0, 0)
        img_next.offset = ft.Offset(1, 0)
        
        # 拡大率などもリセット
        img_curr.scale = 1
        img_curr.opacity = 1

        img_prev.update()
        img_curr.update()
        img_next.update()

        # アニメーション設定を復元
        anim = ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT)
        img_prev.animate_offset = anim
        img_curr.animate_offset = anim
        img_next.animate_offset = anim

    # 4. スライド移動のアニメーション処理
    async def slide_next():
        nonlocal current_index, img_prev, img_curr, img_next, is_animating

        if is_animating or current_index >= len(current_results) - 1: return

        is_animating = True #ロック開始

        # アニメーション開始：中→左、右→中
        img_curr.offset = ft.Offset(-1, 0)
        img_next.offset = ft.Offset(0, 0)
        img_curr.update()
        img_next.update()

        # 移動完了を待つ
        await asyncio.sleep(ANIM_DURATION / 1000)

        current_index += 1 #インデックスを戻す
        update_indicator()

        recycle_img = img_prev
        # アニメーションを切って右端へ瞬間移動
        recycle_img.animate_offset = None
        recycle_img.offset = ft.Offset(1, 0)
        # 中身を「次の次」の画像に更新 (先読み)
        recycle_img.src = get_image_src(current_index + 1)
        # 念のため状態リセット
        recycle_img.scale = 1
        recycle_img.opacity = 1
        recycle_img.update()

        # アニメーション設定を戻す
        recycle_img.animate_offset = ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT)

        # 元Curr -> 新Prev (左へ行ったやつ)
        # 元Next -> 新Curr (中央に来たやつ)
        # 元Prev -> 新Next (右へ回したやつ)
        img_prev = img_curr
        img_curr = img_next
        img_next = recycle_img

        is_animating = False #ロック解除

    async def slide_prev():
        nonlocal current_index, img_prev, img_curr, img_next, is_animating
        
        if is_animating or current_index <= 0: return

        is_animating = True #ロック開始

        # アニメーション開始：中→右、左→中
        img_curr.offset = ft.Offset(1, 0)
        img_prev.offset = ft.Offset(0, 0)
        img_curr.update()
        img_prev.update()

        # 移動完了を待つ
        await asyncio.sleep(ANIM_DURATION / 1000)

        current_index -= 1 #インデックスを戻す
        update_indicator()

        recycle_img = img_next
        # アニメーションを切って左端へ瞬間移動
        recycle_img.animate_offset = None
        recycle_img.offset = ft.Offset(-1, 0)

        # 中身を「前の前」の画像に更新 (先読み)
        recycle_img.src = get_image_src(current_index - 1)
        recycle_img.scale = 1
        recycle_img.opacity = 1
        recycle_img.update()

        # アニメーション設定を戻す
        recycle_img.animate_offset = ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT)

        # 元Next -> [リサイクル] -> 新Prev
        # 元Curr -> 新Next (右へ行ったやつ)
        # 元Prev -> 新Curr (中央に来たやつ)
        img_next = img_curr
        img_curr = img_prev
        img_prev = recycle_img

        is_animating = False #ロック解除

    #ビュアーを閉じる関数
    async def close_viewer(e):
        #小さくしながら透明にする
        img_curr.scale = 0
        img_curr.opacity = 0
        detail_view.opacity = 0
        page.update()
        
        #アニメーションが終わるまで待つ
        await asyncio.sleep(ANIM_DURATION / 1000)
        
        #完全に非表示にする
        detail_view.visible = False
        detail_view.update()

    #閉じるボタンのラッパー（アニメーション用）
    close_btn_wrapper = ft.Container(
        content=ft.IconButton(
            icon=ft.Icons.CLOSE, 
            icon_color="white", 
            icon_size=30,
            on_click=lambda e: asyncio.create_task(close_viewer(e)),
            bgcolor="#8A000000", #ボタン背景を半透明に
        ),
        top=35,   # 画面上端からの距離（SafeAreaの代わり）
        right=20, # 右端からの距離
        
        #初期位置は画面外（上）へ飛ばしておく
        #y=-2 は「自分の高さの2倍分、上に移動」という意味です
        offset=ft.Offset(0, -2),
        
        #位置のアニメーション設定 (滑らかに移動)
        animate_offset=ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
    )

    #UI（閉じるボタン）の出し入れを切り替える関数
    def toggle_ui(e):
        #現在の位置を確認して切り替え
        if close_btn_wrapper.offset.y == 0:
            close_btn_wrapper.offset = ft.Offset(0, -2) #表示中なら -> 上に隠す (y=-2)
            indicator_container.offset = ft.Offset(0, 2) #下へ隠す
            indicator_container.opacity = 0
        else:
            close_btn_wrapper.offset = ft.Offset(0, 0) #隠れてるなら -> 定位置に戻す (y=0) ＝ ニュッと出す
            indicator_container.offset = ft.Offset(0, 0)
            indicator_container.opacity = 1
        
        close_btn_wrapper.update()
        indicator_container.update()

    #ページ番号を表示するテキスト
    page_counter = ft.Text(
        "0 / 0",
        color="white",
        size=16,
        weight=ft.FontWeight.BOLD,
    )

    #テキストを画面下部に配置するためのラッパー
    indicator_container = ft.Container(
        bottom=40, # 下から40pxの位置に固定
        left=0,    # 左右を0にして
        right=0,   # widthを広げずに中央寄せにする準備

        # 内部のテキストだけを中央に寄せる
        content=ft.Row([page_counter], alignment=ft.MainAxisAlignment.CENTER),

        # 閉じるボタンと同じアニメーション設定
        offset=ft.Offset(0, 2), # 初期状態は画面外（下）
        animate_offset=ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
        opacity=0,
        animate_opacity=ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
    )

    #現在のインデックスと総件数を計算して反映
    def update_indicator():
        total = len(current_results)
        current = current_index + 1 if total > 0 else 0
        page_counter.value = f"{current} / {total}"
        page_counter.update()

    # タップされた位置に応じて処理を振り分ける関数
    def handle_tap(e):
        #画面の横幅を取得
        width = page.width
        #左右 20% ずつをタップエリアとして定義
        edge_zone = page.width * 0.2

        if e.local_position.x < edge_zone:
            #左端なら「前へ」
            asyncio.create_task(slide_prev())
        elif e.local_position.x > width - edge_zone:
            #右端なら「次へ」
            asyncio.create_task(slide_next())
        else:
            #中央付近なら「UIの出し入れ」
            toggle_ui(None)

    #スワイプ操作を検知する関数
    def on_pan_end(e):
        #左右の移動速度(絶対値)が上下の移動速度より大きい場合 -> 横スワイプ（画像切り替え）
        if abs(e.velocity.x) > abs(e.velocity.y):
            #velocity_x がプラスなら右スワイプ（前の画像）、マイナスなら左スワイプ（次の画像）
            #感度調整: 速度が小さい場合(誤操作)は無視する
            if e.velocity.x > 100: 
                #前の画像へ (Previous)
                asyncio.create_task(slide_prev())
                    
            elif e.velocity.x < -100:
                #次の画像へ (Next)
                asyncio.create_task(slide_next())

        else: #上下の動きの方が大きい場合
            #velocity.y がプラスなら下スワイプ
            if e.velocity.y > 400: #感度は400くらいが誤爆しにくくてお勧め
                asyncio.create_task(close_viewer(None))

    detail_view = ft.Container(
        visible=False, # 最初は隠しておく
        animate_opacity=ANIM_DURATION, #ANIM_DURATIONミリ秒かけて変化させる
        bgcolor="#000000", #背景は透明→黒(初期値は黒)
        alignment=ft.Alignment(0, 0),
        expand=True,
        content=ft.Stack(
            [
                #レイヤー1: 画像操作用のジェスチャー（背景全体）
                ft.GestureDetector(
                    on_tap_down=handle_tap, #タップ位置によって操作切り替え
                    on_pan_end=on_pan_end, #スワイプで画像切り替え
                    content=ft.Stack([
                        ft.Container(content=img_prev, alignment=ft.Alignment(0,0), expand=True),
                        ft.Container(content=img_curr, alignment=ft.Alignment(0,0), expand=True),
                        ft.Container(content=img_next, alignment=ft.Alignment(0,0), expand=True),
                    ]),
                    expand=True,
                ),
                close_btn_wrapper,
                indicator_container,
            ],
            expand=True,
        )
    )

    # アプリの最前面レイヤーにビューアを追加
    page.overlay.append(detail_view)

    #画像クリック時の処理
    async def on_image_click(e):
        nonlocal current_index, is_animating

        is_animating = False #フラグをリセット

        #クリックされた画像の情報(row)を取得
        row = e.control.data
        if not row: return

        #クリックされた画像がリストの何番目かを探して記憶する
        try:
            current_index = current_results.index(row)
        except ValueError:
            current_index = 0

        reset_images_position(current_index)
        update_indicator()

        #準備：画像URLをセットし、最初は「透明・最小」にする
        img_curr.scale = 0
        img_curr.opacity = 0
        detail_view.opacity = 0

        # 閉じるボタンとインディケータを画面外へ
        close_btn_wrapper.offset = ft.Offset(0, -2)
        indicator_container.offset = ft.Offset(0, 2)
        indicator_container.opacity = 0

        detail_view.visible = True
        page.update()

        #実行：拡大とフェードインを同時に開始
        # 少し待たないとアニメーションが飛ぶことがあるので0.05秒待機
        await asyncio.sleep(0.05)
        img_curr.scale = 1
        img_curr.opacity = 1
        detail_view.opacity = 1
        page.update()

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
        nonlocal current_results
        
        query = search_input.value
        if not query: return #検索窓が空なら何もしない

        #ステータスメッセージの更新
        status_text.value = "検索中..."
        page.update()

        #非同期で検索を実行するとUIが固まらない（今回は簡易的に同期実行）
        results = searcher.search(query, limit=50)

        current_results = results #検索結果をグローバル変数に保存しておく

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