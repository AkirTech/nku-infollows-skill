"""
Single-mode orchestrator for nku-infollows-skill.

Handles the mechanical parts of the workflow (health check, subscription check,
poll trigger, article fetching) and outputs structured data for Claude to
complete the intelligent parts (keyword generation, recommendation scoring).

Usage:
    python orchestrator.py              # Full run (auto-starts backend if needed)
    python orchestrator.py --no-poll    # Skip poll trigger
    python orchestrator.py --no-start   # Don't auto-start backend
    python orchestrator.py --mode check # Only health + subscription check
"""
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import (
    BACKEND_URL,
    TEMP_DIR,
    ARTICLES_FILE,
    STATE_FILE,
    RECOMMENDATIONS_HTML,
    print_header,
    print_ok,
    print_err,
    print_info,
)

# Import backend startup helpers from check_backend
from check_backend import (
    check_backend_health,
    check_backend_auth,
    start_backend,
    wait_for_backend,
)

CST = timezone(timedelta(hours=8))


# ─── Health Check ───────────────────────────────────────────────
def check_backend(auto_start: bool = True) -> dict | None:
    """
    Check backend status. If auto_start is True and backend is not running,
    attempt to start it via start.bat / start.sh.
    Returns parsed JSON or None.
    """
    # Quick health check first
    if check_backend_health():
        return check_backend_auth()

    # Backend not reachable
    print_err(f"后端服务不可达: {BACKEND_URL}")

    if not auto_start:
        print_info("请手动启动后端后重试")
        return None

    print_info("尝试自动启动后端...")
    launched = start_backend()
    if not launched:
        return None

    if not wait_for_backend(timeout=30):
        return None

    # Re-check auth after successful startup
    return check_backend_auth()


# ─── Subscription Check ─────────────────────────────────────────
def get_subscriptions() -> list[dict]:
    """Fetch subscription list. Returns list or empty on failure."""
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/rss/subscriptions", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", [])
    except Exception as e:
        print_err(f"获取订阅列表失败: {e}")
        return []


# ─── Poll Trigger ────────────────────────────────────────────────
def trigger_poll() -> bool:
    """Trigger an article poll. Returns True on success."""
    try:
        req = urllib.request.Request(f"{BACKEND_URL}/api/rss/poll", method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            message = result.get("data", {}).get("message", str(result))
            print_ok(f"拉取触发成功: {message}")
            return True
    except Exception as e:
        print_err(f"触发拉取失败: {e}")
        return False


# ─── Article Fetching ────────────────────────────────────────────
def fetch_articles() -> tuple[list[dict], int]:
    """
    Fetch all articles via cursor pagination from /api/feed/articles.json.
    Returns (articles_list, final_next_since).
    """
    # Load previous state for incremental sync
    since = 0
    if STATE_FILE.exists():
        try:
            state = json.loads(open(STATE_FILE, "r", encoding="utf-8").read())
            since = state.get("next_since", 0)
            print_info(f"增量同步: since={since} ({datetime.fromtimestamp(since, CST).strftime('%Y-%m-%d %H:%M')})")
        except Exception:
            since = 0

    all_articles = []
    batch_count = 0
    max_batches = 100  # safety limit

    while batch_count < max_batches:
        url = f"{BACKEND_URL}/api/feed/articles.json?since={since}&limit=200"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print_err(f"获取文章失败 (since={since}): {e}")
            break

        batch = data.get("articles", [])
        next_since = data.get("next_since", since)

        if not batch:
            print_info("已获取全部文章")
            break

        all_articles.extend(batch)
        batch_count += 1
        since = next_since
        print_info(f"第 {batch_count} 批: {len(batch)} 篇 (累计 {len(all_articles)}, next_since={next_since})")

        # Small delay between batches as courtesy
        if len(batch) == 200:
            time.sleep(0.3)

    if batch_count >= max_batches:
        print_err(f"达到最大批次限制 ({max_batches})，可能存在异常")

    # Save state for next run
    if all_articles:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"next_since": since, "updated_at": datetime.now(CST).isoformat()}, f)

    return all_articles, since


# ─── Save Raw Articles ──────────────────────────────────────────
def save_raw_articles(articles: list[dict]) -> Path:
    """Save articles (without keywords) to JSON. Returns file path."""
    raw_file = TEMP_DIR / "articles_raw.json"
    # Extract only the fields we need for Claude
    simplified = []
    for a in articles:
        simplified.append({
            "id": a.get("id"),
            "title": a.get("title", ""),
            "link": a.get("link", ""),
            "author": a.get("author", ""),
            "nickname": a.get("nickname", ""),
            "publish_time": a.get("publish_time", 0),
            "digest": a.get("digest", ""),
        })

    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(simplified, f, ensure_ascii=False, indent=2)

    return raw_file


# ─── Main ────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="nku-infollows-skill orchestrator")
    parser.add_argument("--no-poll", action="store_true", help="Skip poll trigger")
    parser.add_argument("--no-start", action="store_true", help="Don't auto-start backend")
    parser.add_argument("--mode", choices=["full", "check", "fetch"], default="full",
                        help="Run mode: full (all), check (health+subs only), fetch (skip poll, just fetch)")
    args = parser.parse_args()

    # ── Step 1: Health Check ──
    print_header("Step 1/5: 检查后端服务状态")
    status = check_backend(auto_start=not args.no_start)

    if status is None:
        print_err(f"无法连接到后端服务: {BACKEND_URL}")
        print_info("提示: 移除 --no-start 可自动启动后端")
        return 1

    authenticated = status.get("authenticated", False)
    is_expired = status.get("isExpired", True)
    nickname = status.get("nickname", "")
    fakeid = status.get("fakeid", "")

    if not authenticated or is_expired:
        print_err("后端未登录或登录已过期!")
        print_info(f"请在浏览器中打开 {BACKEND_URL}/login.html 扫码登录")
        return 1

    print_ok(f"后端服务正常 — 登录用户: {nickname} ({fakeid})")

    if args.mode == "check":
        print_ok("检查模式完成")
        return 0

    # ── Step 2: Subscription Check ──
    print_header("Step 2/5: 检查订阅列表")
    subs = get_subscriptions()

    if not subs:
        print_err("订阅列表为空!")
        print_info(f"请先在 {BACKEND_URL}/rss.html 中搜索并订阅公众号")
        return 1

    print_ok(f"已订阅 {len(subs)} 个公众号:")
    for s in subs:
        count = s.get("article_count", 0)
        name = s.get("nickname", s.get("fakeid", "?"))
        print(f"    📌 {name} ({count} 篇)")

    if args.mode == "fetch":
        # ── Step 3 (skip poll) ──
        pass  # Skip poll, go directly to fetch
    else:
        # ── Step 3: Trigger Poll ──
        if not args.no_poll:
            print_header("Step 3/5: 触发文章拉取")
            trigger_poll()
            print_info("等待 5 秒让后端完成拉取...")
            time.sleep(5)
        else:
            print_info("跳过拉取触发 (--no-poll)")

    # ── Step 4: Fetch Articles ──
    print_header("Step 4/5: 获取文章列表")
    articles, final_since = fetch_articles()

    if not articles:
        print_err("未获取到任何文章!")
        print_info("请确认: 1) 已订阅公众号  2) 后端已登录  3) 订阅的公众号有发布文章")
        return 1

    print_ok(f"共获取 {len(articles)} 篇文章")

    # Save raw articles for Claude
    raw_file = save_raw_articles(articles)
    print_info(f"原始文章数据已保存: {raw_file}")

    # ── Step 5: Instruct Claude ──
    print_header("Step 5/5: 下一步 — 关键词生成")
    print(f"""
    ┌──────────────────────────────────────────────────────────┐
    │                                                          │
    │  请 Claude 完成以下步骤:                                  │
    │                                                          │
    │  1. 阅读 {raw_file}                                      │
    │  2. 为每篇文章生成 keywords (基于标题 + 作者)              │
    │     格式: "关键词1 | 关键词2 | 关键词3"                    │
    │  3. 标记 recommended: true/false (评估文章价值)           │
    │  4. 保存为 {ARTICLES_FILE}                               │
    │     格式: [{{"id":int, "title":str, "link":str,           │
    │             "author":str, "keywords":str,                 │
    │             "publish_time":int, "recommended":bool}}]     │
    │  5. 运行: python {Path(__file__).parent / 'generate_html.py'} │
    │  6. 打开浏览器查看推荐页面                                │
    │                                                          │
    │  共 {len(articles)} 篇文章待处理                          │
    │                                                          │
    └──────────────────────────────────────────────────────────┘
    """)

    # Summary stats
    authors = {}
    for a in articles:
        author = a.get("author", a.get("nickname", "未知"))
        authors[author] = authors.get(author, 0) + 1

    print_info("按作者统计:")
    for author, count in sorted(authors.items(), key=lambda x: -x[1]):
        print(f"    {author}: {count} 篇")

    # Time range
    times = [a.get("publish_time", 0) for a in articles if a.get("publish_time")]
    if times:
        oldest = datetime.fromtimestamp(min(times), CST).strftime("%Y-%m-%d")
        newest = datetime.fromtimestamp(max(times), CST).strftime("%Y-%m-%d")
        print_info(f"时间范围: {oldest} ~ {newest}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
