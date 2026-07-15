# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About

A Claude Code skill for WeChat subscription news tracking and AI-powered recommendation.
The core value is **recommendation** — intelligently identifying the most valuable content from your subscriptions.

- Skill entry point: `src/main/skill.md` (the full workflow definition)
- Skill registration: `.claude/skills/nku-infollows/skill.md` → points to `src/main/skill.md`
- Automation scripts: `src/main/scripts/`

## Architecture

```
User invokes /nku-infollows
        │
        ▼
.claude/skills/nku-infollows/skill.md   ← Claude Code discovers this
        │
        ▼
src/main/skill.md                       ← Full workflow instructions
        │
        ├── check_backend.py --start    ← Auto-starts backend (direct uvicorn, fallback to start.bat/start.sh)
        ├── MCP tools (preferred) or REST API (fallback)
        ├── Claude generates keywords + recommendations
        ├── generate_html.py            ← Creates standalone recommendation HTML
        └── Open in browser
```

## Backend

- **wechat-download-api** — Python 3.8+ FastAPI server at `src/backend/wechat-download-api/` (git submodule)
- Remote: `git@github.com:tmwgsicp/wechat-download-api.git`
- Provides REST API on `http://localhost:5000` and optional MCP server at `/mcp`
- Start scripts: `start.bat` (Windows), `start.sh` (Linux/macOS)
- Auto-start via: `python src/main/scripts/check_backend.py --start`

### MCP Tools (when `ENABLE_MCP=1` + `MCP_TOKEN` set)

| Tool | Purpose |
|------|---------|
| `list_subscriptions` | List subscribed accounts with article counts |
| `search_accounts(query)` | Search WeChat accounts by name |
| `get_recent_articles(since, limit, source_id)` | Cursor-paginated article metadata (from SQLite) |
| `read_article(article_id)` | Full article as Markdown with YAML frontmatter |
| `subscribe_account(fakeid)` | Subscribe to an account |
| `unsubscribe_account(fakeid)` | Unsubscribe from an account |

## Scripts

All in `src/main/scripts/`:

| Script | Purpose |
|--------|---------|
| `check_backend.py` | Health/auth check + auto-start (`--start` / `--no-start` / `--wait N`) |
| `trigger_poll.py` | Trigger immediate article poll on backend |
| `orchestrator.py` | Full single-mode workflow (health → subs → poll → fetch → instruct Claude) |
| `generate_html.py` | Read `articles_with_keywords.json` → standalone `recommendations.html` |
| `cleanup.py` | Delete all generated files in `temp/` |
| `config.py` | Shared configuration (BACKEND_URL, TEMP_DIR, file paths) |

## Two Modes

- **Single**: `python src/main/scripts/orchestrator.py` — one-shot fetch + recommend
- **Loop**: `/loop 1h /nku-infollows` — hourly with cleanup between runs

## Database Schema (SQLite)

**articles** table: `id | fakeid | aid | title | link | digest | cover | author | content | plain_content | publish_time | fetched_at | source`

**subscriptions** table: `fakeid (PK) | nickname | alias | head_img | category_id | created_at | last_poll`

## References

- Backend API: `src/refs/openapi.json` (OpenAPI 3.1 spec)
- Backend README: `src/backend/wechat-download-api/README.md`
- Database: `src/backend/wechat-download-api/data/rss.db`
- Credentials: `src/backend/wechat-download-api/data/.credentials.json`
- Rate limits: `RATE_LIMIT_GLOBAL=10`, `RATE_LIMIT_ARTICLE_INTERVAL=3s` (in backend `.env`)
