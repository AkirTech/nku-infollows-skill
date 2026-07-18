"""
Lark/Feishu helper for nku-infollows-skill.

Handles lark-cli interactions:
- Check auth status
- Fetch unfinished tasks
- Fetch recent messages (for potential task detection)
- Parse and save structured data for HTML generation

Usage:
    python lark_helper.py auth                        # Check auth status
    python lark_helper.py fetch-tasks                 # Fetch incomplete tasks → lark_tasks.json
    python lark_helper.py fetch-tasks --include-completed  # Include completed tasks
    python lark_helper.py fetch-messages              # Fetch recent 7-day messages → raw file
    python lark_helper.py fetch-messages --days 3     # Custom day range
    python lark_helper.py save-tasks <json_file>      # Save pre-fetched task JSON
    python lark_helper.py save-analysis <json_file>   # Save message analysis JSON
    python lark_helper.py check                       # Quick check: auth + task count + message count
"""

import sys
import json
import subprocess
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import (
    LARK_TASKS_FILE,
    LARK_MESSAGES_FILE,
    TEMP_DIR,
    print_header,
    print_ok,
    print_err,
    print_info,
)

CST = timezone(timedelta(hours=8))


# ─── CLI Runner ────────────────────────────────────────────────────

def _run_lark(args: list[str], timeout: int = 30, add_format: bool = True) -> dict:
    """Run a lark-cli command and return parsed JSON.

    Args:
        args: lark-cli subcommand and flags (e.g. ['task', '+get-my-tasks'])
        timeout: command timeout in seconds
        add_format: whether to append --format json (some commands like 'auth status'
                    don't support it but already output JSON by default)
    """
    # Resolve lark-cli path (on Windows it's a .cmd wrapper)
    lark_cli = _find_lark_cli()
    if lark_cli is None:
        print_err("lark-cli 未安装或不在 PATH 中")
        print_info("请运行: npm install -g @larksuite/cli")
        return {"ok": False, "error": "lark-cli not found"}

    cmd = [lark_cli] + args
    if add_format:
        cmd += ["--format", "json"]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or "unknown error"
            print_err(f"lark-cli 命令失败: {' '.join(cmd)}")
            print_err(f"  stderr: {stderr[:500]}")
            return {"ok": False, "error": stderr}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        print_err(f"lark-cli 命令超时 ({timeout}s): {' '.join(cmd)}")
        return {"ok": False, "error": "timeout"}
    except json.JSONDecodeError as e:
        print_err(f"lark-cli 输出 JSON 解析失败: {e}")
        return {"ok": False, "error": str(e)}
    except FileNotFoundError:
        print_err("lark-cli 未安装或不在 PATH 中")
        print_info("请运行: npm install -g @larksuite/cli")
        return {"ok": False, "error": "lark-cli not found"}


def _find_lark_cli() -> Optional[str]:
    """Find the lark-cli executable path."""
    import shutil

    # Try bare command
    found = shutil.which("lark-cli")
    if found:
        return found

    # Windows: check npm global prefix
    npm_prefix = None
    try:
        r = subprocess.run(
            ["npm", "config", "get", "prefix"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            npm_prefix = r.stdout.strip()
    except Exception:
        pass

    if npm_prefix:
        for ext in (".cmd", ".ps1", "", ".exe"):
            candidate = Path(npm_prefix) / f"lark-cli{ext}"
            if candidate.exists():
                return str(candidate)

    return None


# ─── Helpers ──────────────────────────────────────────────────────

def _sanitize_str(s: str) -> str:
    """Remove surrogate characters that can break JSON encoding."""
    if not isinstance(s, str):
        return s
    return s.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


# ─── Auth Check ────────────────────────────────────────────────────

def _auth_result_ok(auth: dict) -> bool:
    """Determine if auth result indicates authenticated user."""
    if auth.get("ok") and isinstance(auth.get("ok"), bool):
        return True
    # lark-cli auth status doesn't have 'ok', check identities directly
    user = auth.get("identities", {}).get("user", {})
    return user.get("available", False)


def check_auth() -> dict:
    """Check lark-cli auth status. Returns parsed status dict."""
    print_info("检查飞书登录状态...")
    result = _run_lark(["auth", "status"], add_format=False)
    if _auth_result_ok(result):
        user = result.get("identities", {}).get("user", {})
        bot = result.get("identities", {}).get("bot", {})
        print_ok(f"飞书已登录 — 用户: {user.get('userName', '?')} ({user.get('openId', '?')})")
        if bot.get("available"):
            print_ok(f"Bot 身份可用")
        result["ok"] = True
    else:
        print_err("飞书未登录或登录已过期")
        result["ok"] = False
    return result


def is_authenticated() -> bool:
    """Quick check: is lark-cli logged in as user?"""
    result = _run_lark(["auth", "status"], add_format=False)
    return _auth_result_ok(result)


# ─── Task Fetching ─────────────────────────────────────────────────

def fetch_tasks(include_completed: bool = False, page_all: bool = True) -> dict:
    """
    Fetch my tasks via lark-cli (both assigned-to-me and created-by-me).
    Uses +get-my-tasks first, then +get-related-tasks for tasks without assignee.
    Returns merged task data or empty dict on failure.
    """
    print_info(f"获取{'全部' if include_completed else '未完成'}任务...")

    all_items = []
    seen = set()

    # First: tasks assigned to me
    args = ["task", "+get-my-tasks"]
    if not include_completed:
        args.append("--complete=false")
    if page_all:
        args.extend(["--page-all"])

    result = _run_lark(args, timeout=30)
    if result.get("ok"):
        for item in result.get("data", {}).get("items", []):
            guid = item.get("guid", "")
            if guid and guid not in seen:
                seen.add(guid)
                all_items.append(item)

    # Second: tasks I created but may not be assigned to me
    args2 = ["task", "+get-related-tasks", "--created-by-me"]
    if not include_completed:
        args2.append("--include-complete=false")
    if page_all:
        args2.extend(["--page-all"])

    result2 = _run_lark(args2, timeout=30)
    if result2.get("ok"):
        for item in result2.get("data", {}).get("items", []):
            guid = item.get("guid", "")
            if guid and guid not in seen:
                seen.add(guid)
                all_items.append(item)

    if not all_items and not result.get("ok") and not result2.get("ok"):
        print_err("获取任务失败")
        return {}

    print_ok(f"获取到 {len(all_items)} 个任务")
    return {"items": all_items}


def save_tasks(tasks_data: dict, filepath: Path = LARK_TASKS_FILE) -> Path:
    """Save task data to the standard tasks JSON file.

    Accepts both formats:
    - +get-my-tasks: {completed: bool, guid, summary, due_at, ...}
    - +get-related-tasks: {status: "todo"/"done", guid, summary, ...}
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Simplify task structure for HTML rendering
    simplified = []
    for item in tasks_data.get("items", []):
        # Handle +get-related-tasks format (status: "todo"/"done")
        is_completed = item.get("completed", None)
        if is_completed is None:
            is_completed = item.get("status", "todo") != "todo"

        simplified.append({
            "id": item.get("guid", ""),
            "title": _sanitize_str(item.get("summary", "未命名任务")),
            "description": _sanitize_str(item.get("description", "")),
            "due_at": item.get("due_at", ""),
            "created_at": item.get("created_at", ""),
            "completed": is_completed,
            "url": item.get("url", ""),
            "source": "lark",
        })

    output = {
        "unfinished_tasks": [t for t in simplified if not t["completed"]],
        "completed_tasks": [t for t in simplified if t["completed"]],
        "total": len(simplified),
        "fetched_at": datetime.now(CST).isoformat(),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print_ok(f"任务数据已保存: {filepath} ({len(simplified)} 个)")
    return filepath


# ─── Task Creation ────────────────────────────────────────────────

# Cache for user identity lookups
_USER_OPEN_ID: Optional[str] = None
_TASKLIST_GUID: Optional[str] = None
_TASKLIST_NAME = "NKU-InFollows 待办"


def _get_user_open_id() -> Optional[str]:
    """Get current user's open_id from lark-cli auth, cached."""
    global _USER_OPEN_ID
    if _USER_OPEN_ID:
        return _USER_OPEN_ID

    result = _run_lark(["auth", "status"], add_format=False)
    user = result.get("identities", {}).get("user", {})
    if user.get("available"):
        _USER_OPEN_ID = user.get("openId", "")
        return _USER_OPEN_ID
    return None


def _get_or_create_tasklist() -> Optional[str]:
    """Get or create the default NKU-InFollows tasklist. Returns guid."""
    global _TASKLIST_GUID
    if _TASKLIST_GUID:
        return _TASKLIST_GUID

    # Search existing
    result = _run_lark(
        ["task", "+tasklist-search", "--query", _TASKLIST_NAME, "--page-all"],
        timeout=15,
    )
    if result.get("ok"):
        items = result.get("data", {}).get("items", [])
        for item in items:
            if item.get("name") == _TASKLIST_NAME:
                _TASKLIST_GUID = item.get("guid", "")
                print_info(f"使用已有任务列表: {_TASKLIST_NAME} ({_TASKLIST_GUID})")
                return _TASKLIST_GUID

    # Create new
    result = _run_lark(
        ["task", "+tasklist-create", "--name", _TASKLIST_NAME],
        timeout=15,
    )
    if result.get("ok"):
        _TASKLIST_GUID = result.get("data", {}).get("guid", "")
        print_ok(f"创建任务列表: {_TASKLIST_NAME} ({_TASKLIST_GUID})")
        return _TASKLIST_GUID

    print_err("无法创建任务列表")
    return None


def create_task(
    summary: str,
    description: str = "",
    due_at: Optional[str] = None,
    assignee: Optional[str] = None,
    tasklist_id: Optional[str] = None,
) -> dict:
    """
    Create a Lark task with assignee set to current user by default.

    Args:
        summary: Task title
        description: Task description
        due_at: Due date (ISO 8601 or date:YYYY-MM-DD or relative:+2d)
        assignee: open_id of assignee (default: current user)
        tasklist_id: Tasklist guid (default: auto-create/get NKU-InFollows 待办)

    Returns:
        {"ok": True, "guid": "...", "url": "..."} or {"ok": False, "error": "..."}
    """
    if not assignee:
        assignee = _get_user_open_id()
        if not assignee:
            return {"ok": False, "error": "无法获取当前用户 open_id，请检查飞书登录状态"}

    if not tasklist_id:
        tasklist_id = _get_or_create_tasklist()

    args = [
        "task", "+create",
        "--summary", summary,
        "--assignee", assignee,
    ]

    if description:
        args += ["--description", description]
    if due_at:
        args += ["--due", due_at]
    if tasklist_id:
        args += ["--tasklist-id", tasklist_id]

    result = _run_lark(args, timeout=15)
    if result.get("ok"):
        data = result.get("data", {})
        guid = data.get("guid", "")
        url = data.get("url", "")
        print_ok(f"创建任务: {summary} ({guid})")
        return {"ok": True, "guid": guid, "url": url}
    else:
        print_err(f"创建任务失败: {summary}")
        return {"ok": False, "error": result.get("error", "unknown")}


# ─── Message Fetching ──────────────────────────────────────────────

def fetch_messages(days: int = 7, page_limit: int = 20, page_size: int = 50) -> dict:
    """
    Fetch recent messages from all chats via lark-cli.
    Uses lark-cli im +messages-search with time range.

    Args:
        days: number of days to look back
        page_limit: max pages to fetch (each page = page_size messages, max 40)
        page_size: messages per page (1-50)
    """
    now = datetime.now(CST)
    start = now - timedelta(days=days)
    start_str = start.strftime("%Y-%m-%dT00:00:00+08:00")
    end_str = now.strftime("%Y-%m-%dT23:59:59+08:00")

    print_info(f"获取最近 {days} 天的消息 ({start_str} ~ {end_str})...")
    print_info(f"最多拉取 {page_limit} 页，每页 {page_size} 条")

    args = [
        "im", "+messages-search",
        "--start", start_str,
        "--end", end_str,
        "--page-size", str(page_size),
    ]
    if page_limit > 1:
        args.extend(["--page-all", "--page-limit", str(page_limit)])

    result = _run_lark(args, timeout=60)

    if not result.get("ok"):
        print_err("获取消息失败")
        return {}

    messages = result.get("data", {}).get("messages", [])
    has_more = result.get("data", {}).get("has_more", False)
    total = result.get("data", {}).get("total", len(messages))

    print_ok(f"获取到 {len(messages)} 条消息 (has_more={has_more}, total={total})")
    if has_more:
        print_info("提示: 消息可能未完全拉取，可增加 --page-limit")

    return result.get("data", {})


def save_messages_raw(messages_data: dict, filepath: Optional[Path] = None) -> Path:
    """Save raw messages data for later analysis."""
    if filepath is None:
        filepath = TEMP_DIR / "lark_messages_raw.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "fetched_at": datetime.now(CST).isoformat(),
        "message_count": len(messages_data.get("messages", [])),
        "has_more": messages_data.get("has_more", False),
        "messages": messages_data.get("messages", []),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print_ok(f"原始消息数据已保存: {filepath}")
    return filepath


# ─── Save Analysis Results ─────────────────────────────────────────

def save_analysis(analysis_data: dict, filepath: Path = LARK_MESSAGES_FILE) -> Path:
    """
    Save Claude's message analysis results (potential tasks extracted from messages).

    Expected analysis_data format:
    {
        "potential_tasks": [
            {
                "title": "...",
                "description": "...",
                "priority": "high|medium|low",
                "source_chat": "...",
                "source_message_summary": "...",
                "deadline": "..." (optional)
            }
        ],
        "summary": "..." (overall analysis summary)
    }
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "saved_at": datetime.now(CST).isoformat(),
        **analysis_data,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    task_count = len(analysis_data.get("potential_tasks", []))
    print_ok(f"消息分析结果已保存: {filepath} ({task_count} 个潜在任务)")
    return filepath


# ─── Quick Check ───────────────────────────────────────────────────

def quick_check() -> dict:
    """Quick status check: auth + task count + message count."""
    status = {
        "authenticated": False,
        "user_name": "",
        "unfinished_task_count": 0,
        "message_count_7d": 0,
    }

    # Auth check
    auth = _run_lark(["auth", "status"], add_format=False)
    status["authenticated"] = _auth_result_ok(auth)
    if status["authenticated"]:
        user = auth.get("identities", {}).get("user", {})
        status["user_name"] = user.get("userName", "")

    if not status["authenticated"]:
        return status

    # Task count
    tasks = fetch_tasks(include_completed=False, page_all=True)
    status["unfinished_task_count"] = len(tasks.get("items", []))

    # Message count (just count, sample only)
    messages = fetch_messages(days=7, page_limit=1, page_size=5)
    status["message_count_7d"] = len(messages.get("messages", []))

    return status


# ─── CLI ───────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Lark/Feishu helper for nku-infollows-skill")
    sub = parser.add_subparsers(dest="command", help="Command")

    # auth
    sub.add_parser("auth", help="Check lark-cli auth status")

    # fetch-tasks
    p_tasks = sub.add_parser("fetch-tasks", help="Fetch tasks and save to JSON")
    p_tasks.add_argument("--include-completed", action="store_true",
                         help="Include completed tasks")
    p_tasks.add_argument("--output", type=Path, default=None,
                         help="Output file path")

    # fetch-messages
    p_msgs = sub.add_parser("fetch-messages", help="Fetch recent messages")
    p_msgs.add_argument("--days", type=int, default=7,
                        help="Days to look back (default: 7)")
    p_msgs.add_argument("--page-limit", type=int, default=20,
                        help="Max pages (default: 20, max: 40)")
    p_msgs.add_argument("--output", type=Path, default=None,
                        help="Output file path for raw messages")

    # save-tasks (from pre-fetched JSON)
    p_st = sub.add_parser("save-tasks", help="Save task data from JSON file")
    p_st.add_argument("json_file", type=Path, help="JSON file with task data")
    p_st.add_argument("--output", type=Path, default=None,
                      help="Output file path")

    # save-analysis (from Claude's analysis)
    p_sa = sub.add_parser("save-analysis", help="Save message analysis from JSON file")
    p_sa.add_argument("json_file", type=Path, help="JSON file with analysis data")
    p_sa.add_argument("--output", type=Path, default=None,
                      help="Output file path")

    # create-tasks (batch create from analysis JSON)
    p_ct = sub.add_parser("create-tasks", help="Batch create tasks from analysis JSON")
    p_ct.add_argument("json_file", type=Path, help="JSON file with potential_tasks array")
    p_ct.add_argument("--assignee", type=str, default=None,
                      help="Assignee open_id (default: current user)")
    p_ct.add_argument("--tasklist-id", type=str, default=None,
                      help="Tasklist guid (default: auto NKU-InFollows 待办)")

    # check (quick status)
    sub.add_parser("check", help="Quick status check")

    args = parser.parse_args()

    if args.command == "auth":
        print_header("飞书登录状态")
        result = check_auth()
        return 0 if _auth_result_ok(result) else 1

    elif args.command == "fetch-tasks":
        print_header("获取飞书任务")
        data = fetch_tasks(include_completed=getattr(args, "include_completed", False))
        if not data:
            return 1
        output_path = getattr(args, "output", None) or LARK_TASKS_FILE
        save_tasks(data, filepath=Path(output_path))
        return 0

    elif args.command == "fetch-messages":
        print_header("获取飞书消息")
        data = fetch_messages(
            days=args.days,
            page_limit=args.page_limit,
        )
        if not data:
            return 1
        output_path = getattr(args, "output", None)
        save_messages_raw(data, filepath=Path(output_path) if output_path else None)
        return 0

    elif args.command == "save-tasks":
        print_header("保存任务数据")
        with open(args.json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        output_path = getattr(args, "output", None) or LARK_TASKS_FILE
        save_tasks(data, filepath=Path(output_path))
        return 0

    elif args.command == "save-analysis":
        print_header("保存消息分析")
        with open(args.json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        output_path = getattr(args, "output", None) or LARK_MESSAGES_FILE
        save_analysis(data, filepath=Path(output_path))
        return 0

    elif args.command == "check":
        print_header("飞书快速检查")
        status = quick_check()
        print(f"  登录状态: {'✅ 已登录' if status['authenticated'] else '❌ 未登录'}")
        if status["authenticated"]:
            print(f"  用户名: {status['user_name']}")
            print(f"  未完成任务: {status['unfinished_task_count']} 个")
            print(f"  近7天消息 (样本): {status['message_count_7d']} 条")
        return 0

    elif args.command == "create-tasks":
        print_header("批量创建飞书任务")
        with open(args.json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        potential = data.get("potential_tasks", [])
        if not potential:
            print_info("没有待创建的任务")
            return 0

        created = 0
        failed = 0
        for task in potential:
            result = create_task(
                summary=task.get("title", "未命名任务"),
                description=task.get("description", ""),
                due_at=task.get("deadline") or task.get("due_at"),
                assignee=getattr(args, "assignee", None) or None,
                tasklist_id=getattr(args, "tasklist_id", None) or None,
            )
            if result.get("ok"):
                created += 1
            else:
                failed += 1

        print(f"\n  创建完成: {created} 成功, {failed} 失败")
        return 0 if failed == 0 else 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
