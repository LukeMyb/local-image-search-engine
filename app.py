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
            scale=1,
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

        toggle_detail_panel(False) #ページをめくったらパネルを隠す

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

        toggle_detail_panel(False) #ページをめくったらパネルを隠す

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

    #詳細パネル用の変数とUI構築

    is_detail_open = False

    detail_filename_text = ft.Text(size=16, weight=ft.FontWeight.BOLD, color="white")
    detail_path_text = ft.Text(size=12, color="white70")
    detail_tags_text = ft.Text(size=14, color="white", selectable=True)

    detail_info_panel = ft.Container(
        content=ft.Column(
            [
                detail_filename_text,
                detail_path_text,
                ft.Divider(color="white24"),
                ft.Text("タグ一覧", size=12, color="white54"),
                detail_tags_text,
            ],
            scroll=ft.ScrollMode.AUTO, # タグが多い場合はスクロール可能に
        ),
        bgcolor="#EE000000", # 背景を濃いめの半透明黒に
        padding=20,
        border_radius=ft.border_radius.only(top_left=16, top_right=16),
        bottom=0, left=0, right=0, # 画面下部に固定
        height=300, # パネルの高さ（適宜調整）
        offset=ft.Offset(0, 1), # 初期状態は画面外（下）に100%隠しておく
        animate_offset=ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
    )

    def update_detail_panel(index):
        if 0 <= index < len(current_results):
            row = current_results[index]
            detail_filename_text.value = os.path.basename(row.get('file_path', ''))
            detail_path_text.value = row.get('file_path', '')
            
            # タグを見やすくカンマ＋スペースに整形
            raw_tags = row.get('tags_combined', '')
            detail_tags_text.value = raw_tags.replace(',', ', ') if raw_tags else 'タグなし'
            
            detail_info_panel.update()

    def toggle_detail_panel(show=None):
        nonlocal is_detail_open
        if show is None:
            is_detail_open = not is_detail_open
        else:
            is_detail_open = show

        if is_detail_open:
            update_detail_panel(current_index)
            detail_info_panel.offset = ft.Offset(0, 0) # ニュッと出す
        else:
            detail_info_panel.offset = ft.Offset(0, 1) # 下に隠す

        detail_info_panel.update()

    viewer_last_focal_x = 0
    viewer_last_focal_y = 0
    # ビューアでのピンチ操作開始
    def on_viewer_scale_start(e):
        nonlocal viewer_base_scale, viewer_last_focal_x, viewer_last_focal_y
        # 現在の倍率を基準点として記録
        viewer_base_scale = img_curr.scale

        #操作開始時の指の中心座標を記録
        viewer_last_focal_x = e.local_focal_point.x
        viewer_last_focal_y = e.local_focal_point.y

        # 指の動きにリアルタイムで追従させるため、アニメーションを一時的に切る
        img_curr.animate_scale = None
        img_curr.animate_offset = None
        img_curr.update()

    # ビューアでのピンチ操作中
    def on_viewer_scale_update(e):
        nonlocal viewer_last_focal_x, viewer_last_focal_y

        # 新しい倍率 = 開始時の倍率 × 指の開き具合
        new_scale = viewer_base_scale * e.scale
        
        # 制限: 下限を 1.0 ではなく、0.5 くらいまで許容する（バネのような効果のため）
        if new_scale < 0.5: new_scale = 0.5
        if new_scale > 5.0: new_scale = 5.0
        
        img_curr.scale = new_scale

        # 拡大している時だけ移動できるようにする
        if img_curr.scale > 1.0:
            # 前回の座標との「差分」を計算して移動させる
            dx = (e.local_focal_point.x - viewer_last_focal_x) / page.width
            dy = (e.local_focal_point.y - viewer_last_focal_y) / page.height
            
            # とりあえず計算上の新しい位置
            raw_x = img_curr.offset.x + dx
            raw_y = img_curr.offset.y + dy
            
            #移動限界の計算
            # 例: scale=3倍なら、(3-1)/2 = 1.0 (画面1枚分) まで左右に動ける
            limit = (new_scale - 1) / 2

            # limitを超えた分には 0.4 を掛けて、動きを鈍くする
            resistance = 0.4
            
            # X軸の抵抗処理
            if raw_x > limit:
                raw_x = limit + (raw_x - limit) * resistance
            elif raw_x < -limit:
                raw_x = -limit + (raw_x + limit) * resistance
            # Y軸の抵抗処理
            if raw_y > limit:
                raw_y = limit + (raw_y - limit) * resistance
            elif raw_y < -limit:
                raw_y = -limit + (raw_y + limit) * resistance
            
            img_curr.offset = ft.Offset(raw_x, raw_y)
        
        # 次のフレームのために現在の座標を保存
        viewer_last_focal_x = e.local_focal_point.x
        viewer_last_focal_y = e.local_focal_point.y

        img_curr.update()

    # ビューアでのピンチ操作終了
    def on_viewer_scale_end(e):
        # アニメーション設定を元に戻す（ダブルタップ時のため）
        img_curr.animate_scale = ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT)
        img_curr.animate_offset = ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT)
        
        # もし指を離した時に等倍(1.0)に戻っていたら、位置ズレもリセットする
        # 指を離した時に 1.0倍 未満なら 1.0 に戻す（バウンスバック）
        if img_curr.scale < 1.0:
            img_curr.scale = 1.0
            # 位置ズレもリセット（拡大したまま閉じたり戻ったりすると変になるため）
            img_curr.offset = ft.Offset(0, 0)
            img_curr.update()
            return

        #拡大中に端からはみ出していた場合のバウンスバック
        if img_curr.scale > 1.0:
            # 現在の正しい限界値を計算
            limit = (img_curr.scale - 1) / 2
            
            curr_x = img_curr.offset.x
            curr_y = img_curr.offset.y
            needs_reset = False # リセットが必要かどうかのフラグ

            # X軸のはみ出しチェック
            if curr_x > limit:
                curr_x = limit
                needs_reset = True
            elif curr_x < -limit:
                curr_x = -limit
                needs_reset = True
            # Y軸のはみ出しチェック
            if curr_y > limit:
                curr_y = limit
                needs_reset = True
            elif curr_y < -limit:
                curr_y = -limit
                needs_reset = True

            # もしはみ出していたら、定位置に戻して終了 (return)
            if needs_reset:
                img_curr.offset = ft.Offset(curr_x, curr_y)
                img_curr.update()
                return
            
            # はみ出していなければ、ここで return してスワイプ判定に行かせない
            # (拡大中はスワイプページめくりをさせない仕様の場合)
            return

        # ScaleEndEvent にも velocity (速度) 情報が含まれています
        vx = e.velocity.x
        vy = e.velocity.y

        # 左右の移動速度(絶対値)が上下より大きい -> 横スワイプ
        if abs(vx) > abs(vy):
            if vx > 100: 
                asyncio.create_task(slide_prev())
            elif vx < -100:
                asyncio.create_task(slide_next())
        else: 
            if vy > 400: #下スワイプ
                if is_detail_open:
                    toggle_detail_panel(False) #パネルが開いていたら閉じる
                else:
                    asyncio.create_task(close_viewer(None)) #パネルが閉じていたらビューアを閉じる
            elif vy < -400: #上スワイプ
                if not is_detail_open:
                    toggle_detail_panel(True) #パネルを開く

    # ダブルタップされたときの処理
    def on_double_tap_down(e):
        # すでに拡大されているかチェック
        if img_curr.scale != 1:
            # 拡大中なら → 等倍に戻す（リセット）
            img_curr.scale = 1
            img_curr.offset = ft.Offset(0, 0)
            # 戻る時は滑らかに
            img_curr.animate_offset = ft.Animation(ANIM_DURATION, ft.AnimationCurve.EASE_OUT)
        else:
            # 等倍なら → 2倍にズーム
            img_curr.scale = 2
            # ズーム中は指に吸い付くように動かしたいので、アニメーションを切る
            img_curr.animate_offset = None
            
            # 拡大した瞬間にUI（ボタンなど）が邪魔なら隠す
            if close_btn_wrapper.offset.y == 0:
                 toggle_ui(None)
                 
        img_curr.update()

    # タップされた位置に応じて処理を振り分ける関数
    def handle_tap(e):
        # 詳細パネルが開いている時は、どこをタップしてもパネルを閉じる処理を優先
        if is_detail_open:
            toggle_detail_panel(False)
            return

        #拡大中は移動操作を無効にする（誤操作防止）
        if img_curr.scale > 1:
            toggle_ui(None) # UIの出し入れだけ許可する
            return

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

                    #ダブルタップとドラッグ移動
                    on_double_tap_down=on_double_tap_down,

                    #ビューア用のピンチ操作
                    on_scale_start=on_viewer_scale_start,
                    on_scale_update=on_viewer_scale_update,
                    on_scale_end=on_viewer_scale_end,

                    content=ft.Stack([
                        ft.Container(content=img_prev, alignment=ft.Alignment(0,0), expand=True),
                        ft.Container(content=img_curr, alignment=ft.Alignment(0,0), expand=True),
                        ft.Container(content=img_next, alignment=ft.Alignment(0,0), expand=True),
                    ]),
                    expand=True,
                ),
                close_btn_wrapper,
                indicator_container,
                detail_info_panel,
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

        #新しく画像を開くときは詳細パネルの状態をリセット
        nonlocal is_detail_open
        is_detail_open = False
        detail_info_panel.offset = ft.Offset(0, 1)

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

    base_columns = 3 #ピンチ操作基準用の変数
    viewer_base_scale = 1.0 #ピンチ操作基準用の変数（ビューア用）

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
        results, conversion_log = searcher.search(query, limit=50)

        current_results = results #検索結果をグローバル変数に保存しておく

        #グリッドをクリア
        images_grid.controls.clear()

        if not results:
            status_text.value = "見つかりませんでした。"
        else:
            status_text.value = f"Hit: {len(results)} {conversion_log}"

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