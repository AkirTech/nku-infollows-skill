"""
Check if the wechat-download-api backend is running and authenticated.

With --start: if backend is not running, attempt to start it using
the backend's own start.bat (Windows) or start.sh (Linux/macOS),
then wait for it to become ready.

Exit 0: backend is healthy and authenticated.
Exit 1: backend is unreachable or not authenticated.
"""
import sys
import json
import time
import subprocess
import platform
import urllib.request
import urllib.error
from pathlib import Path

# Ensure clean Unicode output on Windows (loaded before config's own reconfigure)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import BACKEND_URL, print_header, print_ok, print_err, print_info

# Path to backend directory (relative to this script's location)
SCRIPTS_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = SCRIPTS_DIR.parent.parent / "backend" / "wechat-download-api"


def _backend_http(path: str, timeout: int = 5) -> dict | None:
    """Make a GET request to the backend. Returns parsed JSON or None."""
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def check_backend_health() -> bool:
    """Check if backend is reachable. Returns True if responding."""
    result = _backend_http("/api/health", timeout=3)
    return result is not None


def check_backend_auth() -> dict | None:
    """Check backend auth status. Returns parsed JSON or None."""
    return _backend_http("/api/admin/status", timeout=5)


def get_start_command() -> list[str] | None:
    """
    Determine the appropriate start command for the current platform.
    Returns a list of command arguments, or None if no start script found.
    """
    system = platform.system()

    if system == "Windows":
        bat = BACKEND_DIR / "start.bat"
        if bat.exists():
            # start.bat uses `cmd /k` internally, so it opens its own window.
            # We just need to launch it and return — it runs independently.
            return ["cmd", "/c", "start", str(bat)]
        return None

    else:
        # Linux / macOS
        sh = BACKEND_DIR / "start.sh"
        if sh.exists():
            # start.sh is interactive; run it in background mode.
            # The script uses `python app.py` which runs in foreground.
            # We background it with nohup so it survives after this script exits.
            return ["bash", str(sh)]
        return None


def start_backend() -> bool:
    """
    Attempt to start the backend using the platform-appropriate script.
    Returns True if the start command was launched.
    """
    cmd = get_start_command()
    if cmd is None:
        print_err(f"未找到启动脚本 (start.bat / start.sh) 在 {BACKEND_DIR}")
        return False

    print_info(f"启动后端服务: {' '.join(cmd)}")
    print_info(f"后端目录: {BACKEND_DIR}")

    try:
        system = platform.system()
        if system == "Windows":
            # start.bat opens its own window — just launch and return
            subprocess.Popen(
                cmd,
                cwd=str(BACKEND_DIR),
                shell=False,
                creationflags=subprocess.CREATE_NEW_CONSOLE,  # new window
            )
        else:
            # Linux/macOS: run start.sh in background
            # start.sh does everything (venv, deps, then runs python app.py in foreground).
            # Use nohup to detach it so it survives after this script exits.
            subprocess.Popen(
                cmd,
                cwd=str(BACKEND_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # detach from parent process group
            )
        return True
    except Exception as e:
        print_err(f"启动后端失败: {e}")
        return False


def wait_for_backend(timeout: int = 30, interval: float = 2.0) -> bool:
    """
    Poll the backend health endpoint until it responds or timeout.
    Returns True when backend becomes reachable.
    """
    print_info(f"等待后端启动 (最多 {timeout}s)...")
    start_time = time.time()
    dots = 0

    while time.time() - start_time < timeout:
        if check_backend_health():
            print()
            print_ok("后端服务已启动")
            return True
        print(".", end="", flush=True)
        time.sleep(interval)

    print()
    print_err(f"后端在 {timeout}s 内未响应，请手动检查")
    return False


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Check backend health and auth status")
    parser.add_argument(
        "--start", action="store_true",
        help="If backend is not running, attempt to start it via start.bat/start.sh"
    )
    parser.add_argument(
        "--no-start", action="store_true",
        help="Do not attempt to start the backend (just report status)"
    )
    parser.add_argument(
        "--wait", type=int, default=30,
        help="Max seconds to wait for backend startup (default: 30)"
    )
    args = parser.parse_args()

    print_header("检查后端服务状态")

    # ── Check if backend is reachable ──
    is_healthy = check_backend_health()

    if not is_healthy:
        print_err(f"后端服务不可达: {BACKEND_URL}")

        if args.no_start:
            print_info("请手动启动后端后重试")
            print_info(f"  Windows: {BACKEND_DIR / 'start.bat'}")
            print_info(f"  Linux:   bash {BACKEND_DIR / 'start.sh'}")
            return 1

        if args.start:
            print_info("尝试自动启动后端...")
            launched = start_backend()
            if not launched:
                print_info("请手动启动后端:")
                print_info(f"  cd {BACKEND_DIR}")
                if platform.system() == "Windows":
                    print_info(f"  {BACKEND_DIR / 'start.bat'}")
                else:
                    print_info(f"  bash {BACKEND_DIR / 'start.sh'}")
                return 1

            if not wait_for_backend(timeout=args.wait):
                return 1
        else:
            print_info("提示: 使用 --start 参数可自动启动后端")
            print_info(f"  或手动启动: cd {BACKEND_DIR}")
            if platform.system() == "Windows":
                print_info(f"  运行 {BACKEND_DIR / 'start.bat'}")
            else:
                print_info(f"  运行 bash {BACKEND_DIR / 'start.sh'}")
            return 1

    else:
        print_ok(f"后端服务运行中: {BACKEND_URL}")

    # ── Check auth status ──
    data = check_backend_auth()
    if data is None:
        print_err("无法获取后端认证状态")
        return 1

    authenticated = data.get("authenticated", False)
    nickname = data.get("nickname", "")
    status = data.get("status", "unknown")
    is_expired = data.get("isExpired", True)

    print_info(f"服务状态: {status}")
    print_info(f"登录用户: {nickname or '(未登录)'}")

    if not authenticated or is_expired:
        print_err("后端未登录或登录已过期!")
        print_info(f"请在浏览器中打开 {BACKEND_URL}/login.html 扫码登录")
        return 1

    print_ok(f"后端服务运行正常，已登录为 {nickname}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
