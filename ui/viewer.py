import flet as ft
import asyncio
import os
import time

class ImageViewer:
    def __init__(self, page: ft.Page, db):
        self.page = page
        self.db = db
        
        self.ANIM_DURATION = 100 #アニメーションの設定（ミリ秒）
        self.current_results = [] #検索結果のリスト
        self.current_index = 0 #現在表示中の画像のインデックス
        self.is_animating = False

        #ダミー画像
        self.dummy_src = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

        self.viewer_base_scale = 1.0 #ピンチ操作基準用の変数（ビューア用）
        self.viewer_last_focal_x = 0
        self.viewer_last_focal_y = 0
        self.is_detail_open = False
        self.last_scale_update = 0 #スロットリング用のタイマー変数
        self.is_ui_visible = False #UIの表示状態を記憶するフラグ

        self._build_ui()

    def _build_ui(self):
        # 画像本体（中身）を作成
        self.img_prev = self._create_inner_image()
        self.img_curr = self._create_inner_image()
        self.img_next = self._create_inner_image()

        # 画像を包む「ページ（黒背景コンテナ）」を作成し、これにOffset（位置）を持たせる
        self.page_prev = self._create_page_container(self.img_prev, -1)
        self.page_curr = self._create_page_container(self.img_curr, 0)
        self.page_next = self._create_page_container(self.img_next, 1)

        #ページ番号を表示するテキスト
        self.page_counter = ft.Text(
            "0 / 0",
            color="white",
            size=16,
            weight=ft.FontWeight.BOLD,
        )

        #テキストを画面下部に配置するためのラッパー
        self.indicator_container = ft.Container(
            bottom=40, # 下から40pxの位置に固定
            left=0,    # 左右を0にして
            right=0,   # widthを広げずに中央寄せにする準備
            # 内部のテキストだけを中央に寄せる
            content=ft.Row([self.page_counter], alignment=ft.MainAxisAlignment.CENTER),
            # 閉じるボタンと同じアニメーション設定
            offset=ft.Offset(0, 2), # 初期状態は画面外（下）
            animate_offset=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
            opacity=0,
            animate_opacity=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
        )

        #閉じるボタンのラッパー（アニメーション用）
        self.close_btn_wrapper = ft.Container(
            content=ft.IconButton(
                icon=ft.Icons.CLOSE, 
                icon_color="white", 
                icon_size=30,
                on_click=lambda e: asyncio.create_task(self.close_viewer(e)),
                bgcolor="#8A000000", #ボタン背景を半透明に
            ),
            top=35,   # 画面上端からの距離（SafeAreaの代わり）
            right=20, # 右端からの距離
            #初期位置は画面外（上）へ飛ばしておく
            #y=-2 は「自分の高さの2倍分、上に移動」という意味です
            offset=ft.Offset(0, -2),
            #位置のアニメーション設定 (滑らかに移動)
            animate_offset=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
        )

        # 右下に配置するお気に入り（ハート）ボタンのラッパー
        self.favorite_btn = ft.IconButton(
            icon=ft.Icons.FAVORITE_BORDER,
            icon_color=ft.Colors.WHITE,
            tooltip="お気に入り",
            on_click=self.on_favorite_click,
            icon_size=30,
            bgcolor="#8A000000", # 閉じるボタンと同じく半透明の黒背景で押しやすく
        )
        self.favorite_btn_wrapper = ft.Container(
            content=self.favorite_btn,
            bottom=35, # 画面下端からの距離
            left=20,  # 画面左端からの距離（親指が届きやすい位置）
            offset=ft.Offset(0, 2), # 初期状態は画面外（下）に逃がすことでタップ干渉を防ぐ
            animate_offset=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
            opacity=0,
            animate_opacity=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
        )

        #詳細パネル用の変数とUI構築
        self.detail_filename_text = ft.Text(size=16, weight=ft.FontWeight.BOLD, color="white")
        self.detail_path_text = ft.Text(size=12, color="white70")
        self.detail_tags_text = ft.Text(size=14, color="white", selectable=True)

        self.detail_info_panel = ft.Container(
            content=ft.Column(
                [
                    self.detail_filename_text,
                    self.detail_path_text,
                    ft.Divider(color="white24"),
                    ft.Text("タグ一覧", size=12, color="white54"),
                    self.detail_tags_text,
                ],
                scroll=ft.ScrollMode.AUTO, # タグが多い場合はスクロール可能に
            ),
            bgcolor="#EE000000", # 背景を濃いめの半透明黒に
            padding=20,
            border_radius=ft.border_radius.only(top_left=16, top_right=16),
            bottom=0, left=0, right=0, # 画面下部に固定
            height=300, # パネルの高さ（適宜調整）
            offset=ft.Offset(0, 1), # 初期状態は画面外（下）に100%隠しておく
            animate_offset=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
        )

        self.detail_view = ft.Container(
            visible=False, # 最初は隠しておく
            animate_opacity=self.ANIM_DURATION, #ANIM_DURATIONミリ秒かけて変化させる
            bgcolor="#000000", #背景は透明→黒(初期値は黒)
            alignment=ft.Alignment(0, 0),
            expand=True,
            content=ft.Stack(
                [
                    #レイヤー1: 画像操作用のジェスチャー（背景全体）
                    ft.GestureDetector(
                        on_tap_down=self.handle_tap, #タップ位置によって操作切り替え
                        #ダブルタップとドラッグ移動
                        on_double_tap_down=self.on_double_tap_down,
                        #ビューア用のピンチ操作
                        on_scale_start=self.on_viewer_scale_start,
                        on_scale_update=self.on_viewer_scale_update,
                        on_scale_end=self.on_viewer_scale_end,
                        content=ft.Stack([
                            self.page_prev,
                            self.page_curr,
                            self.page_next,
                        ], clip_behavior=ft.ClipBehavior.HARD_EDGE), #画面外のはみ出しを強制カット
                        expand=True,
                    ),
                    self.close_btn_wrapper,
                    self.indicator_container,
                    self.favorite_btn_wrapper,
                    self.detail_info_panel,
                ],
                expand=True,
            )
        )
        # アプリの最前面レイヤーにビューアを追加
        self.page.overlay.append(self.detail_view)

    # お気に入りボタンが押された時の処理
    def on_favorite_click(self, e):
        if 0 <= self.current_index < len(self.current_results):
            row = self.current_results[self.current_index]
            image_id = row['id']
            
            # DBのトグル関数を呼び出し、新しい状態を取得
            new_status = self.db.toggle_favorite(image_id)
            
            # 見た目の更新
            if new_status == 1:
                self.favorite_btn.icon = ft.Icons.FAVORITE
                self.favorite_btn.icon_color = ft.Colors.RED
            else:
                self.favorite_btn.icon = ft.Icons.FAVORITE_BORDER
                self.favorite_btn.icon_color = ft.Colors.WHITE
            self.favorite_btn.update()
            
            # ローカルのリストにも反映（ページを移動して戻ってきた時用）
            if isinstance(row, dict):
                 row['is_favorite'] = new_status
            else:
                 new_row = dict(row)
                 new_row['is_favorite'] = new_status
                 self.current_results[self.current_index] = new_row

    # 画像が切り替わった時にハートの見た目を更新する関数
    def update_favorite_button_state(self):
        if 0 <= self.current_index < len(self.current_results):
            row = self.current_results[self.current_index]
            image_id = row['id']
            
            # 確実な状態を取得するためDBから引く
            db_row = self.db.get_image_by_id(image_id)
            current_status = db_row.get('is_favorite', 0) if db_row else 0

            if current_status == 1:
                self.favorite_btn.icon = ft.Icons.FAVORITE
                self.favorite_btn.icon_color = ft.Colors.RED
            else:
                self.favorite_btn.icon = ft.Icons.FAVORITE_BORDER
                self.favorite_btn.icon_color = ft.Colors.WHITE
            self.favorite_btn.update()

    # ページを包むコンテナを作成する関数
    def _create_page_container(self, content_img, initial_x):
        return ft.Container(
            content=content_img,
            alignment=ft.Alignment(0, 0),
            top=0, left=0, right=0, bottom=0,
            bgcolor="black", # これが「壁」になり、後ろの画像を隠す
            offset=ft.Offset(initial_x, 0),
            animate_offset=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
        )

    # 画像単体の設定
    def _create_inner_image(self):
        return ft.Image(
            src=self.dummy_src,
            fit="contain",
            expand=True,
            scale=1,
            offset=ft.Offset(0, 0), # ズーム時の移動用
            animate_scale=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
            animate_opacity=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
            animate_offset=ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT),
        )

    # 2. 画像パスを取得するヘルパー関数
    def get_image_src(self, index):
        if 0 <= index < len(self.current_results):
            row = self.current_results[index]
            raw_path = row.get('file_path', '')
            
            if raw_path:
                # 基準ディレクトリ（data/images）からの相対パスを取得してURL形式へ変換
                try:
                    rel_path = os.path.relpath(raw_path, "data/images").replace("\\", "/")
                except ValueError:
                    rel_path = os.path.basename(raw_path)
                    
                return f"/images/{rel_path}"
            else:
                # thumbnail_pathの取得処理も少し安全に修正
                thumbnail_path = row.get('thumbnail_path')
                if thumbnail_path:
                    return f"/thumbnails/{os.path.basename(thumbnail_path)}"
        return self.dummy_src

    # 3. 3枚の画像をセットして位置をリセットする関数（重要）
    def reset_images_position(self, index):
        # アニメーションを一時的に無効化（瞬間移動させるため）
        self.page_prev.animate_offset = None
        self.page_curr.animate_offset = None
        self.page_next.animate_offset = None

        # 3枚の画像の中身を更新（プリロード）
        self.img_prev.src = self.get_image_src(index - 1)
        self.img_curr.src = self.get_image_src(index)
        self.img_next.src = self.get_image_src(index + 1)

        # 位置を定位置（左・中・右）に戻す
        self.page_prev.offset = ft.Offset(-1, 0)
        self.page_curr.offset = ft.Offset(0, 0)
        self.page_next.offset = ft.Offset(1, 0)
        
        # 拡大率や透明度を「3枚すべて」確実にリセットする（透明化バグの防止）
        for img in [self.img_prev, self.img_curr, self.img_next]:
            img.scale = 1
            img.offset = ft.Offset(0, 0)
            img.opacity = 1

        self.page_prev.update()
        self.page_curr.update()
        self.page_next.update()

        # アニメーション設定を復元
        anim = ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT)
        self.page_prev.animate_offset = anim
        self.page_curr.animate_offset = anim
        self.page_next.animate_offset = anim

    # 4. スライド移動のアニメーション処理
    async def slide_next(self):
        if self.is_animating or self.current_index >= len(self.current_results) - 1: return

        self.is_animating = True #ロック開始
        self.toggle_detail_panel(False) #ページをめくったらパネルを隠す

        # アニメーション開始：中→左、右→中
        self.page_curr.offset = ft.Offset(-1, 0)
        self.page_next.offset = ft.Offset(0, 0)
        self.page_curr.update()
        self.page_next.update()

        # 移動完了を待つ
        await asyncio.sleep(self.ANIM_DURATION / 1000)

        self.current_index += 1 #インデックスを戻す
        self.update_indicator()

        recycle_page = self.page_prev
        recycle_img = self.img_prev
        self.update_favorite_button_state() #ページをめくった時にハートの状態を更新
        
        recycle_page.animate_offset = None
        recycle_page.offset = ft.Offset(1, 0)
        recycle_img.src = self.get_image_src(self.current_index + 1)
        recycle_img.scale = 1
        recycle_img.offset = ft.Offset(0, 0)
        recycle_img.opacity = 1 # スワイプ時にも確実に表示状態へ戻す
        recycle_page.update()

        #アニメーションの設定を戻す
        recycle_page.animate_offset = ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT)

        self.page_prev = self.page_curr
        self.page_curr = self.page_next
        self.page_next = recycle_page
        
        self.img_prev = self.img_curr
        self.img_curr = self.img_next
        self.img_next = recycle_img

        self.is_animating = False #ロック解除

    async def slide_prev(self):
        if self.is_animating or self.current_index <= 0: return

        self.is_animating = True #ロック開始
        self.toggle_detail_panel(False) #ページをめくったらパネルを隠す

        # アニメーション開始：中→右、左→中
        self.page_curr.offset = ft.Offset(1, 0)
        self.page_prev.offset = ft.Offset(0, 0)
        self.page_curr.update()
        self.page_prev.update()

        # 移動完了を待つ
        await asyncio.sleep(self.ANIM_DURATION / 1000)

        self.current_index -= 1 #インデックスを戻す
        self.update_indicator()
        self.update_favorite_button_state() # ページをめくった時にハートの状態を更新

        recycle_page = self.page_next
        recycle_img = self.img_next

        recycle_page.animate_offset = None
        recycle_page.offset = ft.Offset(-1, 0)
        recycle_img.src = self.get_image_src(self.current_index - 1)
        recycle_img.scale = 1
        recycle_img.offset = ft.Offset(0, 0)
        recycle_img.opacity = 1 # スワイプ時にも確実に表示状態へ戻す
        recycle_page.update()

        recycle_page.animate_offset = ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT)

        self.page_next = self.page_curr
        self.page_curr = self.page_prev
        self.page_prev = recycle_page
        
        self.img_next = self.img_curr
        self.img_curr = self.img_prev
        self.img_prev = recycle_img

        self.is_animating = False #ロック解除

    #ビュアーを閉じる関数
    async def close_viewer(self, e):
        #小さくしながら透明にする
        self.img_curr.scale = 0
        self.img_curr.opacity = 0
        self.detail_view.opacity = 0
        self.page.update()
        
        #アニメーションが終わるまで待つ
        await asyncio.sleep(self.ANIM_DURATION / 1000)
        
        #完全に非表示にする
        self.detail_view.visible = False
        self.detail_view.update()

    #UI（閉じるボタン）の出し入れを切り替える関数
    def toggle_ui(self, e=None, force_state=None):
        #フラグで状態を管理
        if force_state is not None:
            self.is_ui_visible = force_state
        else:
            self.is_ui_visible = not self.is_ui_visible

        #現在の位置を確認して切り替え
        if not self.is_ui_visible:
            self.close_btn_wrapper.offset = ft.Offset(0, -2) #上に隠す

            #下へ隠す
            self.indicator_container.offset = ft.Offset(0, 2)
            self.indicator_container.opacity = 0
            self.favorite_btn_wrapper.offset = ft.Offset(0, 2)
            self.favorite_btn_wrapper.opacity = 0
        else:
            #定位置に戻す
            self.close_btn_wrapper.offset = ft.Offset(0, 0)

            self.indicator_container.offset = ft.Offset(0, 0)
            self.indicator_container.opacity = 1
            self.favorite_btn_wrapper.offset = ft.Offset(0, 0)
            self.favorite_btn_wrapper.opacity = 1

        # open()から状態復元として呼ばれた場合(force_stateがある場合)は、
        # 後でページ全体が更新されるため個別のupdateはスキップする
        if force_state is None:
            self.close_btn_wrapper.update()
            self.indicator_container.update()
            self.favorite_btn_wrapper.update()

    #現在のインデックスと総件数を計算して反映
    def update_indicator(self):
        total = len(self.current_results)
        current = self.current_index + 1 if total > 0 else 0
        self.page_counter.value = f"{current} / {total}"
        self.page_counter.update()

    def update_detail_panel(self, index):
        if 0 <= index < len(self.current_results):
            row = self.current_results[index]
            self.detail_filename_text.value = os.path.basename(row.get('file_path', ''))
            self.detail_path_text.value = row.get('file_path', '')
            
            # タグを見やすくカンマ＋スペースに整形
            raw_tags = row.get('tags_combined', '')
            self.detail_tags_text.value = raw_tags.replace(',', ', ') if raw_tags else 'タグなし'
            
            self.detail_info_panel.update()

    def toggle_detail_panel(self, show=None):
        if show is None:
            self.is_detail_open = not self.is_detail_open
        else:
            self.is_detail_open = show

        if self.is_detail_open:
            self.update_detail_panel(self.current_index)
            self.detail_info_panel.offset = ft.Offset(0, 0) # ニュッと出す
        else:
            self.detail_info_panel.offset = ft.Offset(0, 1) # 下に隠す

        self.detail_info_panel.update()

    # ビューアでのピンチ操作開始
    async def on_viewer_scale_start(self, e):
        # 現在の倍率を基準点として記録
        self.viewer_base_scale = self.img_curr.scale

        #操作開始時の指の中心座標を記録
        self.viewer_last_focal_x = e.local_focal_point.x
        self.viewer_last_focal_y = e.local_focal_point.y

        # 指の動きにリアルタイムで追従させるため、アニメーションを一時的に切る
        self.img_curr.animate_scale = None
        self.img_curr.animate_offset = None
        self.img_curr.update()

        # スロットリング用のタイマーをリセット
        self.last_scale_update = time.time()

    # ビューアでのピンチ操作中
    async def on_viewer_scale_update(self, e):
        # 新しい倍率 = 開始時の倍率 × 指の開き具合
        new_scale = self.viewer_base_scale * e.scale
        
        # 制限: 下限を 1.0 ではなく、0.5 くらいまで許容する（バネのような効果のため）
        if new_scale < 0.5: new_scale = 0.5
        if new_scale > 5.0: new_scale = 5.0
        
        self.img_curr.scale = new_scale

        # 拡大している時だけ移動できるようにする
        if self.img_curr.scale > 1.0:
            # 前回の座標との「差分」を計算して移動させる
            dx = (e.local_focal_point.x - self.viewer_last_focal_x) / self.page.width
            dy = (e.local_focal_point.y - self.viewer_last_focal_y) / self.page.height
            
            # とりあえず計算上の新しい位置
            raw_x = self.img_curr.offset.x + dx
            raw_y = self.img_curr.offset.y + dy
            
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
            
            self.img_curr.offset = ft.Offset(raw_x, raw_y)
        
        # 次のフレームのために現在の座標を保存
        self.viewer_last_focal_x = e.local_focal_point.x
        self.viewer_last_focal_y = e.local_focal_point.y

        # 描画更新を30fps相当（0.033秒間隔）に設定
        current_time = time.time()
        if current_time - self.last_scale_update > 0.033:
            self.img_curr.update()
            self.last_scale_update = current_time

    # ビューアでのピンチ操作終了
    async def on_viewer_scale_end(self, e):
        # 指を離した瞬間に確実に最終位置で描画を更新する
        self.img_curr.update()

        # アニメーション設定を元に戻す（ダブルタップ時のため）
        self.img_curr.animate_scale = ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT)
        self.img_curr.animate_offset = ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT)
        
        # もし指を離した時に等倍(1.0)に戻っていたら、位置ズレもリセットする
        # 指を離した時に 1.0倍 未満なら 1.0 に戻す（バウンスバック）
        if self.img_curr.scale < 1.0:
            self.img_curr.scale = 1.0
            # 位置ズレもリセット（拡大したまま閉じたり戻ったりすると変になるため）
            self.img_curr.offset = ft.Offset(0, 0)
            self.img_curr.update()
            return

        #拡大中に端からはみ出していた場合のバウンスバック
        if self.img_curr.scale > 1.0:
            # 現在の正しい限界値を計算
            limit = (self.img_curr.scale - 1) / 2
            
            curr_x = self.img_curr.offset.x
            curr_y = self.img_curr.offset.y
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
                self.img_curr.offset = ft.Offset(curr_x, curr_y)
                self.img_curr.update()
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
                asyncio.create_task(self.slide_prev())
            elif vx < -100:
                asyncio.create_task(self.slide_next())
        else: 
            if vy > 800: #下スワイプ
                if self.is_detail_open:
                    self.toggle_detail_panel(False) #パネルが開いていたら閉じる
                else:
                    asyncio.create_task(self.close_viewer(None)) #パネルが閉じていたらビューアを閉じる
            elif vy < -800: #上スワイプ
                if not self.is_detail_open:
                    self.toggle_detail_panel(True) #パネルを開く

    # ダブルタップされたときの処理
    async def on_double_tap_down(self, e):
        # すでに拡大されているかチェック
        if self.img_curr.scale != 1:
            # 拡大中なら → 等倍に戻す（リセット）
            self.img_curr.scale = 1
            self.img_curr.offset = ft.Offset(0, 0)
            # 戻る時は滑らかに
            self.img_curr.animate_offset = ft.Animation(self.ANIM_DURATION, ft.AnimationCurve.EASE_OUT)
        else:
            # 等倍なら → 2倍にズーム
            self.img_curr.scale = 2
            # ズーム中は指に吸い付くように動かしたいので、アニメーションを切る
            self.img_curr.animate_offset = None
            
            # 拡大した瞬間にUI（ボタンなど）が邪魔なら隠す
            if self.is_ui_visible:
                self.toggle_ui(None)
                 
        self.img_curr.update()

    # タップされた位置に応じて処理を振り分ける関数
    async def handle_tap(self, e):
        # 詳細パネルが開いている時は、どこをタップしてもパネルを閉じる処理を優先
        if self.is_detail_open:
            self.toggle_detail_panel(False)
            return

        #拡大中は移動操作を無効にする（誤操作防止）
        if self.img_curr.scale > 1:
            self.toggle_ui(None) # UIの出し入れだけ許可する
            return
        
        #両端タップで左右の画面に移動
        """
        #画面の横幅を取得
        width = self.page.width
        #左右 20% ずつをタップエリアとして定義
        edge_zone = width * 0.2

        if e.local_position.x < edge_zone:
            #左端なら「前へ」
            asyncio.create_task(self.slide_prev())
        elif e.local_position.x > width - edge_zone:
            #右端なら「次へ」
            asyncio.create_task(self.slide_next())
        else:
            #中央付近なら「UIの出し入れ」
            self.toggle_ui(None)
        """

        #画面のどこをタップしてもUIの出し入れのみにする
        self.toggle_ui(None)

    # アプリ側から呼び出すエントリポイント
    async def open(self, results, clicked_row):
        self.is_animating = False #フラグをリセット
        self.current_results = results
        
        #クリックされた画像がリストの何番目かを探して記憶する
        try:
            self.current_index = self.current_results.index(clicked_row)
        except ValueError:
            self.current_index = 0

        self.reset_images_position(self.current_index)
        self.update_indicator()
        self.update_favorite_button_state()

        #準備：画像URLをセットし、最初は「透明・最小」にする
        self.img_curr.scale = 0
        self.img_curr.opacity = 0
        self.detail_view.opacity = 0

        #記憶している前回のUI状態をそのまま復元する
        self.toggle_ui(force_state=self.is_ui_visible)

        #新しく画像を開くときは詳細パネルの状態をリセット
        self.is_detail_open = False
        self.detail_info_panel.offset = ft.Offset(0, 1)

        self.detail_view.visible = True
        self.page.update()

        #実行：拡大とフェードインを同時に開始
        # 少し待たないとアニメーションが飛ぶことがあるので0.05秒待機
        await asyncio.sleep(0.05)
        self.img_curr.scale = 1
        self.img_curr.opacity = 1
        self.detail_view.opacity = 1
        self.page.update()