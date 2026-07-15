# nku-infollows-skill

Fetches WeChat subscription articles via `wechat-download-api`, generates AI keyword tags, and creates an HTML recommendation page. The core value is **recommendation** — intelligently identifying and highlighting the most valuable content.

## Prerequisites

- Python 3.8+ available for running utility scripts
- Backend source at `src/backend/wechat-download-api/` (with `start.bat` / `start.sh`)

## Backend Startup

The backend provides platform-native startup scripts that handle venv creation, dependency installation, and service launch:

| Platform | Script | Behavior |
|----------|--------|----------|
| Windows | `src/backend/wechat-download-api/start.bat` | Opens a new console window, runs `python app.py` |
| Linux/macOS | `src/backend/wechat-download-api/start.sh` | Creates venv, installs deps, runs `python app.py` |
| Linux (systemd) | `sudo bash start.sh` | Full deployment with systemd service |

The skill's `check_backend.py` can **automatically launch** these scripts when the backend is not running (see Step 1).

Once the backend starts, visit `http://localhost:5000/login.html` to scan the WeChat QR code and log in. After login, add subscriptions via `http://localhost:5000/rss.html`.

## Scripts

All utility scripts are in `src/main/scripts/` (relative to repo root):

| Script | Purpose |
|--------|---------|
| `config.py` | Shared configuration (BACKEND_URL, TEMP_DIR paths, unicode output) |
| `check_backend.py` | Health/auth check with **auto-start** support (`--start` flag) |
| `trigger_poll.py` | Triggers immediate article poll on backend (timeout is non-fatal) |
| `generate_html.py` | Creates standalone `recommendations.html` with dark/light theme support |
| `cleanup.py` | Deletes all generated files in TEMP_DIR |
| `orchestrator.py` | Single entry point for the complete single-mode workflow |

---

## Single Mode — REST API Path (Primary)

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
- `--wait N` — max seconds to wait for startup (default 30)

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

Collect only these fields per article: `id`, `title`, `link`, `author`, `publish_time`.

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
    "recommended": true
  }
]
```
Use `Write` tool to save the file to the absolute path of `src/main/scripts/temp/articles_with_keywords.json`.

Schema fields: `id` (int), `title` (string), `link` (string), `author` (string), `keywords` (string, pipe-separated), `publish_time` (int, unix timestamp), `recommended` (bool).

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

Run the Single mode process every 1 hour using Claude Code's loop mechanism:
```
/loop 1h /nku-infollows
```

**Before each iteration:**
1. Run `python src/main/scripts/cleanup.py` to clear old generated files.
2. Re-check backend health (Step 1).

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

## Practical Notes

1. **Localhost API calls** — Claude's `WebFetch` tool cannot access `localhost`. Always use `python -c "import urllib.request; ..."` for calling the backend API.
2. **Poll timeout** — `trigger_poll.py` exits 0 on timeout (it's a warning, not an error). The database may already contain articles from previous polls — proceed to fetch them.
3. **JSON encoding** — Chinese curly/smart quotes (`""`, `''`) in article titles can break JSON when writing with the `Write` tool. Use corner brackets `「」` as alternatives, or rely on `generate_html.py`'s built-in sanitization.
4. **Unicode output** — All scripts now configure `sys.stdout.reconfigure(encoding="utf-8")` for clean Chinese output on Windows.

## Reference

- Backend OpenAPI spec: `src/refs/openapi.json`
- Backend README: `src/backend/wechat-download-api/README.md`
- MCP server implementation: `src/backend/wechat-download-api/mcp_server/`
- Database schema: `articles` table in `src/backend/wechat-download-api/data/rss.db`
