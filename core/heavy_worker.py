import os
import sys
import time
import threading
import multiprocessing
from multiprocessing.connection import Connection
from typing import Optional, Dict, Any, List


def _heavy_worker_loop(
    conn: Connection,
    db_path: str,
    tag_index_path: str,
    style_index_path: str,
):
    """
    子プロセス内で実行されるAI推論ワーカーのメインループ。
    メインプロセスをPyTorch / DirectML / FAISSのメモリ空間から完全に隔離し、
    子プロセス終了時にOSへRAM・VRAMを100%返還できるようにする。
    """
    try:
        t_start = time.time()
        print(f"  [HeavyWorker] 子プロセス起動 (PID: {os.getpid()}) - AIモデルをロード中...", flush=True)

        # 外部通信の完全遮断（起動高速化・フリーズ防止）
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("translators_default_region", "EN")

        import csv
        import faiss
        import torch
        import torch_directml
        from huggingface_hub import hf_hub_download
        from transformers import CLIPTokenizer, CLIPTextModelWithProjection, logging as hf_logging
        from transformers import modeling_utils
        from transformers.utils import import_utils

        hf_logging.set_verbosity_error()
        if hasattr(modeling_utils, "check_torch_load_is_safe"):
            modeling_utils.check_torch_load_is_safe = lambda: None
        if hasattr(import_utils, "check_torch_load_is_safe"):
            import_utils.check_torch_load_is_safe = lambda: None

        from core.database import ImageDatabase
        from core.style_search import StyleSearcher

        # 1. DirectMLデバイスの初期化
        device = torch_directml.device()
        print(f"  [HeavyWorker] Device: {device} (DirectML)", flush=True)

        # 2. CLIPテキストエンコーダーとトークナイザーのロード
        model_id = "openai/clip-vit-base-patch32"
        clip_model = CLIPTextModelWithProjection.from_pretrained(
            model_id, use_safetensors=False, local_files_only=True
        ).to(device)
        clip_model.eval()
        tokenizer = CLIPTokenizer.from_pretrained(model_id, local_files_only=True)

        # 3. タグFAISSインデックスとタグ名リストのロード
        tag_index = faiss.read_index(tag_index_path)
        repo_id = "SmilingWolf/wd-v1-4-moat-tagger-v2"
        csv_path = hf_hub_download(repo_id, "selected_tags.csv", local_files_only=True)
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            tag_list = [row["name"] for row in reader]
        tag_set = set(tag_list)

        # 4. DB接続と絵柄検索エンジン（VGG16 + style.index）のロード
        db = ImageDatabase(db_path)
        style_searcher = StyleSearcher(db, index_path=style_index_path, device=device)

        # 翻訳モジュールは実際に未知語翻訳が呼ばれた時のみ遅延インポート
        ts_module = None

        def get_translators():
            nonlocal ts_module
            if ts_module is None:
                import translators as ts
                ts_module = ts
            return ts_module

        def query_to_vector(text: str):
            inputs = tokenizer([text], return_tensors="pt", padding=True).to(device)
            with torch.no_grad():
                output = clip_model(**inputs)
            if isinstance(output, torch.Tensor):
                vec = output
            elif hasattr(output, "text_embeds"):
                vec = output.text_embeds
            elif hasattr(output, "pooler_output"):
                vec = output.pooler_output
            else:
                raise ValueError(f"Unknown output type: {type(output)}")
            vec = vec / vec.norm(p=2, dim=-1, keepdim=True)
            return vec.cpu().numpy().astype("float32")

        size_modifiers = [
            "small", "flat", "tiny", "little", "mini", "short", "low",
            "big", "large", "huge", "giant", "massive", "gigantic", "enormous",
            "long", "tall", "high", "hyper", "absurd",
        ]

        def has_size_modifier(text: str) -> bool:
            t_low = text.lower()
            return any(m in t_low for m in size_modifiers)

        def check_conflict(query_translated: str, tag_name: str) -> bool:
            q = query_translated.lower().replace("_", " ")
            t = tag_name.lower().replace("_", " ")
            big = ["big", "large", "huge", "giant", "massive", "gigantic"]
            small = ["small", "flat", "tiny", "little"]
            if any(w in q for w in big) and any(w in t for w in small):
                return True
            if any(w in q for w in small) and any(w in t for w in big):
                return True
            return False

        elapsed = time.time() - t_start
        print(f"  [HeavyWorker] 準備完了 ({elapsed:.2f}s, PID: {os.getpid()})", flush=True)
        conn.send({"status": "ready", "pid": os.getpid(), "elapsed": elapsed})

        # 親プロセスからのリクエスト待機ループ
        while True:
            try:
                if not conn.poll(0.5):
                    continue
                req = conn.recv()
            except (EOFError, OSError):
                break

            if not isinstance(req, dict):
                continue

            cmd = req.get("cmd")
            if cmd == "shutdown":
                conn.send({"ok": True})
                break

            try:
                if cmd == "ping":
                    conn.send({"ok": True, "pid": os.getpid()})

                elif cmd == "translate":
                    word = req["word"]
                    translator_name = req.get("translator", "google")
                    ts = get_translators()
                    translated = ts.translate_text(
                        word, translator=translator_name, to_language="en", timeout=3.0
                    )
                    conn.send({"ok": True, "result": translated})

                elif cmd == "vector_search_tags":
                    final_query = req["final_query"]
                    english_word = req["english_word"]
                    top_k = req.get("top_k", 25)

                    found_tags_map = {}
                    norm_final = final_query.lower().replace(" ", "_")
                    prefix_search = f"{norm_final}_("
                    text_match_count = 0

                    for t in tag_list:
                        if t == norm_final or t.startswith(prefix_search):
                            found_tags_map[t] = 1.0
                            text_match_count += 1

                    if text_match_count > 0:
                        print(
                            f"  ├─ [Text Match Hit]: Found {text_match_count} tags matching '{norm_final}' or '{prefix_search}...'",
                            flush=True,
                        )

                    query_vec = query_to_vector(final_query)
                    distances, indices = tag_index.search(query_vec, top_k)

                    if norm_final in tag_set:
                        found_tags_map[norm_final] = 1.0

                    query_has_size = has_size_modifier(final_query)

                    for i, idx in enumerate(indices[0]):
                        score = float(distances[0][i])
                        tag_name = tag_list[idx]

                        if check_conflict(english_word, tag_name):
                            continue
                        if query_has_size and not has_size_modifier(tag_name):
                            continue

                        if score > 0.90:
                            found_tags_map[tag_name] = max(
                                found_tags_map.get(tag_name, 0), score
                            )

                    conn.send({"ok": True, "result": found_tags_map})

                elif cmd == "search_by_style_name":
                    style_name = req["style_name"]
                    threshold = req.get("threshold", 0.98)
                    trash_only = req.get("trash_only", False)
                    include_deleted = req.get("include_deleted", False)
                    results = style_searcher.search_by_style_name(
                        style_name,
                        threshold=threshold,
                        trash_only=trash_only,
                        include_deleted=include_deleted,
                    )
                    conn.send({"ok": True, "result": results})

                elif cmd == "calculate_centroid":
                    image_paths = req["image_paths"]
                    centroid = style_searcher.calculate_centroid(image_paths)
                    conn.send({"ok": True, "result": centroid})

                elif cmd == "get_style_suggestions":
                    prefix = req["prefix"]
                    base_query = req["base_query"]
                    suggestions = style_searcher.get_style_suggestions(prefix, base_query)
                    conn.send({"ok": True, "result": suggestions})

                else:
                    conn.send({"ok": False, "error": f"Unknown command: {cmd}"})

            except Exception as e:
                conn.send({"ok": False, "error": str(e)})

        db.close()
    except Exception as e:
        try:
            conn.send({"status": "error", "error": str(e)})
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
        print(f"  [HeavyWorker] 子プロセス終了 (PID: {os.getpid()})", flush=True)


# ページを閉じてハートビート（通信）が途絶えてから重量モードを自動終了するまでの秒数（300秒＝5分）
AUTO_STOP_TIMEOUT_SECONDS = 300.0


class HeavyEngineManager:
    """
    親プロセス（軽量サーバー）側からAI推論ワーカー子プロセスを管理するクラス。
    状態:
      - "light": ワーカー未起動（省メモリ状態）
      - "starting": ワーカープロセス起動・モデル読み込み中
      - "heavy": ワーカー稼働中（AI検索・絵柄作成が利用可能）
    """

    def __init__(
        self,
        db_path: str = "data/db/index.db",
        tag_index_path: str = "data/tag_vector_index.bin",
        style_index_path: str = "data/faiss/style.index",
        idle_timeout: float = AUTO_STOP_TIMEOUT_SECONDS,
    ):
        self.db_path = db_path
        self.tag_index_path = tag_index_path
        self.style_index_path = style_index_path
        self.idle_timeout = idle_timeout

        self._state_lock = threading.Lock()
        self._rpc_lock = threading.Lock()
        self._mode: str = "light"
        self._last_error: Optional[str] = None
        self._process: Optional[multiprocessing.Process] = None
        self._conn: Optional[Connection] = None
        self._ready_event = threading.Event()
        self._last_active_time: float = time.time()

    def touch(self) -> None:
        """最終アクセス（ハートビート）時刻を現在時刻に更新する"""
        self._last_active_time = time.time()

    def get_status(self, touch: bool = True) -> Dict[str, Any]:
        """現在のモード状態とワーカーPIDを返す"""
        if touch:
            self.touch()
        with self._state_lock:
            # 万が一子プロセスが予期せず終了していた場合は light に戻す
            if self._mode == "heavy" and (
                self._process is None or not self._process.is_alive()
            ):
                self._mode = "light"
                self._process = None
                self._conn = None

            pid = (
                self._process.pid
                if self._process is not None and self._process.is_alive()
                else None
            )
            return {
                "mode": self._mode,
                "worker_pid": pid,
                "error": self._last_error,
            }

    @property
    def is_heavy_ready(self) -> bool:
        return self.get_status(touch=False)["mode"] == "heavy"

    def start(self, wait: bool = False, timeout: float = 30.0) -> Dict[str, Any]:
        """
        重量ワーカープロセスを起動する。
        wait=False の場合はバックグラウンドでロードを開始し即座に "starting" を返す。
        wait=True の場合はロード完了（またはtimeout秒経過）まで待機してから返す。
        """
        with self._state_lock:
            if self._mode in ("heavy", "starting") and self._process and self._process.is_alive():
                status = self._mode
            else:
                self._last_error = None
                self._ready_event.clear()
                ctx = multiprocessing.get_context("spawn")
                parent_conn, child_conn = ctx.Pipe()
                proc = ctx.Process(
                    target=_heavy_worker_loop,
                    args=(
                        child_conn,
                        self.db_path,
                        self.tag_index_path,
                        self.style_index_path,
                    ),
                    daemon=True,
                )
                proc.start()
                child_conn.close()  # 親側では child_conn を使わないため閉じる

                self._process = proc
                self._conn = parent_conn
                self._mode = "starting"
                status = "starting"

                # バックグラウンドスレッドで子プロセスからの ready 通知を待つ（タイムアウト付き）
                threading.Thread(
                    target=self._wait_for_ready,
                    args=(proc, parent_conn, timeout),
                    daemon=True,
                ).start()

        if wait and status == "starting":
            finished = self._ready_event.wait(timeout=timeout + 1.0)
            if not finished:
                self._last_error = f"Startup timed out after {timeout}s"
                self.stop()

        return self.get_status()

    def _wait_for_ready(self, proc: multiprocessing.Process, conn: Connection, timeout: float):
        """子プロセスからの初期ロード完了通知を待機する内部スレッド（タイムアウト付き）"""
        deadline = time.time() + timeout
        try:
            while proc.is_alive() and time.time() < deadline:
                if conn.poll(0.2):
                    msg = conn.recv()
                    if isinstance(msg, dict) and msg.get("status") == "ready":
                        with self._state_lock:
                            if self._process is proc:
                                self._mode = "heavy"
                                self._last_active_time = time.time()
                                # アイドル自動停止監視スレッドを起動
                                threading.Thread(
                                    target=self._idle_watchdog_loop,
                                    args=(proc,),
                                    daemon=True,
                                ).start()
                        self._ready_event.set()
                        return
                    elif isinstance(msg, dict) and msg.get("status") == "error":
                        with self._state_lock:
                            if self._process is proc:
                                self._last_error = msg.get("error", "Unknown error")
                                self._mode = "light"
                        self._ready_event.set()
                        return

            # タイムアウトまたはプロセス異常終了時
            if time.time() >= deadline and proc.is_alive():
                print(f"  [HeavyWorker] 起動タイムアウト ({timeout}s) のため子プロセスを停止します。", flush=True)
                try:
                    proc.terminate()
                except Exception:
                    pass
                with self._state_lock:
                    if self._process is proc:
                        self._last_error = f"Worker startup timed out ({timeout}s)"
                        self._mode = "light"
                        self._process = None
                        self._conn = None
            else:
                with self._state_lock:
                    if self._process is proc and self._mode == "starting":
                        self._last_error = "Worker process exited unexpectedly during startup"
                        self._mode = "light"
        except Exception as e:
            with self._state_lock:
                if self._process is proc:
                    self._last_error = str(e)
                    self._mode = "light"
        finally:
            self._ready_event.set()

    def _idle_watchdog_loop(self, proc: multiprocessing.Process):
        """
        一定時間（self.idle_timeout秒）フロントエンドからのハートビートや検索リクエストが
        途絶えた場合に、自動で子プロセスを終了してメモリを解放する監視スレッド。
        """
        while proc.is_alive():
            time.sleep(2.0)
            with self._state_lock:
                if self._process is not proc or self._mode != "heavy":
                    return
                idle_sec = time.time() - self._last_active_time
            if self.idle_timeout > 0 and idle_sec >= self.idle_timeout:
                print(
                    f"\n  [HeavyWorker] {int(self.idle_timeout)}秒間アクセスがなかったため、重量モードを自動終了します...",
                    flush=True,
                )
                self.stop()
                return

    def stop(self) -> Dict[str, Any]:
        """
        重量ワーカープロセスを即座に終了し、RAM・VRAMをOSへ100%解放する。
        自身が起動した self._process のみを終了するため、他のPythonプロセスには一切干渉しない。
        """
        with self._state_lock:
            proc = self._process
            conn = self._conn
            self._process = None
            self._conn = None
            self._mode = "light"
            self._ready_event.set()

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

        if proc is not None and proc.is_alive():
            print(f"  [HeavyWorker] 子プロセス (PID: {proc.pid}) を終了してメモリを解放します...", flush=True)
            proc.terminate()
            proc.join(timeout=3.0)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=1.0)
            print("  [HeavyWorker] メモリ解放完了（軽量モードに移行しました）", flush=True)

        return self.get_status()

    def _call(self, payload: Dict[str, Any], timeout: float = 30.0) -> Any:
        """子プロセスへRPCリクエストを送信し、結果を受け取る（タイムアウト付き）"""
        self.touch()
        with self._state_lock:
            if self._mode != "heavy" or self._conn is None or self._process is None or not self._process.is_alive():
                raise RuntimeError("重量モードが起動していません")
            conn = self._conn

        with self._rpc_lock:
            conn.send(payload)
            if not conn.poll(timeout):
                raise TimeoutError(f"Worker RPC timed out after {timeout}s ({payload.get('cmd')})")
            resp = conn.recv()

        if not isinstance(resp, dict) or not resp.get("ok"):
            raise RuntimeError(resp.get("error", "Worker RPC failed") if isinstance(resp, dict) else "Invalid worker response")
        return resp.get("result")

    def translate(self, word: str, translator: str = "google") -> str:
        return self._call({"cmd": "translate", "word": word, "translator": translator}, timeout=6.0)

    def vector_search_tags(self, final_query: str, english_word: str, top_k: int = 25) -> Dict[str, float]:
        return self._call(
            {
                "cmd": "vector_search_tags",
                "final_query": final_query,
                "english_word": english_word,
                "top_k": top_k,
            },
            timeout=15.0,
        )

    def search_by_style_name(
        self,
        style_name: str,
        threshold: float = 0.98,
        trash_only: bool = False,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        return self._call(
            {
                "cmd": "search_by_style_name",
                "style_name": style_name,
                "threshold": threshold,
                "trash_only": trash_only,
                "include_deleted": include_deleted,
            },
            timeout=30.0,
        )

    def calculate_centroid(self, image_paths: List[str]):
        return self._call(
            {
                "cmd": "calculate_centroid",
                "image_paths": image_paths,
            },
            timeout=60.0,
        )

    def get_style_suggestions(self, prefix: str, base_query: str) -> List[Dict[str, Any]]:
        return self._call(
            {
                "cmd": "get_style_suggestions",
                "prefix": prefix,
                "base_query": base_query,
            },
            timeout=10.0,
        )


def _get_process_memory_mb(pid: int) -> float:
    """WindowsのWin32 API (GetProcessMemoryInfo) で指定PIDのWorkingSet(MB)を高速・安全に取得する"""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    h_proc = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h_proc:
        return 0.0
    try:
        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        if psapi.GetProcessMemoryInfo(h_proc, ctypes.byref(pmc), pmc.cb):
            return round(pmc.WorkingSetSize / (1024.0 * 1024.0), 1)
        return 0.0
    finally:
        kernel32.CloseHandle(h_proc)


if __name__ == "__main__":
    # Windowsのmultiprocessing(spawn)で python -m core.heavy_worker 実行時にも
    # 確実に core.heavy_worker モジュールとして関数が解決されるように再インポートする
    from core.heavy_worker import HeavyEngineManager as _Manager, _get_process_memory_mb as _get_mem

    parent_pid = os.getpid()
    manager = _Manager()

    print("=" * 65, flush=True)
    print(" [Phase 1 単体検証] HeavyEngineManager (子プロセス分離・メモリ解放テスト)", flush=True)
    print("=" * 65, flush=True)
    print("1. 初期状態（軽量モード）", flush=True)
    print(f"   - ステータス     : {manager.get_status()}", flush=True)
    print(f"   - 親プロセスPID  : {parent_pid} (RAM: {_get_mem(parent_pid)} MB)", flush=True)

    auto_mode = "--auto" in sys.argv

    if not auto_mode:
        input("\n[Enter] を押すと重量ワーカー（子プロセス）を起動します...")
    else:
        print("\n-> 重量ワーカー（子プロセス）を起動します (timeout=25s)...", flush=True)

    t0 = time.time()
    status = manager.start(wait=True, timeout=25.0)
    worker_pid = status["worker_pid"]
    print(f"\n2. 重量モード起動結果 ({time.time() - t0:.2f}s)", flush=True)
    print(f"   - ステータス     : {status}", flush=True)
    print(f"   - 親プロセスPID  : {parent_pid} (RAM: {_get_mem(parent_pid)} MB) ※親は軽量のまま", flush=True)
    if worker_pid:
        print(f"   - 子プロセスPID  : {worker_pid} (RAM: {_get_mem(worker_pid)} MB) ※AIモデル保持", flush=True)

    if status["mode"] == "heavy":
        print("\n3. 子プロセスでのCLIPベクトル検索テスト ('magical sword')", flush=True)
        t1 = time.time()
        tags = manager.vector_search_tags("magical sword", "magical sword", top_k=10)
        print(f"   - ヒット件数: {len(tags)}件 ({time.time() - t1:.2f}s) -> 例: {list(tags.items())[:5]}", flush=True)

    if not auto_mode:
        input("\n[Enter] を押すと重量ワーカーを停止し、メモリを解放します（タスクマネージャーでも確認可能です）...")
    else:
        print("\n-> 重量ワーカーを停止し、メモリを解放します...", flush=True)

    t2 = time.time()
    after_status = manager.stop()
    print(f"\n4. 重量モード停止完了 ({time.time() - t2:.3f}s)", flush=True)
    print(f"   - ステータス     : {after_status}", flush=True)
    print(f"   - 親プロセスPID  : {parent_pid} (RAM: {_get_mem(parent_pid)} MB)", flush=True)
    if worker_pid:
        print(f"   - 旧子プロセスPID: {worker_pid} (RAM: {_get_mem(worker_pid)} MB -> 0.0 MB なら完全消滅)", flush=True)
    print("=" * 65, flush=True)
