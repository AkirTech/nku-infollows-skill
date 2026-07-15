"""
Trigger an immediate article poll on the backend.

Sends POST /api/rss/poll to fetch the latest articles from all subscriptions.
Timeout is dynamically calculated based on subscription count.
If the poll times out, checks /api/rss/status and waits for completion.
"""
import sys
import json
import time
import urllib.request
import urllib.error

from config import BACKEND_URL, print_header, print_ok, print_err, print_info


def get_subscription_count() -> int:
    """Fetch subscription count from backend. Returns 0 on failure."""
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/rss/subscriptions", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return len(data.get("data", []))
    except Exception:
        return 0


def calculate_poll_timeout(num_subs: int) -> int:
    """
    Calculate poll timeout based on subscription count.

    Backend polls subscriptions sequentially (~5-40s each with full content).
    Formula: base_overhead + num_subs * per_sub_time, clamped to [30, 300].

    Returns timeout in seconds.
    """
    BASE_OVERHEAD = 10
    PER_SUB_TIME = 10
    timeout = BASE_OVERHEAD + num_subs * PER_SUB_TIME
    return max(30, min(300, timeout))


def trigger_poll(timeout: int = 30) -> dict | None:
    """Trigger a poll. Returns parsed JSON response or None on failure/timeout."""
    url = f"{BACKEND_URL}/api/rss/poll"
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except TimeoutError:
        print(f"  [WARN] 拉取请求超时 ({timeout}s)，检查后端轮询器状态...")
        # Check if poll is still running on the backend
        try:
            with urllib.request.urlopen(f"{BACKEND_URL}/api/rss/status", timeout=5) as resp:
                status = json.loads(resp.read().decode("utf-8"))
                poller_data = status.get("data", {})
                if poller_data.get("running", False):
                    print(f"  [INFO] 轮询器仍在运行，等待完成 (最多 2 分钟)...")
                    for i in range(12):
                        time.sleep(10)
                        try:
                            with urllib.request.urlopen(f"{BACKEND_URL}/api/rss/status", timeout=3) as cr:
                                s2 = json.loads(cr.read().decode("utf-8"))
                                if not s2.get("data", {}).get("running", False):
                                    print_ok("轮询已完成")
                                    return None
                        except Exception:
                            pass
                    print("  [INFO] 等待超时，将继续使用数据库现有文章")
        except Exception:
            pass
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
        "--timeout", type=int, default=None,
        help="Request timeout in seconds (default: dynamically calculated from subscription count)"
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

    # Calculate dynamic timeout based on subscription count
    sub_count = get_subscription_count()
    if args.timeout is not None:
        poll_timeout = args.timeout
        print_info(f"订阅数: {sub_count}, 使用手动指定超时: {poll_timeout}s")
    else:
        poll_timeout = calculate_poll_timeout(sub_count)
        print_info(f"订阅数: {sub_count}, 动态计算超时: {poll_timeout}s")

    print_info("正在触发文章拉取...")
    result = trigger_poll(timeout=poll_timeout)

    if result is None:
        # Timeout or connection error — non-fatal for timeout
        return 0

    if result.get("success", False):
        message = result.get("data", {}).get("message", "拉取完成")
        print_ok(f"文章拉取成功: {message}")
    else:
        message = result.get("message", "未知错误")
        print_info(f"拉取结果: {message}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
