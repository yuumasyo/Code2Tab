"""
Code2Tab Launcher
=================
pywebview + Streamlit を組み合わせたネイティブウィンドウアプリのエントリーポイント。

動作モード:
  - ランチャーモード (デフォルト):
      空きポートを取得 → サーバーモードで自分自身をサブプロセス起動
      → Streamlit サーバーが立ち上がるのを待機 → pywebview でウィンドウを開く
  - サーバーモード (argv[1] == _SERVER_FLAG):
      Streamlit サーバーとして動作し、ランチャーの webview に応答する

PyInstaller でビルドした場合:
  sys.executable = Code2Tab.exe
  sys._MEIPASS   = 展開された一時ディレクトリ (app.py / src/ 等が入っている)
"""

import sys
import os
import socket
import subprocess
import time

# pywebview のバックエンドを import より前に確定させる (import 時にバックエンド選択が走るため)
# Qt (PySide6) バックエンドを使用。Python 3.12 で pythonnet ビルド不要の唯一の安定策。
os.environ['PYWEBVIEW_GUI'] = 'qt'

# サーバーモードを識別するための内部フラグ
_SERVER_FLAG = "--_code2tab_server"

# ─────────────────────────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────────────────────────

def find_free_port() -> int:
    """OS に空きポートを割り当てさせて番号を返す。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(port: int, timeout: float = 120.0) -> bool:
    """localhost:<port> への TCP 接続が成功するまで待機する。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def get_app_root() -> str:
    """
    app.py が置かれているディレクトリを返す。
    - PyInstaller フリーズ済み: sys._MEIPASS (そこに app.py を展開する)
    - 開発環境: このファイルの 1 つ上のディレクトリ (プロジェクトルート)
    """
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    # dist_pywebview/ の親ディレクトリ = プロジェクトルート
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────────────────────
# サーバーモード  (子プロセスとして起動)
# ─────────────────────────────────────────────────────────────

def run_server(port: int) -> None:
    """
    Streamlit サーバーとして起動する。
    ランチャーから [sys.executable, _SERVER_FLAG, str(port)] で呼ばれる。
    """
    root = get_app_root()

    # 作業ディレクトリを app.py のある場所に変更 (相対パス解決のため)
    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)

    app_path = os.path.join(root, "app.py")

    # Streamlit CLI を直接呼び出す
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", app_path,
        "--server.port",                 str(port),
        "--server.headless",             "true",
        "--server.enableCORS",           "false",
        "--server.enableXsrfProtection", "false",
        "--server.fileWatcherType",      "none",
        "--browser.gatherUsageStats",    "false",
        "--global.developmentMode",      "false",
    ]
    stcli.main()


# ─────────────────────────────────────────────────────────────
# ランチャーモード  (ウィンドウを持つメインプロセス)
# ─────────────────────────────────────────────────────────────

def run_launcher() -> None:
    """
    空きポートを決め → サーバーサブプロセスを起動 → 準備完了後に webview ウィンドウを開く。
    ウィンドウが閉じられたらサーバーを終了する。
    """
    port = find_free_port()

    # Windows: ターミナルウィンドウを出さずにサーバーを起動
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW

    server_proc = subprocess.Popen(
        [sys.executable, _SERVER_FLAG, str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )

    print(f"[Code2Tab] Streamlit サーバー起動中 (port={port})…")

    # ─ スプラッシュ用の簡易 HTML (サーバーが立ち上がるまで表示) ─
    splash_html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin:0; background:#0e1117; display:flex; flex-direction:column;
         align-items:center; justify-content:center; height:100vh;
         font-family:'Helvetica Neue', Arial, sans-serif; color:#fff; }
  .title  { font-size:2.2em; font-weight:bold; margin-bottom:0.3em; }
  .sub    { font-size:1em; color:#aaa; margin-bottom:2em; }
  .spinner{ width:48px; height:48px; border:5px solid #333;
            border-top-color:#ff4b4b; border-radius:50%;
            animation:spin 0.9s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .note   { margin-top:1.5em; font-size:0.85em; color:#666; }
</style>
</head>
<body>
  <div class="title">🎸 Code2Tab</div>
  <div class="sub">AI コード解析エンジンを起動しています…</div>
  <div class="spinner"></div>
  <div class="note">初回起動時は BTC モデルの読み込みに時間がかかる場合があります</div>
</body>
</html>"""

    import webview

    window = webview.create_window(
        title="Code2Tab 🎸",
        html=splash_html,       # まずスプラッシュを表示
        width=1400,
        height=900,
        resizable=True,
        min_size=(900, 600),
    )

    # ─ サーバーが立ち上がったら URL へ切り替えるスレッド ─
    def _switch_to_app():
        if wait_for_server(port, timeout=120):
            print(f"[Code2Tab] サーバー準備完了。アプリを読み込みます…")
            window.load_url(f"http://127.0.0.1:{port}")
        else:
            print("[Code2Tab] ERROR: サーバーが 120 秒以内に起動しませんでした。")
            error_html = """<body style='background:#0e1117;color:#ff4b4b;font-family:sans-serif;
                display:flex;align-items:center;justify-content:center;height:100vh;'>
                <div><h2>起動エラー</h2>
                <p>Streamlit サーバーの起動に失敗しました。<br>
                コンソールのログを確認してください。</p></div></body>"""
            window.load_html(error_html)

    import threading
    threading.Thread(target=_switch_to_app, daemon=True).start()

    # メインスレッドで webview を開始 (Windows 必須)
    webview.start()

    # ─ ウィンドウが閉じられたらサーバー (子孫プロセスを含む) を確実に終了 ─
    print("[Code2Tab] ウィンドウが閉じられました。サーバーを終了します…")
    if sys.platform == "win32":
        # /T で子孫プロセスまで含めてツリー全体を強制終了
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(server_proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        import signal as _sig
        try:
            os.killpg(os.getpgid(server_proc.pid), _sig.SIGTERM)
        except Exception:
            server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_proc.kill()


# ─────────────────────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == _SERVER_FLAG:
        # サーバーモード: ランチャーから起動された子プロセス
        run_server(int(sys.argv[2]))
    else:
        # ランチャーモード: ユーザーが直接 exe / スクリプトを起動
        run_launcher()
