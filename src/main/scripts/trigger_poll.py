"""
Trigger an immediate article poll on the backend.

Sends POST /api/rss/poll to fetch the latest articles from all subscriptions.
Timeout is non-fatal: articles may already be in the database from prior polls.
"""
import sys
import json
import urllib.request
import urllib.error

from config import BACKEND_URL, print_header, print_ok, print_err, print_info


def trigger_poll(timeout: int = 30) -> dict | None:
    """Trigger a poll. Returns parsed JSON response or None on failure."""
    url = f"{BACKEND_URL}/api/rss/poll"
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except TimeoutError:
        print("  [WARN] 拉取请求超时（后端可能仍在处理，或已触发频率限制）")
        print("  [INFO] 这不影响后续流程 — 数据库可能已有文章，请继续获取")
        return None
    except urllib.error.URLError as e:
        print_err(f"无法连接到后端服务: {e.reason}")
        return None
    except Exception as e:
        print_err(f"触发拉取时发生错误: {e}")
        return None


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Trigger an article poll on the backend")
    parser.add_argument(
        "--timeout", type=int, default=30,
        help="Request timeout in seconds (default: 30)"
    )
    args = parser.parse_args()

    print_header("触发文章拉取")

    # First check if backend is reachable
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/health", timeout=5):
            pass
    except Exception as e:
        print_err(f"后端服务不可达: {e}")
        return 1

    print_info("正在触发文章拉取...")
    result = trigger_poll(timeout=args.timeout)

    if result is None:
        # Timeout or connection error — connection error already printed
        # For timeout, it's non-fatal; for connection error, it's fatal
        return 0  # non-fatal: articles may still be in DB

    if result.get("success", False):
        message = result.get("data", {}).get("message", "拉取完成")
        print_ok(f"文章拉取成功: {message}")
    else:
        message = result.get("message", "未知错误")
        print_info(f"拉取结果: {message}")

    print_info("请稍等几秒让后端完成拉取后再获取文章")
    return 0


if __name__ == "__main__":
    sys.exit(main())
