import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import psutil
import pystray
from dotenv import load_dotenv
from PIL import Image, ImageDraw

# プロジェクトルートのパスを確定
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
PYTHON_EXE = BASE_DIR / ".venv" / "Scripts" / "python.exe"

# .env を読み込んでホスト・ポート設定を取得
load_dotenv(BASE_DIR / ".env")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", 8715))
WEB_PORT = int(os.getenv("WEB_PORT", 3715))

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def acquire_single_instance_mutex():
    """多重起動を防止するためのWindows名前付きミューテックスを取得する"""
    if os.name != "nt":
        return None
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "Local\\LISE_Tray_Manager_Mutex")
    last_error = kernel32.GetLastError()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        return None
    return mutex


def create_tray_icon(is_running: bool) -> Image.Image:
    """
    他のツールと一目で区別できる専用アイコン（画像フレーム＋虫眼鏡＋状態バッジ）を描画する
    - is_running=True : スカイブルー枠＋白/水色アイコン＋右下に緑色の稼働バッジ
    - is_running=False: グレー枠＋グレーアイコン＋右下にオレンジ色の一時停止バッジ
    """
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. 背景の角丸四角形
    bg_color = (24, 24, 27, 255)  # #18181b
    border_color = (56, 189, 248, 255) if is_running else (82, 82, 91, 255)
    draw.rounded_rectangle(
        [2, 2, 56, 56],
        radius=12,
        fill=bg_color,
        outline=border_color,
        width=3,
    )

    # 2. 写真フレームと山・太陽モチーフ
    fg_main = (244, 244, 245, 255) if is_running else (113, 113, 122, 255)
    fg_accent = (56, 189, 248, 255) if is_running else (82, 82, 91, 255)

    # 太陽（左上の丸）
    draw.ellipse([12, 12, 20, 20], fill=fg_accent)

    # 山のシルエット
    draw.polygon([(10, 42), (22, 26), (32, 38), (38, 30), (46, 42)], fill=fg_main)

    # 3. 虫眼鏡（中央〜左上）
    draw.ellipse(
        [16, 14, 42, 40],
        outline=border_color if is_running else fg_main,
        width=4,
    )
    draw.line(
        [(38, 36), (48, 46)],
        fill=border_color if is_running else fg_main,
        width=5,
    )

    # 4. 右下のステータスバッジ（視認性を高める大きめドット）
    badge_bbox = [38, 38, 62, 62]
    if is_running:
        # 緑色の稼働中バッジ
        draw.ellipse(badge_bbox, fill=(34, 197, 94, 255), outline=(9, 9, 11, 255), width=3)
    else:
        # オレンジ色の一時停止バッジ（中に「||」マーク）
        draw.ellipse(badge_bbox, fill=(245, 158, 11, 255), outline=(9, 9, 11, 255), width=3)
        draw.rectangle([46, 45, 48, 55], fill=(24, 24, 27, 255))
        draw.rectangle([52, 45, 54, 55], fill=(24, 24, 27, 255))

    return img


class ServerTrayManager:
    def __init__(self):
        self.backend_proc: subprocess.Popen | None = None
        self.frontend_proc: subprocess.Popen | None = None
        self.is_running: bool = False
        self.lock = threading.Lock()
        self.icon: pystray.Icon | None = None

    def _kill_process_tree(self, pid: int):
        """指定PIDとその子プロセス（重量ワーカーやNode子プロセス）を確実に終了する"""
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            parent.terminate()
            _, alive = psutil.wait_procs(children + [parent], timeout=3)
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
        except Exception:
            # フォールバックとして taskkill /F /T を非表示実行
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def _kill_processes_on_ports(self, ports: list[int]):
        """指定ポートをListenしているプロセスがあればツリーごと終了する"""
        target_pids = set()
        try:
            for conn in psutil.net_connections(kind="inet"):
                if (
                    conn.status == psutil.CONN_LISTEN
                    and conn.laddr
                    and conn.laddr.port in ports
                    and conn.pid
                ):
                    target_pids.add(conn.pid)
        except Exception:
            pass

        for pid in target_pids:
            if pid != os.getpid():
                self._kill_process_tree(pid)

    def start_servers(self):
        """バックエンドとフロントエンドを非表示で起動する"""
        with self.lock:
            if self.is_running:
                return

            # 起動前にポート(8715/3715)に残っている古いプロセスがあれば掃除
            self._kill_processes_on_ports([API_PORT, WEB_PORT])

            python_cmd = str(PYTHON_EXE) if PYTHON_EXE.exists() else sys.executable
            npm_cmd = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"

            # バックエンド起動 (python api.py)
            self.backend_proc = subprocess.Popen(
                [python_cmd, "api.py"],
                cwd=str(BASE_DIR),
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # フロントエンド起動 (npm run start)
            self.frontend_proc = subprocess.Popen(
                [npm_cmd, "run", "start"],
                cwd=str(FRONTEND_DIR),
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.is_running = True
            self._update_tray_ui()

    def stop_servers(self):
        """常駐サーバーを停止してポートを解放する"""
        with self.lock:
            if self.backend_proc and self.backend_proc.poll() is None:
                self._kill_process_tree(self.backend_proc.pid)
            self.backend_proc = None

            if self.frontend_proc and self.frontend_proc.poll() is None:
                self._kill_process_tree(self.frontend_proc.pid)
            self.frontend_proc = None

            # 念のためポートを掴んでいる残存プロセスも解放
            self._kill_processes_on_ports([API_PORT, WEB_PORT])

            self.is_running = False
            self._update_tray_ui()

    def restart_servers(self):
        """常駐サーバーを再起動する"""
        self.stop_servers()
        time.sleep(0.5)
        self.start_servers()

    def _update_tray_ui(self):
        """アイコン画像・ツールチップ・メニュー表示を最新状態に更新する"""
        if not self.icon:
            return
        self.icon.icon = create_tray_icon(self.is_running)
        status_str = "常駐稼働中" if self.is_running else "停止中"
        self.icon.title = f"LISE - {status_str} ({API_PORT} / {WEB_PORT})"
        self.icon.update_menu()

    # --- メニューアクション ---

    def on_open_browser(self, icon=None, item=None):
        url = f"http://{API_HOST}:{WEB_PORT}"
        webbrowser.open(url)

    def on_open_vscode(self, icon=None, item=None):
        code_cmd = shutil.which("code.cmd") or shutil.which("code")
        if not code_cmd:
            # 標準的なVS Codeインストールパスを探索
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            candidate = Path(local_app_data) / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd"
            if candidate.exists():
                code_cmd = str(candidate)

        if code_cmd:
            subprocess.Popen(
                [code_cmd, str(BASE_DIR)],
                cwd=str(BASE_DIR),
                creationflags=CREATE_NO_WINDOW,
            )
        else:
            os.startfile(str(BASE_DIR))

    def on_toggle_servers(self, icon=None, item=None):
        if self.is_running:
            threading.Thread(target=self.stop_servers, daemon=True).start()
        else:
            threading.Thread(target=self.start_servers, daemon=True).start()

    def on_restart_servers(self, icon=None, item=None):
        threading.Thread(target=self.restart_servers, daemon=True).start()

    def on_exit_tray(self, icon=None, item=None):
        self.stop_servers()
        if self.icon:
            self.icon.stop()

    def build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: (
                    f"● 状態: 常駐稼働中 ({API_PORT} / {WEB_PORT})"
                    if self.is_running
                    else f"○ 状態: 停止中 ({API_PORT} / {WEB_PORT})"
                ),
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                f"🌐 ブラウザで開く ({API_HOST}:{WEB_PORT})",
                self.on_open_browser,
                default=True,
            ),
            pystray.MenuItem(
                "📁 プロジェクトフォルダをVS Codeで開く",
                self.on_open_vscode,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "⏸ 常駐を停止" if self.is_running else "▶ 常駐を再開",
                self.on_toggle_servers,
            ),
            pystray.MenuItem(
                "🔄 常駐サーバーを再起動",
                self.on_restart_servers,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "❌ トレイから完全終了",
                self.on_exit_tray,
            ),
        )

    def run(self):
        self.icon = pystray.Icon(
            name="local-image-search-engine",
            icon=create_tray_icon(False),
            title=f"LISE - 起動中 ({API_PORT} / {WEB_PORT})",
            menu=self.build_menu(),
        )

        def setup(icon: pystray.Icon):
            icon.visible = True
            self.start_servers()

        self.icon.run(setup=setup)


if __name__ == "__main__":
    mutex = acquire_single_instance_mutex()
    if mutex is None:
        # 既にトレイアプリが起動している場合は二重起動せず終了
        sys.exit(0)

    manager = ServerTrayManager()
    manager.run()
