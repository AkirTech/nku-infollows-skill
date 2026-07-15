# nku-infollows-skill

A Claude Code skill for intelligent WeChat subscription news tracking and AI-powered recommendation.

## Overview

This skill helps you keep up with the most valuable news from your WeChat subscriptions. It fetches articles via the [wechat-download-api](https://github.com/nku/infollows) backend, extracts key information, generates keywords using AI comprehension, and presents personalized recommendations in a clean HTML report.

The core of this skill is not just fetching articles — it emphasizes **"Recommend"** more: sorting, filtering, and surfacing only the most relevant items based on content understanding.

## Architecture

- **Backend**: `wechat-download-api` (Python 3.8+ with FastAPI) — handles WeChat authentication, article fetching, and data storage
- **Database**: SQLite (`src/backend/wechat-download-api/data/rss.db`) with `articles` and `subscriptions` tables
- **Skill layer**: Claude Code orchestrates the workflow — querying the backend, analyzing articles, generating recommendations

## Modes

### Single Mode

Runs once to fetch and recommend articles:

1. Verify the backend server is running
2. Check that subscriptions are configured
3. Fetch latest articles from the backend (respects rate limits)
4. Export articles as JSON with AI-generated keywords:
   ```json
   {
     "id": 5,
     "title": "南开大学发布暑假放假通知！",
     "link": "https://mp.weixin.qq.com/s/XxwJo1ueMSvOaTXOs-DHdg",
     "author": "南开大学",
     "keywords": "假期 | 重要通知"
   }
   ```
5. Generate a standalone HTML page to display the JSON data
6. Sort, filter, and identify the most valuable articles
7. Render recommendations in HTML and open in the default browser

### Loop Mode

Triggers the Single mode process every 1 hour on a recurring basis. Previous recommendation data is cleared between runs to save storage.

### Clear

Cleans up generated JSON and HTML files.

## Project Structure

```
├── src/
│   ├── main/                     # Skill entry point
│   └── backend/
│       └── wechat-download-api/  # Backend server (git submodule)
│           ├── routes/           # API route handlers
│           ├── utils/            # Core utilities (fetcher, auth, RSS, etc.)
│           ├── mcp_server/       # MCP server integration
│           ├── static/           # Frontend HTML pages
│           └── data/             # SQLite database and credentials
├── refs/
│   └── openapi.json             # Backend API reference
└── CLAUDE.md                    # Skill instructions for Claude Code
```

## Prerequisites

- Python 3.8+
- A WeChat account (for authentication)
- Claude Code with the skill installed

## Getting Started

1. Set up the backend:
   ```bash
   cd src/backend/wechat-download-api
   pip install -r requirements.txt
   cp env.example .env    # Configure your environment
   ```

2. Start the backend server:
   ```bash
   python app.py
   ```

3. Log in with your WeChat account and add subscriptions via the admin dashboard.

4. Invoke the skill in Claude Code:
   ```
   /nku-infollows
   ```

## References

- Backend API documentation: `refs/openapi.json`
- Backend README: `src/backend/wechat-download-api/README.md`

## License

See `src/backend/wechat-download-api/LICENSE` for backend license information.
