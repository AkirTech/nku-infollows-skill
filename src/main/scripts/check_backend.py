"""
Check if the wechat-download-api backend is running and authenticated.

With --start: if backend is not running, attempt to start it.
Prefers direct uvicorn launch (fast, trackable) over start.bat (slow, blind).
Falls back to start.bat / start.sh when venv is not ready.

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

# Where uvicorn startup output is logged (for progress tracking)
_UVICORN_LOG = BACKEND_DIR / "data" / "uvicorn_startup.log"

# Default wait timeout (seconds)
DEFAULT_WAIT_TIMEOUT = 120


def _backend_http(path: str, timeout: int = 5) -> dict | None:
    """Make a GET request to the backend. Returns parsed JSON or None."""
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _venv_python() -> Path | None:
    """Return the path to the venv Python executable, or None."""
    system = platform.system()
    if system == "Windows":
        python_exe = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
    else:
        python_exe = BACKEND_DIR / "venv" / "bin" / "python"
    if python_exe.exists():
        return python_exe
    return None


def check_venv_ready() -> bool:
    """
    Check if the backend venv exists and has key dependencies installed.
    A ready venv means we can launch uvicorn directly — no setup needed.
    """
    python_exe = _venv_python()
    if python_exe is None:
        print_info("虚拟环境未创建，将使用 start.bat 完整安装")
        return False

    # Try importing the two essential packages
    try:
        result = subprocess.run(
            [str(python_exe), "-c", "import fastapi, uvicorn; print('OK')"],
            capture_output=True, text=True, timeout=15,
            cwd=str(BACKEND_DIR),
        )
        if result.returncode == 0 and "OK" in result.stdout:
            return True
        print_info("虚拟环境依赖不完整，将使用 start.bat 安装")
        return False
    except Exception as e:
        print_info(f"虚拟环境检测失败: {e}")
        return False


def setup_backend_env() -> bool:
    """
    Install backend Python dependencies via pip. Shows progress.
    Returns True on success.
    """
    python_exe = _venv_python()
    if python_exe is None:
        # No venv at all — create one first
        print_info("创建虚拟环境...")
        system_python = "python"
        try:
            subprocess.run(
                [system_python, "-m", "venv", str(BACKEND_DIR / "venv")],
                check=True, capture_output=True, text=True, timeout=60,
                cwd=str(BACKEND_DIR),
            )
            python_exe = _venv_python()
            if python_exe is None:
                print_err("虚拟环境创建失败")
                return False
            print_ok("虚拟环境已创建")
        except subprocess.CalledProcessError as e:
            print_err(f"虚拟环境创建失败: {e.stderr}")
            return False

    # Install dependencies
    req_file = BACKEND_DIR / "requirements.txt"
    if not req_file.exists():
        print_err(f"未找到 requirements.txt: {req_file}")
        return False

    print_info("安装后端依赖 (pip install -r requirements.txt)...")
    try:
        proc = subprocess.Popen(
            [str(python_exe), "-m", "pip", "install", "-r", str(req_file)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=str(BACKEND_DIR),
        )
        # Stream output line by line, showing key progress lines
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            # Show meaningful lines; skip progress bars
            if any(kw in line.lower() for kw in ["requirement already satisfied",
                                                   "installing",
                                                   "successfully installed",
                                                   "error", "failed"]):
                print(f"  {line}")
        proc.wait(timeout=300)
        if proc.returncode == 0:
            print_ok("依赖安装完成")
            return True
        else:
            print_err(f"依赖安装失败 (exit {proc.returncode})")
            return False
    except Exception as e:
        print_err(f"依赖安装出错: {e}")
        return False


def check_backend_health() -> bool:
    """Check if backend is reachable. Returns True if responding."""
    result = _backend_http("/api/health", timeout=3)
    return result is not None


def check_backend_auth() -> dict | None:
    """Check backend auth status. Returns parsed JSON or None."""
    return _backend_http("/api/admin/status", timeout=5)


def get_start_command() -> list[str] | None:
    """
    Determine the platform-appropriate startup command.
    Returns a list of command arguments, or None if no start script found.
    """
    system = platform.system()

    if system == "Windows":
        bat = BACKEND_DIR / "start.bat"
        if bat.exists():
            return ["cmd", "/c", "start", str(bat)]
        return None
    else:
        sh = BACKEND_DIR / "start.sh"
        if sh.exists():
            return ["bash", str(sh)]
        return None


def start_uvicorn_direct() -> subprocess.Popen | None:
    """
    Start uvicorn directly from the venv (fast path — no start.bat overhead).
    Returns the Popen instance, or None on failure.
    """
    python_exe = _venv_python()
    if python_exe is None:
        return None

    # Ensure data directory exists for the log
    log_dir = _UVICORN_LOG.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = open(str(_UVICORN_LOG), "w", encoding="utf-8")

    try:
        proc = subprocess.Popen(
            [str(python_exe), "-m", "uvicorn", "app:app",
             "--host", "0.0.0.0", "--port", "5000",
             "--log-level", "info"],
            cwd=str(BACKEND_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            # Detach from parent so it survives after this script exits
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            start_new_session=True,
        )
        return proc
    except Exception as e:
        print_err(f"启动 uvicorn 失败: {e}")
        log_file.close()
        return None


def _read_startup_log() -> str:
    """Read the last few lines of the uvicorn startup log for progress display."""
    try:
        if _UVICORN_LOG.exists():
            lines = _UVICORN_LOG.read_text(encoding="utf-8").strip().splitlines()
            # Return the last meaningful line
            for line in reversed(lines):
                line = line.strip()
                if line and not line.startswith("INFO:"):
                    return line
                if "Application startup" in line:
                    return line
            if lines:
                return lines[-1].strip()
    except Exception:
        pass
    return ""


def start_backend() -> bool:
    """
    Attempt to start the backend.
    Tries direct uvicorn launch first (fast, trackable).
    Falls back to start.bat / start.sh (slow, full setup).
    Returns True if the start command was launched.
    """
    # ── Fast path: check if venv is ready for direct uvicorn launch ──
    if check_venv_ready():
        print_info("虚拟环境就绪，直接启动 uvicorn (快速模式)...")
        proc = start_uvicorn_direct()
        if proc is not None:
            print_ok(f"uvicorn 已启动 (pid={proc.pid})")
            return True
        print_info("直接启动失败，回退到 start.bat...")

    # ── Almost-ready path: venv exists but deps missing ──
    python_exe = _venv_python()
    if python_exe is not None:
        print_info("虚拟环境存在但依赖缺失，尝试安装后直接启动...")
        if setup_backend_env():
            proc = start_uvicorn_direct()
            if proc is not None:
                print_ok(f"uvicorn 已启动 (pid={proc.pid})")
                return True

    # ── Slow path: full start.bat / start.sh ──
    cmd = get_start_command()
    if cmd is None:
        print_err(f"未找到启动脚本 (start.bat / start.sh) 在 {BACKEND_DIR}")
        return False

    print_info(f"启动后端服务: {' '.join(cmd)}")
    print_info(f"后端目录: {BACKEND_DIR}")

    try:
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(
                cmd,
                cwd=str(BACKEND_DIR),
                shell=False,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen(
                cmd,
                cwd=str(BACKEND_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        return True
    except Exception as e:
        print_err(f"启动后端失败: {e}")
        return False


def wait_for_backend(timeout: int = DEFAULT_WAIT_TIMEOUT, interval: float = 2.0) -> bool:
    """
    Poll the backend health endpoint until it responds or timeout.
    Shows startup progress from uvicorn log when available.
    Returns True when backend becomes reachable.
    """
    print_info(f"等待后端启动 (最多 {timeout}s)...")
    start_time = time.time()
    last_log_line = ""

    while time.time() - start_time < timeout:
        if check_backend_health():
            elapsed = time.time() - start_time
            print()
            print_ok(f"后端服务已启动 (耗时 {elapsed:.0f}s)")
            return True

        # Progress: show elapsed time
        elapsed = time.time() - start_time

        # Check uvicorn log for progress
        log_line = _read_startup_log()
        if log_line and log_line != last_log_line:
            last_log_line = log_line
            print(f"\n  [{elapsed:.0f}s] {log_line}", end="", flush=True)
        else:
            print(".", end="", flush=True)

        time.sleep(interval)

    print()
    # Show the last log lines for diagnostics
    if _UVICORN_LOG.exists():
        print_info("最近的后端日志:")
        try:
            lines = _UVICORN_LOG.read_text(encoding="utf-8").strip().splitlines()
            for line in lines[-5:]:
                print(f"    {line.strip()}")
        except Exception:
            pass

    print_err(f"后端在 {timeout}s 内未响应，请手动检查")
    return False


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Check backend health and auth status")
    parser.add_argument(
        "--start", action="store_true",
        help="If backend is not running, attempt to start it (direct uvicorn or start.bat/start.sh)"
    )
    parser.add_argument(
        "--no-start", action="store_true",
        help="Do not attempt to start the backend (just report status)"
    )
    parser.add_argument(
        "--wait", type=int, default=DEFAULT_WAIT_TIMEOUT,
        help=f"Max seconds to wait for backend startup (default: {DEFAULT_WAIT_TIMEOUT})"
    )
    parser.add_argument(
        "--force-bat", action="store_true",
        help="Force using start.bat/start.sh even if venv is ready (for full reinstall)"
    )
    args = parser.parse_args()

    print_header("检查后端服务状态")

    # ── Pre-flight: show venv status ──
    venv_ready = check_venv_ready()

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

            # If venv was just detected as ready, use fast path
            # (check_venv_ready was already called above)
            if args.force_bat:
                print_info("--force-bat: 强制使用启动脚本")
                # Bypass the direct-start logic in start_backend by temporarily
                # using the bat path directly
                cmd = get_start_command()
                if cmd is None:
                    print_err(f"未找到启动脚本")
                    return 1
                try:
                    system = platform.system()
                    if system == "Windows":
                        subprocess.Popen(
                            cmd, cwd=str(BACKEND_DIR), shell=False,
                            creationflags=subprocess.CREATE_NEW_CONSOLE,
                        )
                    else:
                        subprocess.Popen(
                            cmd, cwd=str(BACKEND_DIR),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True,
                        )
                    launched = True
                except Exception as e:
                    print_err(f"启动失败: {e}")
                    launched = False
            else:
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
