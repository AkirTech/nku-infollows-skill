# nku-infollows-skill

Fetches WeChat subscription articles via `wechat-download-api`, integrates Feishu/Lark tasks and messages, generates AI keyword tags and recommendations, and creates an HTML aggregation page. The core value is **recommendation** — intelligently identifying and highlighting the most valuable content across both platforms.

## Prerequisites

- Python 3.8+ available for running utility scripts
- Backend source at `src/backend/wechat-download-api/` (with `start.bat` / `start.sh`)
- Node.js + npm (for lark-cli — Feishu/Lark integration)
- lark-cli installed (`npm install -g @larksuite/cli`) and logged in

## Mode Selection

**When the user invokes `/nku-infollows`, FIRST ask them which mode they want:**

> 请选择运行模式:
> 1. **全部** (默认) — 微信公众号文章 + 飞书任务
> 2. **仅微信公众号** — 只处理微信公众号文章
> 3. **仅飞书** — 只处理飞书任务和消息

Default to **全部 (All)** if the user doesn't specify.

Save the mode choice to `src/main/scripts/temp/.mode.json`:
```json
{"mode": "all"}
```
Valid values: `"all"`, `"wechat"`, `"lark"`.

## Scripts

All utility scripts are in `src/main/scripts/` (relative to repo root):

| Script | Purpose |
|--------|---------|
| `config.py` | Shared configuration (BACKEND_URL, TEMP_DIR paths, unicode output) |
| `check_backend.py` | Health/auth check with **auto-start** support (`--start` flag) |
| `trigger_poll.py` | Triggers immediate article poll on backend (timeout is non-fatal) |
| `generate_html.py` | Creates standalone `recommendations.html` with articles + tasks + dark/light theme |
| `cleanup.py` | Deletes all generated files in TEMP_DIR |
| `orchestrator.py` | Single entry point for the complete single-mode WeChat workflow |
| `lark_helper.py` | Feishu/Lark task fetching, message fetching, and data parsing |

---

## Mode: 全部 (All) — Parallel WeChat + Feishu/Lark

When mode is `all`, run the **WeChat thread** and **Feishu/Lark thread** concurrently.
Both threads produce their respective data files. Then the **main thread** merges results,
asks about task creation, and generates the HTML.

### WeChat Thread

Follow the **Single Mode — REST API Path** workflow described below (Steps 1–5 for keyword generation).
Save `articles_with_keywords.json` when done.

### Feishu/Lark Thread

#### Step L1: Check Feishu/Lark Login

Run `lark-cli auth status` (or `python src/main/scripts/lark_helper.py auth`) to verify login.

If not logged in, guide the user through the install and login process:
1. Install: `npm install -g @larksuite/cli`
2. Configure: `lark-cli config init --new`
3. Login: `lark-cli auth login --recommend` (user must complete in browser)
4. Verify: `lark-cli auth status`

#### Step L2: Fetch Unfinished Tasks

```
python src/main/scripts/lark_helper.py fetch-tasks
```

This runs `lark-cli task +get-my-tasks --complete=false --page-all` and saves to `src/main/scripts/temp/lark_tasks.json`.

The output format:
```json
{
  "unfinished_tasks": [
    {
      "id": "guid",
      "title": "任务标题",
      "description": "描述",
      "due_at": "2026-07-19T08:00:00+08:00",
      "created_at": "2026-07-18T14:44:48+08:00",
      "completed": false,
      "url": "https://applink.feishu.cn/client/todo/detail?guid=...",
      "source": "lark"
    }
  ],
  "completed_tasks": [],
  "total": 3,
  "fetched_at": "2026-07-18T15:00:00+08:00"
}
```

#### Step L3: Fetch Recent Messages (7 days)

```
python src/main/scripts/lark_helper.py fetch-messages --days 7 --page-limit 20
```

This runs `lark-cli im +messages-search` with a 7-day time range and saves raw messages to
`src/main/scripts/temp/lark_messages_raw.json`.

> **Note:** Message volume can be very large. The `--page-limit` controls how many pages to fetch
> (max 40, default 20, each page up to 50 messages). Adjust based on the user's chat volume.
> For very active users, consider increasing `--page-limit` or narrowing the search with `--chat-id`.

#### Step L4: Analyze Messages for Potential Tasks

Read `src/main/scripts/temp/lark_messages_raw.json` and analyze the messages:

1. **Filter out noise**: Skip system messages, reactions, short replies, and purely social chat.
2. **Identify actionable messages**: Look for:
   - Deadlines or time-bound requests (due dates, deadlines, "by Friday")
   - Assignment/notification messages from teachers, admins, or group leaders
   - Action items: "请...", "需要...", "务必...", "提交...", "填写...", "完成..."
   - Event announcements with registration/signup requirements
3. **Evaluate priority**:
   - **High (high)**: Urgent deadlines within 48 hours, mandatory actions, official notices
   - **Medium (medium)**: Upcoming deadlines, course assignments, general tasks
   - **Low (low)**: Informational notices, optional activities, FYI messages
4. **Extract structured data** for each potential task:
   - `title`: Concise task summary
   - `description`: What needs to be done
   - `priority`: "high" | "medium" | "low"
   - `source_chat`: Which chat/group the message came from
   - `source_message_summary`: Brief summary of the original message
   - `deadline`: Extracted deadline (ISO 8601 or null)

Save the analysis to `src/main/scripts/temp/lark_messages_analysis.json` using:
```
python src/main/scripts/lark_helper.py save-analysis <path_to_analysis_json>
```

Or use the `Write` tool directly. The format should be:
```json
{
  "potential_tasks": [
    {
      "title": "填写天津市选民登记表",
      "description": "7月19日12:00前完成，通过金山文档链接填写",
      "priority": "high",
      "source_chat": "【分流后计密网】25级本科安全提醒群",
      "source_message_summary": "通知要求全体同学在7月19日12:00前完成选民登记表填写",
      "deadline": "2026-07-19T12:00:00+08:00"
    }
  ],
  "summary": "近7天消息分析：共扫描XX条消息，发现N个潜在待办事项。..."
}
```

### Main Thread (Merge & Create Tasks)

After BOTH threads complete:

#### Step M1: Present Detected Potential Tasks

Show the user the potential tasks detected from messages:
> 📋 **检测到以下潜在任务（未在飞书任务列表中）：**
> 1. 🔴 **[高优先级]** 填写天津市选民登记表 — 截止 7/19 12:00
>    来源: 【分流后计密网】安全提醒群
> 2. 🟡 **[中优先级]** 提交计算机科学前沿技术作业
>    来源: 0016课程群
>
> 是否需要将这些任务添加到飞书任务列表？

#### Step M2: Create Tasks in Feishu/Lark (If User Confirms)

If the user says yes, ask which tasks they want to create (they can choose specific ones).

Use the batch creation command which automatically:
- Sets the **assignee** to the current lark-cli user (so tasks appear prominently in Feishu app)
- Creates/uses the **"NKU-InFollows 待办"** task list for organization

```bash
python src/main/scripts/lark_helper.py create-tasks src/main/scripts/temp/lark_messages_analysis.json
```

This reads `potential_tasks` from the analysis JSON and creates each one with proper assignee and tasklist.

> If you need to create tasks individually (e.g., user only selected specific ones), use:
> ```bash
> lark-cli task +create --summary "任务标题" --due "2026-07-19T12:00:00+08:00" --description "任务描述" --assignee "ou_xxx" --tasklist-id "xxx"
> ```
> The `--assignee` flag is **required** for tasks to show in the user's "分配给我的" view in the Feishu app.

After creating tasks, re-fetch the task list to update `lark_tasks.json`:
```
python src/main/scripts/lark_helper.py fetch-tasks
```

#### Step M3: Generate Combined HTML

```
python src/main/scripts/generate_html.py
```

This reads all available data files and creates a tabbed page:
- **📰 文章推荐** tab: Recommended articles grid + all articles accordion (from `articles_with_keywords.json`)
- **✅ 飞书任务** tab: Unfinished tasks + potential tasks (from `lark_tasks.json` + `lark_messages_analysis.json`)

The HTML supports:
- Dark & Light themes with auto-detection + manual toggle
- Article search, filter by author/date, sort
- Star/bookmark articles (persisted in localStorage)
- Task filtering by priority
- Responsive layout

#### Step M4: Open in Browser

```
python -c "import os; os.startfile('src/main/scripts/temp/recommendations.html')"
```
(On Windows use `os.startfile`, on macOS use `open`, on Linux use `xdg-open`)

---

## Mode: 仅微信公众号 (WeChat Only)

Follow the **Single Mode — REST API Path** workflow below exactly as described.
Skip all Feishu/Lark steps.

---

## Mode: 仅飞书 (Feishu/Lark Only)

Run only the Feishu/Lark thread (Steps L1–L4 above) followed by the Main Thread.
Skip all WeChat steps. The HTML will show only the task tab.

---

## Single Mode — REST API Path (WeChat)

This is the primary path — it uses Python's built-in `urllib` to call the backend REST API. No extra configuration needed.

### Step 1: Health Check (with Auto-Start)

Run with `--start` to automatically launch the backend if it's not running:
```
python src/main/scripts/check_backend.py --start
```

**What happens:**
1. Check if backend responds on `http://localhost:5000`
2. **If not running**: automatically launches the platform-appropriate startup script:
   - Windows → `start.bat` (opens new console window, runs independently)
   - Linux/macOS → `start.sh` (venv + deps + `python app.py`, backgrounded)
3. Polls the health endpoint every 2s for up to 30s until backend responds
4. Once reachable, verifies WeChat authentication status
5. If not authenticated, directs user to `http://localhost:5000/login.html`

**Flags:**
- `--start` — auto-start backend if not running (RECOMMENDED for normal use)
- `--no-start` — only check status, never attempt startup (use when user wants manual control)
- `--wait N` — max seconds to wait for startup (default 120)

**Exit codes:** 0 = healthy & authenticated, 1 = problem detected.

### Step 2: Check Subscriptions

Use Python to call the REST API:
```
python -c "import urllib.request, json; r = urllib.request.urlopen('http://localhost:5000/api/rss/subscriptions'); print(json.dumps(json.loads(r.read())['data'], indent=2, ensure_ascii=False))"
```
> **Note:** The `WebFetch` tool does NOT support localhost URLs. Always use `python -c "import urllib.request..."` or equivalent for local API calls.

- If the `data` array is empty: guide user to subscribe first at `http://localhost:5000/rss.html`
- Print subscription count and names for the user.

### Step 3: Trigger Poll (Optional but Recommended)

Run `src/main/scripts/trigger_poll.py` to fetch the latest articles immediately:
```
python src/main/scripts/trigger_poll.py
```
> **If the poll times out:** This is **non-fatal**. The backend may already have articles in the database from previous polls. Proceed to Step 4. The script exits 0 on timeout (warning only).

### Step 4: Fetch Articles via REST API

Call the feed endpoint with cursor pagination:
```
python -c "
import urllib.request, json
all_articles = []
next_since = 0
while True:
    url = f'http://localhost:5000/api/feed/articles.json?since={next_since}&limit=200'
    data = json.loads(urllib.request.urlopen(url).read())
    articles = data.get('articles', [])
    if not articles:
        break
    all_articles.extend(articles)
    next_since = data.get('next_since', 0)
    print(f'Fetched {len(articles)} (total: {len(all_articles)})')
print(f'Done: {len(all_articles)} articles')
# Save for processing
with open('src/main/scripts/temp/raw_articles.json', 'w', encoding='utf-8') as f:
    json.dump(all_articles, f, ensure_ascii=False, indent=2)
"
```

Collect only these fields per article: `id`, `title`, `link`, `author`, `publish_time`, `cover`.

**Rate limiting note:** `/api/feed/articles.json` reads from SQLite — it does NOT hit WeChat API rate limits. Safe to call without throttling.

### Step 5: Generate Keywords and Recommendations

For EACH article in the collected list, generate:

1. **`keywords`** — 2-5 pipe-separated Chinese keyword phrases based on comprehension of the title and author.
   - Extract core topics from the title
   - Consider the source/author for context
   - Format: `"关键词1 | 关键词2 | 关键词3"`
   - Example: title `"南开大学发布暑假放假通知！"`, author `"南开大学"` → keywords: `"假期 | 重要通知 | 教务"`

2. **`recommended`** — `true` or `false` based on value assessment:
   - **Recommend** articles that are: official announcements from authoritative sources, time-sensitive (deadlines, policy changes, event notices), or highly informative
   - **Skip** articles that are: routine updates, promotional content, duplicate/reposted content

Save the result as `articles_with_keywords.json` in `src/main/scripts/temp/`:
```json
[
  {
    "id": 5,
    "title": "南开大学发布暑假放假通知！",
    "link": "https://mp.weixin.qq.com/s/XxwJo1ueMSvOaTXOs-DHdg",
    "author": "南开大学",
    "keywords": "假期 | 重要通知 | 教务",
    "publish_time": 1720963200,
    "recommended": true,
    "cover": "http://localhost:5000/api/image?url=..."
  }
]
```
Use `Write` tool to save the file to the absolute path of `src/main/scripts/temp/articles_with_keywords.json`.

Schema fields: `id` (int), `title` (string), `link` (string), `author` (string), `keywords` (string, pipe-separated), `publish_time` (int, unix timestamp), `recommended` (bool), `cover` (string, proxied image URL).

> **⚠️ JSON Safety:** Avoid using curly/smart quotes (`""`, `''`) in titles — they can break JSON parsing. The `generate_html.py` script will automatically sanitize them by converting to corner brackets (`「」`), but it's best practice to use corner brackets in the JSON source as well.

### Step 6: Generate HTML

Run the HTML generator:
```
python src/main/scripts/generate_html.py
```
This reads `articles_with_keywords.json` and creates `src/main/scripts/temp/recommendations.html`.

The generated HTML supports:
- **Dark & Light themes** with auto-detection (`prefers-color-scheme`) and manual toggle (☀️/☽ button in header)
- Full-text search across titles, keywords, and authors
- Filter by author, date range
- Sort by date, author, recommendation status
- Star/bookmark articles for custom recommendations (persisted in localStorage)
- Accordion grouping by author with auto-expand for small groups

### Step 7: Open in Browser

Open the generated HTML file in the default browser:
```
python -c "import os; os.startfile('src/main/scripts/temp/recommendations.html')"
```
(On Windows use `os.startfile`, on macOS use `open`, on Linux use `xdg-open`)

---

## Single Mode — MCP Path (If Available)

Use this path when the backend MCP server is configured (`ENABLE_MCP=1` and `MCP_TOKEN` set in backend `.env`).

MCP tools are called directly by Claude — no HTTP scripts needed for data fetching. When MCP tools are available, use:
- `list_subscriptions` instead of REST API in Step 2
- `search_accounts` / `subscribe_account` for adding new subscriptions
- `get_recent_articles` instead of REST API in Step 4

Steps 5-7 are identical to the REST API path.

---

## Loop Mode

Run the process every 1 hour using Claude Code's loop mechanism:
```
/loop 1h /nku-infollows
```

**Before each iteration:**
1. Run `python src/main/scripts/cleanup.py` to clear old generated files.
2. Re-check backend health (Step 1).
3. Re-check lark-cli auth status.

**Important:** The `cleanup.py` call before each iteration ensures storage stays bounded and each recommendation batch is independent.

---

## Clear Mode

When invoked with "clear" or "clean":
1. Run `python src/main/scripts/cleanup.py`
2. Report what was removed to the user

---

## Rate Limiting

| Endpoint | Limit | Notes |
|----------|-------|-------|
| `/api/feed/articles.json` | No WeChat API limit | Reads SQLite, safe for bulk fetch |
| `/api/feed/article/{id}.md` | 3s interval | Hits WeChat for full content |
| `/api/public/*` | 10/min global | Hits WeChat API |
| `/api/rss/poll` | Follows internal limits | Backend manages its own throttling |
| `lark-cli task +get-my-tasks` | Lark API rate limit | Up to 100 requests/min |
| `lark-cli im +messages-search` | Lark API rate limit | Up to 100 requests/min |

The skill primarily uses `/api/feed/articles.json` (SQLite-backed) which avoids rate limits entirely.

## Error Handling

| Scenario | Action |
|----------|--------|
| Backend not running | Auto-start via `check_backend.py --start` (launches `start.bat`/`start.sh`) |
| Backend fails to start | Show manual start command: `start.bat` (Win) or `bash start.sh` (Linux) |
| Not authenticated | Tell user to visit `http://localhost:5000/login.html` and scan QR |
| No subscriptions | Guide user to search & subscribe accounts at `http://localhost:5000/rss.html` |
| Empty article list | Suggest triggering a poll, then retry |
| Poll timeout | Non-fatal — proceed to fetch articles (DB may already have them) |
| JSON parse error in HTML gen | Check article titles for curly quotes (`""`) — sanitize or re-save JSON |
| Browser won't open | Report the file path so user can open manually |
| lark-cli not installed | Guide user: `npm install -g @larksuite/cli` |
| lark-cli not logged in | Guide user: `lark-cli auth login --recommend` |
| lark-cli auth expired | Re-login: `lark-cli auth login --recommend` |
| Message search too large | Increase `--page-limit` or narrow with `--chat-id` |
| No Lark tasks found | Show empty task state in HTML; this is normal |

## Practical Notes

1. **Localhost API calls** — Claude's `WebFetch` tool cannot access `localhost`. Always use `python -c "import urllib.request; ..."` for calling the backend API.
2. **Poll timeout** — `trigger_poll.py` exits 0 on timeout (it's a warning, not an error). The database may already contain articles from previous polls — proceed to fetch them.
3. **JSON encoding** — Chinese curly/smart quotes (`""`, `''`) in article titles can break JSON when writing with the `Write` tool. Use corner brackets `「」` as alternatives, or rely on `generate_html.py`'s built-in sanitization.
4. **Unicode output** — All scripts now configure `sys.stdout.reconfigure(encoding="utf-8")` for clean Chinese output on Windows.
5. **Parallel execution** — In `all` mode, the WeChat and Feishu/Lark threads are independent. Run them concurrently for faster completion.
6. **Task creation confirmation** — Always ask the user before creating Lark tasks. The AI's analysis may not perfectly capture the user's intent.

## Reference

- Backend OpenAPI spec: `src/refs/openapi.json`
- Backend README: `src/backend/wechat-download-api/README.md`
- MCP server implementation: `src/backend/wechat-download-api/mcp_server/`
- Database schema: `articles` table in `src/backend/wechat-download-api/data/rss.db`
- Lark CLI docs: https://open.larkoffice.com/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu.md
