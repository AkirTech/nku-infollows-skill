# nku-infollows-skill

A Claude Code skill for intelligent WeChat subscription news tracking and AI-powered recommendation.

## Overview

This skill helps you keep up with the most valuable news from your WeChat subscriptions. It fetches articles via the [wechat-download-api](https://github.com/tmwgsicp/wechat-download-api) backend, generates keywords using AI comprehension, and presents personalized recommendations in a clean, interactive HTML report.

The core philosophy: **not just fetching articles, but recommending** — sorting, filtering, and surfacing only the most valuable content.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Claude Code                                         │
│  /nku-infollows  ────→  src/main/skill.md            │
│                              │                       │
│    MCP tools (preferred) ────┤                       │
│    or REST API (fallback) ───┤                       │
│                              ▼                       │
│    Claude generates keywords + recommendations       │
│                              │                       │
│    generate_html.py ────→ recommendations.html       │
│                              │                       │
│    Open in browser ←─────────┘                       │
└──────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│  wechat-download-api (git submodule)                 │
│  FastAPI + SQLite + MCP server                       │
│  http://localhost:5000                               │
└──────────────────────────────────────────────────────┘
```

## Project Structure

```
├── .claude/skills/nku-infollows/   # Skill registration (Claude Code discovers this)
│   └── skill.md                    #   → points to src/main/skill.md
├── .gitignore
├── .gitmodules                     # Backend submodule config
├── CLAUDE.md                       # Guidance for Claude Code
├── LICENSE
├── README.md
└── src/
    ├── main/
    │   ├── skill.md                # Full skill workflow definition
    │   ├── scripts/                # Automation scripts
    │   │   ├── config.py           #   Shared configuration
    │   │   ├── check_backend.py    #   Health check + auto-start
    │   │   ├── trigger_poll.py     #   Trigger article poll
    │   │   ├── generate_html.py    #   Generate recommendation HTML
    │   │   ├── cleanup.py          #   Clean up generated files
    │   │   ├── orchestrator.py     #   Single-mode workflow runner
    │   │   └── temp/               #   Generated output (gitignored)
    │   └── reference/              #   Reserved for skill references
    ├── refs/
    │   └── openapi.json            # Backend API OpenAPI 3.1 spec
    └── backend/
        └── wechat-download-api/    # Backend server (git submodule)
            ├── app.py              #   FastAPI entry point
            ├── start.bat           #   Windows startup script
            ├── start.sh            #   Linux/macOS startup script
            ├── routes/             #   API route handlers
            ├── utils/              #   Core utilities
            ├── mcp_server/         #   MCP server (6 tools)
            ├── static/             #   Frontend HTML pages
            └── data/               #   SQLite DB + credentials
```

## Modes

### Single Mode

Run once to fetch and recommend articles. Trigger with `/nku-infollows` in Claude Code, or:

```bash
python src/main/scripts/orchestrator.py
```

### Loop Mode

Run automatically every hour:

```bash
/loop 1h /nku-infollows
```

### Clear

Clean up generated files:

```bash
python src/main/scripts/cleanup.py
```

## Getting Started

### 1. Clone with submodule

```bash
git clone --recurse-submodules <this-repo>
cd nku-infollows-skill
```

### 2. Start the backend

The skill auto-starts the backend, but you can also do it manually:

**Windows:**
```bash
src\backend\wechat-download-api\start.bat
```

**Linux/macOS:**
```bash
bash src/backend/wechat-download-api/start.sh
```

### 3. Log in to WeChat

Open `http://localhost:5000/login.html` and scan the QR code with your WeChat app.

### 4. Add subscriptions

Go to `http://localhost:5000/rss.html` to search and subscribe to WeChat official accounts.

### 5. Run the skill

In Claude Code:
```
/nku-infollows
```

Or manually:
```bash
# Auto-start backend + fetch articles + generate recommendations
python src/main/scripts/orchestrator.py

# Step by step
python src/main/scripts/check_backend.py --start
python src/main/scripts/trigger_poll.py
python src/main/scripts/generate_html.py
```

## MCP Support (Optional)

Enable the backend MCP server for direct tool access from Claude:

1. In the backend `.env`, set:
   ```
   ENABLE_MCP=1
   MCP_TOKEN=your-secret-token
   ```
2. Restart the backend
3. Claude Code can now call `list_subscriptions`, `get_recent_articles`, `read_article`, and other MCP tools directly — no HTTP scripts needed for data fetching

The skill automatically prefers MCP when available, falling back to REST API calls otherwise.

## Article Data Schema

```json
{
  "id": 5,
  "title": "南开大学发布暑假放假通知！",
  "link": "https://mp.weixin.qq.com/s/XxwJo1ueMSvOaTXOs-DHdg",
  "author": "南开大学",
  "keywords": "假期 | 重要通知 | 教务",
  "publish_time": 1720963200,
  "recommended": true
}
```

Keywords are AI-generated based on title and author comprehension. Recommendations are based on content value, recency, and user preferences.

## References

- Backend API spec: `src/refs/openapi.json`
- Backend README: `src/backend/wechat-download-api/README.md`
- Backend repository: [wechat-download-api](https://github.com/tmwgsicp/wechat-download-api)

## License

MIT. See `LICENSE` for details.
The backend (`src/backend/wechat-download-api/`) is licensed under AGPL-3.0-only.
