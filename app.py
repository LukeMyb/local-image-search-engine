import flet as ft

def main(page: ft.Page):
    # ページ設定
    page.title = "Flet Test"
    page.theme_mode = "dark"
    
    # 部品の作成
    text = ft.Text("Hello! 画面が見えたら成功です", size=30, color="green")
    
    def on_click(e):
        text.value = "ボタンが押されました！動作しています。"
        page.update()

    btn = ft.ElevatedButton("テストボタン", on_click=on_click)

    # 画面に追加
    page.add(text, btn)
    page.update()

if __name__ == "__main__":
    # ブラウザモードで起動
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=8000)