"""
Generate a standalone HTML page from articles JSON and Lark/Feishu task data.

Reads articles_with_keywords.json, lark_tasks.json, and lark_messages_analysis.json,
then produces recommendations.html with tabbed WeChat articles + Feishu/Lark tasks.

Features:
- Dark/light theme with auto-detection + manual toggle
- Tabbed interface: "文章推荐" + "飞书任务"
- Smart article cards with keyword tags, star recommendations, lazy-loaded covers
- Task cards with priority badges, due dates, source context
- Search, filter, sort for articles; filter for tasks
- Accordion grouping by author for articles
- Graceful degradation: works with only articles or only tasks
"""

import sys
import json
import html as html_mod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Ensure clean Unicode output on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import (
    ARTICLES_FILE,
    LARK_TASKS_FILE,
    LARK_MESSAGES_FILE,
    MODE_FILE,
    RECOMMENDATIONS_HTML,
    TEMP_DIR,
    print_header,
    print_ok,
    print_err,
    print_info,
)

# Timezone for China (UTC+8)
CST = timezone(timedelta(hours=8))

# Keyword tag color palette
KEYWORD_COLORS = [
    ("#f3e5f5", "#6A2C70"),  # Nankai purple
    ("#e8f5e9", "#2e7d32"),  # green
    ("#e3f2fd", "#1565c0"),  # blue
    ("#fef7e8", "#B8860B"),  # Nankai gold
    ("#fce4ec", "#c62828"),  # red/pink
    ("#e0f7fa", "#00695c"),  # teal
    ("#fff3e0", "#e65100"),  # orange
    ("#f1f8e9", "#558b2f"),  # light green
]

# Priority colors
PRIORITY_COLORS = {
    "high":   ("#fce4ec", "#c62828", "🔴 高"),
    "medium": ("#fff3e0", "#e65100", "🟡 中"),
    "low":    ("#e8f5e9", "#2e7d32", "🟢 低"),
}


# ─── Sanitization ─────────────────────────────────────────────────

def sanitize_text(s: str) -> str:
    """Replace smart/curly quotes with corner brackets."""
    if not isinstance(s, str):
        return s
    return (
        s.replace("“", "「")  # " → 「
         .replace("”", "」")  # " → 」
         .replace("‘", "『")  # ' → 『
         .replace("’", "』")  # ' → 』
         .replace("＂", "」")  # ＂ (fullwidth) → 」
    )


def sanitize_articles(articles: list[dict]) -> list[dict]:
    """Sanitize text fields in all articles to prevent JSON issues."""
    text_fields = ("title", "author", "keywords", "digest", "nickname", "cover")
    for a in articles:
        for field in text_fields:
            if field in a and isinstance(a[field], str):
                a[field] = sanitize_text(a[field])
    return articles


# ─── CSS ──────────────────────────────────────────────────────────

CSS = r"""
/* === Theme Variables === */
:root {
    --bg-primary: #f7f4f9;
    --bg-secondary: #ffffff;
    --bg-tertiary: #f5f0f7;
    --bg-recommended: #fefcf3;
    --bg-hover: #efe8f2;
    --text-primary: #1a1420;
    --text-secondary: #5c5060;
    --text-muted: #8e8094;
    --link-color: #6A2C70;
    --border: #e4dce8;
    --border-light: #d5cadb;
    --shadow-sm: 0 1px 3px rgba(106,44,112,0.06);
    --shadow-md: 0 2px 8px rgba(106,44,112,0.10);
    --shadow-lg: 0 2px 12px rgba(106,44,112,0.12);
    --header-gradient: linear-gradient(135deg, #6A2C70 0%, #8B3A7E 50%, #A052A0 100%);
    --header-text: #ffffff;
    --header-stat-bg: rgba(255,255,255,0.18);
    --accent: #6A2C70;
    --accent-hover: #5B1F60;
    --accent-light: rgba(106,44,112,0.10);
    --star-color: #D4A843;
    --star-inactive: #dad0e0;
    --badge-bg: #ede4f0;
    --badge-text: #6A2C70;
    --rec-border: #C4A23D;
    --toolbar-shadow: 0 1px 3px rgba(106,44,112,0.06);
    --input-focus-ring: rgba(106,44,112,0.12);
    --accordion-border: #e4dce8;
    --empty-color: #8e8094;
    /* Task-specific */
    --tab-active-bg: #ffffff;
    --tab-inactive-bg: #f0ecf3;
    --task-high-bg: #fef5f5;
    --task-high-border: #e53e3e;
    --task-medium-bg: #fffdf5;
    --task-medium-border: #dd6b20;
    --task-low-bg: #f5fdf7;
    --task-low-border: #38a169;
    --task-due-overdue: #e53e3e;
    --task-due-soon: #dd6b20;
    --task-due-normal: #718096;
}

/* === Dark Theme === */
[data-theme="dark"] {
    --bg-primary: #1a1220;
    --bg-secondary: #221830;
    --bg-tertiary: #281c36;
    --bg-recommended: #2a2218;
    --bg-hover: #2e2040;
    --text-primary: #e8e0ec;
    --text-secondary: #a890b0;
    --text-muted: #7a6880;
    --link-color: #c090d0;
    --border: #3a2848;
    --border-light: #483858;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.25);
    --shadow-md: 0 2px 8px rgba(0,0,0,0.35);
    --shadow-lg: 0 2px 12px rgba(0,0,0,0.40);
    --header-gradient: linear-gradient(135deg, #3D1540 0%, #5B1F60 50%, #6A2C70 100%);
    --header-text: #e8e0ec;
    --header-stat-bg: rgba(255,255,255,0.10);
    --accent: #a070b0;
    --accent-hover: #b080c0;
    --accent-light: rgba(160,112,176,0.15);
    --star-color: #D4A843;
    --star-inactive: #483858;
    --badge-bg: #3a2848;
    --badge-text: #a890b0;
    --rec-border: #B8963A;
    --toolbar-shadow: 0 1px 3px rgba(0,0,0,0.3);
    --input-focus-ring: rgba(160,112,176,0.18);
    --accordion-border: #3a2848;
    --empty-color: #7a6880;
    --tab-active-bg: #221830;
    --tab-inactive-bg: #2e2040;
    --task-high-bg: #3a1a1a;
    --task-high-border: #fc8181;
    --task-medium-bg: #3a2a1a;
    --task-medium-border: #f6ad55;
    --task-low-bg: #1a2e1a;
    --task-low-border: #68d391;
    --task-due-overdue: #fc8181;
    --task-due-soon: #f6ad55;
    --task-due-normal: #a0aec0;
}

@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
        --bg-primary: #1a1220;
        --bg-secondary: #221830;
        --bg-tertiary: #281c36;
        --bg-recommended: #2a2218;
        --bg-hover: #2e2040;
        --text-primary: #e8e0ec;
        --text-secondary: #a890b0;
        --text-muted: #7a6880;
        --link-color: #c090d0;
        --border: #3a2848;
        --border-light: #483858;
        --shadow-sm: 0 1px 3px rgba(0,0,0,0.25);
        --shadow-md: 0 2px 8px rgba(0,0,0,0.35);
        --shadow-lg: 0 2px 12px rgba(0,0,0,0.40);
        --header-gradient: linear-gradient(135deg, #3D1540 0%, #5B1F60 50%, #6A2C70 100%);
        --header-text: #e8e0ec;
        --header-stat-bg: rgba(255,255,255,0.10);
        --accent: #a070b0;
        --accent-hover: #b080c0;
        --accent-light: rgba(160,112,176,0.15);
        --star-color: #D4A843;
        --star-inactive: #483858;
        --badge-bg: #3a2848;
        --badge-text: #a890b0;
        --rec-border: #B8963A;
        --toolbar-shadow: 0 1px 3px rgba(0,0,0,0.3);
        --input-focus-ring: rgba(160,112,176,0.18);
        --accordion-border: #3a2848;
        --empty-color: #7a6880;
        --tab-active-bg: #221830;
        --tab-inactive-bg: #2e2040;
        --task-high-bg: #3a1a1a;
        --task-high-border: #fc8181;
        --task-medium-bg: #3a2a1a;
        --task-medium-border: #f6ad55;
        --task-low-bg: #1a2e1a;
        --task-low-border: #68d391;
        --task-due-overdue: #fc8181;
        --task-due-soon: #f6ad55;
        --task-due-normal: #a0aec0;
    }
}

/* === Reset === */
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue",
                 Arial, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    min-height: 100vh;
    transition: background 0.3s, color 0.3s;
}

/* === Header === */
.header {
    background: var(--header-gradient);
    color: var(--header-text);
    padding: 24px 32px;
    box-shadow: var(--shadow-lg);
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 16px;
}
.header-left { flex: 1; min-width: 200px; }
.header-left h1 {
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.header-left .subtitle {
    font-size: 0.85rem;
    opacity: 0.85;
    margin-top: 4px;
}
.header .stats {
    display: flex;
    gap: 20px;
    margin-top: 12px;
    flex-wrap: wrap;
}
.header .stat-item {
    background: var(--header-stat-bg);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.82rem;
    backdrop-filter: blur(4px);
}
.header-right { flex-shrink: 0; }

/* Theme toggle button */
.theme-toggle {
    background: rgba(255,255,255,0.15);
    border: 1.5px solid rgba(255,255,255,0.25);
    color: var(--header-text);
    font-size: 1.2rem;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    cursor: pointer;
    transition: background 0.2s, transform 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(4px);
}
.theme-toggle:hover {
    background: rgba(255,255,255,0.28);
    transform: scale(1.08);
}

/* === Tabs === */
.tabs {
    display: flex;
    gap: 0;
    background: var(--bg-secondary);
    border-bottom: 2px solid var(--border);
    padding: 0 24px;
    position: sticky;
    top: 0;
    z-index: 101;
    box-shadow: var(--toolbar-shadow);
    transition: background 0.3s, border-color 0.3s;
}
.tab-btn {
    padding: 12px 24px;
    border: none;
    background: none;
    font-size: 0.92rem;
    font-weight: 500;
    cursor: pointer;
    color: var(--text-secondary);
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: color 0.2s, border-color 0.2s;
    white-space: nowrap;
}
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
    font-weight: 600;
}
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* === Toolbar === */
.toolbar {
    background: var(--bg-secondary);
    padding: 14px 24px;
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    align-items: center;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: var(--toolbar-shadow);
    transition: background 0.3s, border-color 0.3s;
}
/* When tabs exist, toolbar scrolls under tabs */
.tabs ~ .tab-content .toolbar {
    top: 49px;
}
.toolbar input[type="text"] {
    flex: 1;
    min-width: 180px;
    padding: 8px 14px;
    border: 1.5px solid var(--border-light);
    border-radius: 24px;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.2s;
    background: var(--bg-secondary);
    color: var(--text-primary);
}
.toolbar input[type="text"]:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-light);
}
.toolbar input[type="text"]::placeholder { color: var(--text-muted); }
.toolbar select {
    padding: 8px 12px;
    border: 1.5px solid var(--border-light);
    border-radius: 8px;
    font-size: 0.85rem;
    background: var(--bg-secondary);
    color: var(--text-primary);
    cursor: pointer;
    outline: none;
    min-width: 140px;
}
.toolbar input[type="date"] {
    padding: 7px 10px;
    border: 1.5px solid var(--border-light);
    border-radius: 8px;
    font-size: 0.85rem;
    background: var(--bg-secondary);
    color: var(--text-primary);
    outline: none;
    cursor: pointer;
}
.toolbar .btn {
    padding: 8px 18px;
    border: none;
    border-radius: 8px;
    font-size: 0.85rem;
    cursor: pointer;
    font-weight: 500;
    transition: background 0.2s, color 0.2s;
}
.btn-primary {
    background: var(--accent);
    color: #fff;
}
.btn-primary:hover { background: var(--accent-hover); }
.btn-outline {
    background: var(--bg-secondary);
    color: var(--text-secondary);
    border: 1.5px solid var(--border-light) !important;
}
.btn-outline:hover { background: var(--bg-hover); }

/* === Main Content === */
.container {
    max-width: 960px;
    margin: 0 auto;
    padding: 20px 16px 60px;
}

/* === Section titles === */
.section-title {
    font-size: 1.15rem;
    font-weight: 600;
    margin: 24px 0 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-primary);
}
.section-title .icon { font-size: 1.3rem; }
.section-title .badge {
    background: var(--badge-bg);
    color: var(--badge-text);
    font-size: 0.78rem;
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: 500;
}

/* === Article Card === */
.article-card {
    background: var(--bg-secondary);
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 8px;
    border-left: 4px solid transparent;
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.2s, border-color 0.2s, background 0.3s;
    display: flex;
    align-items: flex-start;
    gap: 12px;
}
.article-card:hover { box-shadow: var(--shadow-md); }
.article-card.recommended {
    border-left-color: var(--rec-border);
    background: var(--bg-recommended);
}
.article-card .star-btn {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border: none;
    background: none;
    font-size: 1.3rem;
    cursor: pointer;
    border-radius: 50%;
    transition: transform 0.15s, background 0.15s;
    line-height: 32px;
    text-align: center;
    padding: 0;
    color: var(--star-inactive);
}
.article-card .star-btn:hover {
    transform: scale(1.2);
    background: var(--bg-hover);
}
.article-card .star-btn.starred { color: var(--star-color); }
.article-card .card-body { flex: 1; min-width: 0; }
.article-card .card-title {
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--link-color);
    text-decoration: none;
    display: block;
    margin-bottom: 6px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.article-card .card-title:hover { text-decoration: underline; }
.article-card .card-meta {
    font-size: 0.78rem;
    color: var(--text-secondary);
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
}
.article-card .card-meta .author-name {
    color: var(--text-primary);
    font-weight: 500;
}
.article-card .keyword-tags {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    margin-top: 6px;
}
.keyword-tag {
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 10px;
    white-space: nowrap;
    cursor: pointer;
    transition: opacity 0.15s;
    user-select: none;
}
.keyword-tag:hover { opacity: 0.75; }

[data-theme="dark"] .keyword-tag { filter: brightness(1.35) saturate(0.85); }
@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) .keyword-tag {
        filter: brightness(1.35) saturate(0.85);
    }
}

/* === Recommended Grid === */
.rec-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}
@media (max-width: 768px) { .rec-grid { grid-template-columns: 1fr; } }

.rec-grid .article-card {
    flex-direction: column;
    padding: 0;
    margin-bottom: 0;
    border-left: none;
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.25s, transform 0.25s;
}
.rec-grid .article-card:hover {
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
}
.rec-grid .article-card.recommended {
    border-color: var(--rec-border);
    background: var(--bg-recommended);
}
.rec-grid .card-cover {
    width: 100%;
    height: 180px;
    overflow: hidden;
    background: var(--bg-tertiary);
    position: relative;
    flex-shrink: 0;
}
.rec-grid .card-cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 0.3s ease;
}
.rec-grid .article-card:hover .card-cover img { transform: scale(1.05); }
.rec-grid .card-cover .cover-placeholder {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--accent) 0%, var(--bg-tertiary) 100%);
    font-size: 2.5rem;
    color: rgba(255,255,255,0.5);
}
.rec-grid .star-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 2;
    background: rgba(0,0,0,0.35);
    border-radius: 50%;
    width: 32px;
    height: 32px;
    line-height: 32px;
    text-align: center;
    color: #fff;
    font-size: 1.1rem;
    backdrop-filter: blur(2px);
}
.rec-grid .star-btn:hover { background: rgba(0,0,0,0.55); transform: scale(1.15); }
.rec-grid .star-btn.starred { color: var(--star-color); }
.rec-grid .card-body { padding: 14px 16px 16px; flex: 1; min-width: 0; }
.rec-grid .card-title {
    white-space: normal;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-size: 0.92rem;
    margin-bottom: 8px;
}
.rec-grid .card-meta { font-size: 0.76rem; }

.rec-grid .card-cover img.lazy-loaded {
    animation: fadeIn 0.35s ease-in;
}
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

/* === Accordion === */
.accordion { margin-bottom: 6px; }
.accordion-header {
    background: var(--bg-secondary);
    border: 1px solid var(--accordion-border);
    border-radius: 10px;
    padding: 12px 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 500;
    font-size: 0.92rem;
    transition: background 0.15s;
    user-select: none;
    color: var(--text-primary);
}
.accordion-header:hover { background: var(--bg-hover); }
.accordion-header .arrow {
    transition: transform 0.2s;
    font-size: 0.7rem;
    color: var(--text-secondary);
}
.accordion-header.open .arrow { transform: rotate(90deg); }
.accordion-header .author-avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    object-fit: cover;
    background: var(--badge-bg);
}
.accordion-header .count {
    margin-left: auto;
    font-size: 0.78rem;
    color: var(--text-secondary);
    font-weight: 400;
}
.accordion-body { display: none; padding: 4px 0 4px 38px; }
.accordion-body.open { display: block; }

/* === Task Cards === */
.task-card {
    background: var(--bg-secondary);
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 10px;
    box-shadow: var(--shadow-sm);
    display: flex;
    align-items: flex-start;
    gap: 14px;
    transition: box-shadow 0.2s;
    border-left: 4px solid transparent;
}
.task-card:hover { box-shadow: var(--shadow-md); }
.task-card.priority-high {
    border-left-color: var(--task-high-border);
    background: var(--task-high-bg);
}
.task-card.priority-medium {
    border-left-color: var(--task-medium-border);
    background: var(--task-medium-bg);
}
.task-card.priority-low {
    border-left-color: var(--task-low-border);
    background: var(--task-low-bg);
}
.task-card .task-icon {
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
}
.task-card.priority-high .task-icon { background: #fee2e2; }
.task-card.priority-medium .task-icon { background: #fef3c7; }
.task-card.priority-low .task-icon { background: #c6f6d5; }
[data-theme="dark"] .task-card.priority-high .task-icon { background: #5a2020; }
[data-theme="dark"] .task-card.priority-medium .task-icon { background: #5a4020; }
[data-theme="dark"] .task-card.priority-low .task-icon { background: #204020; }

.task-card .task-body { flex: 1; min-width: 0; }
.task-card .task-title {
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--text-primary);
    margin-bottom: 6px;
}
.task-card .task-title a {
    color: var(--link-color);
    text-decoration: none;
}
.task-card .task-title a:hover { text-decoration: underline; }
.task-card .task-meta {
    font-size: 0.78rem;
    color: var(--text-secondary);
    display: flex;
    gap: 14px;
    align-items: center;
    flex-wrap: wrap;
}
.task-card .task-due {
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
}
.task-card .task-due.overdue {
    color: var(--task-due-overdue);
    background: rgba(229,62,62,0.1);
}
.task-card .task-due.soon {
    color: var(--task-due-soon);
    background: rgba(221,107,32,0.1);
}
.task-card .task-due.normal {
    color: var(--task-due-normal);
}
.task-card .task-priority-badge {
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 500;
}
.task-card .task-source {
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
}
.task-card .task-description {
    font-size: 0.82rem;
    color: var(--text-secondary);
    margin-top: 6px;
    line-height: 1.5;
}

/* === Summary Card === */
.summary-card {
    background: var(--bg-secondary);
    border-radius: 10px;
    padding: 18px 22px;
    margin-bottom: 16px;
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
    line-height: 1.7;
    font-size: 0.9rem;
    color: var(--text-secondary);
}

/* === Empty State === */
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: var(--empty-color);
}
.empty-state .icon { font-size: 3rem; margin-bottom: 12px; }

/* === Footer === */
.footer {
    text-align: center;
    padding: 24px;
    font-size: 0.75rem;
    color: var(--text-muted);
}
.footer a { color: var(--link-color); }

/* === Responsive === */
@media (max-width: 600px) {
    .header { padding: 16px 20px; }
    .header h1 { font-size: 1.3rem; }
    .tabs { padding: 0 12px; }
    .tab-btn { padding: 10px 16px; font-size: 0.85rem; }
    .toolbar { padding: 10px 14px; flex-direction: column; }
    .toolbar input[type="text"] { width: 100%; }
    .toolbar select { width: 100%; }
    .article-card { padding: 12px 14px; }
    .article-card .card-title { font-size: 0.88rem; }
    .task-card { padding: 12px 14px; }
}
"""


# ─── JavaScript ───────────────────────────────────────────────────

JS = r"""
// --- Data ---
const ARTICLE_DATA = __ARTICLE_DATA_PLACEHOLDER__;
const LARK_TASKS = __LARK_TASKS_PLACEHOLDER__;
const ANALYSIS_DATA = __ANALYSIS_DATA_PLACEHOLDER__;
const ACTIVE_MODE = "__ACTIVE_MODE__";  // "all" | "wechat" | "lark"
const GENERATED_AT = "__GENERATED_AT__";
const KW_BG = __KW_BG__;
const KW_FG = __KW_FG__;
const KW_COLORS_LEN = __KW_COLORS_LEN__;
const PRIORITY_MAP = __PRIORITY_MAP__;

// --- Theme ---
(function initTheme() {
    const saved = localStorage.getItem("nku_infollows_theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
    updateThemeIcon();
})();

function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme");
    const next = (current === "dark") ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("nku_infollows_theme", next);
    updateThemeIcon();
}

function updateThemeIcon() {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    const current = document.documentElement.getAttribute("data-theme");
    if (!current) {
        const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        btn.textContent = prefersDark ? "☽" : "☀️";
        return;
    }
    btn.textContent = (current === "dark") ? "☽" : "☀️";
}

window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!localStorage.getItem("nku_infollows_theme")) updateThemeIcon();
});

// --- Tab switching ---
function switchTab(tabName) {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    const btn = document.getElementById("tab-" + tabName);
    const panel = document.getElementById("panel-" + tabName);
    if (btn) btn.classList.add("active");
    if (panel) panel.classList.add("active");
}

// --- State (articles) ---
let articles = ARTICLE_DATA;
let userStars = JSON.parse(localStorage.getItem("nku_infollows_stars") || "{}");
let filteredArticles = [...articles];
let currentSearch = "";
let currentAuthor = "";
let startDate = null;
let endDate = null;

// --- Init ---
document.addEventListener("DOMContentLoaded", () => {
    if (ACTIVE_MODE === "wechat" || ACTIVE_MODE === "all") {
        applyUserStars();
        populateAuthorFilter();
        renderAll();
        updateStats();
        document.getElementById("search-input").addEventListener("input", onSearch);
        document.getElementById("author-filter").addEventListener("change", onFilterChange);
        document.getElementById("date-start").addEventListener("change", onFilterChange);
        document.getElementById("date-end").addEventListener("change", onFilterChange);
        document.getElementById("sort-select").addEventListener("change", onSortChange);
        document.getElementById("clear-filters").addEventListener("click", clearFilters);
        document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
    }

    if (ACTIVE_MODE === "lark" || ACTIVE_MODE === "all") {
        renderTasks();
        document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
        // Task filter
        const taskFilter = document.getElementById("task-filter");
        if (taskFilter) {
            taskFilter.addEventListener("change", renderTasks);
        }
    }

    // Default to first available tab
    if (ACTIVE_MODE === "all") {
        switchTab("articles");
    }
});

// --- User stars ---
function applyUserStars() {
    articles.forEach(a => {
        if (userStars[a.id]) a.recommended = true;
    });
}

function toggleStar(articleId, btn) {
    if (userStars[articleId]) {
        delete userStars[articleId];
    } else {
        userStars[articleId] = true;
    }
    localStorage.setItem("nku_infollows_stars", JSON.stringify(userStars));
    applyUserStars();
    const card = btn.closest(".article-card");
    if (userStars[articleId]) {
        card.classList.add("recommended");
        btn.classList.add("starred");
        btn.textContent = "★";
    } else {
        card.classList.remove("recommended");
        btn.classList.remove("starred");
        btn.textContent = "☆";
    }
    updateStats();
}

// --- Render articles ---
function renderAll() {
    applyFilters();
    renderRecommendations();
    renderAccordions();
    updateStats();
}

function renderRecommendations() {
    const container = document.getElementById("recommendations");
    const recs = filteredArticles.filter(a => a.recommended);
    const section = document.getElementById("rec-section");
    const badge = document.getElementById("rec-count");
    if (recs.length === 0) {
        section.style.display = "none";
    } else {
        section.style.display = "";
        badge.textContent = recs.length;
        container.innerHTML = recs.map(a => renderRecCard(a)).join("");
        setupLazyLoading();
    }
}

function renderAccordions() {
    const container = document.getElementById("accordions");
    const showRecsOnly = document.getElementById("show-recs-only")?.checked || false;
    let list = filteredArticles;
    if (showRecsOnly) list = list.filter(a => a.recommended);

    const groups = {};
    list.forEach(a => {
        const author = a.author || "未知作者";
        if (!groups[author]) groups[author] = [];
        groups[author].push(a);
    });

    const sortedAuthors = Object.keys(groups).sort((a, b) =>
        a.localeCompare(b, "zh-Hans-CN")
    );

    let html = "";
    sortedAuthors.forEach(author => {
        html += renderAccordion(author, groups[author]);
    });

    if (sortedAuthors.length === 0) {
        html = `<div class="empty-state">
            <div class="icon">📭</div>
            <p>没有匹配的文章</p>
            <p style="font-size:0.8rem">尝试调整筛选条件</p>
        </div>`;
    }

    container.innerHTML = html;
    document.getElementById("all-count").textContent = list.length;
}

function renderCard(a, showStar) {
    if (showStar === undefined) showStar = true;
    const starred = userStars[a.id] || a.recommended;
    const dateStr = a.publish_time
        ? new Date(a.publish_time * 1000).toLocaleDateString("zh-CN")
        : "未知日期";
    const keywords = (a.keywords || "").split("|").map(k => k.trim()).filter(Boolean);
    const kwTags = keywords.map((kw, i) => {
        const colorIdx = i % KW_COLORS_LEN;
        return `<span class="keyword-tag" style="background:${KW_BG[colorIdx]};color:${KW_FG[colorIdx]}"
              onclick="document.getElementById('search-input').value='${kw.replace(/'/g, "\\'")}'; onSearch();">${kw}</span>`;
    }).join("");

    return `
    <div class="article-card ${a.recommended ? "recommended" : ""}" data-id="${a.id}">
        ${showStar ? `<button class="star-btn ${starred ? "starred" : ""}"
            onclick="toggleStar(${a.id}, this)" title="标记为推荐">${starred ? "★" : "☆"}</button>` : ""}
        <div class="card-body">
            <a class="card-title" href="${a.link || "#"}" target="_blank" rel="noopener"
               title="${htmlEscape(a.title)}">${a.title}</a>
            <div class="card-meta">
                <span class="author-name">${a.author || "未知作者"}</span>
                <span>${dateStr}</span>
            </div>
            ${kwTags ? `<div class="keyword-tags">${kwTags}</div>` : ""}
        </div>
    </div>`;
}

function renderRecCard(a) {
    const starred = userStars[a.id] || a.recommended;
    const dateStr = a.publish_time
        ? new Date(a.publish_time * 1000).toLocaleDateString("zh-CN")
        : "未知日期";
    const keywords = (a.keywords || "").split("|").map(k => k.trim()).filter(Boolean);
    const kwTags = keywords.map((kw, i) => {
        const colorIdx = i % KW_COLORS_LEN;
        return `<span class="keyword-tag" style="background:${KW_BG[colorIdx]};color:${KW_FG[colorIdx]}"
              onclick="event.stopPropagation(); document.getElementById('search-input').value='${kw.replace(/'/g, "\\'")}'; onSearch();">${kw}</span>`;
    }).join("");

    const coverUrl = a.cover || "";
    const coverHtml = coverUrl
        ? `<img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='200'%3E%3C/svg%3E"
                  data-src="${htmlEscape(coverUrl)}"
                  alt="${htmlEscape(a.title)}"
                  class="lazy-cover"
                  loading="lazy"
                  onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
           <div class="cover-placeholder" style="display:none">📰</div>`
        : `<div class="cover-placeholder">📰</div>`;

    return `
    <div class="article-card ${a.recommended ? "recommended" : ""}" data-id="${a.id}">
        <div class="card-cover">
            ${coverHtml}
            <button class="star-btn ${starred ? "starred" : ""}"
                onclick="event.stopPropagation(); toggleStar(${a.id}, this)"
                title="标记为推荐">${starred ? "★" : "☆"}</button>
        </div>
        <div class="card-body">
            <a class="card-title" href="${a.link || "#"}" target="_blank" rel="noopener"
               title="${htmlEscape(a.title)}">${a.title}</a>
            <div class="card-meta">
                <span class="author-name">${a.author || "未知作者"}</span>
                <span>${dateStr}</span>
            </div>
            ${kwTags ? `<div class="keyword-tags">${kwTags}</div>` : ""}
        </div>
    </div>`;
}

function setupLazyLoading() {
    const images = document.querySelectorAll(".rec-grid .card-cover img[data-src]");
    if ("IntersectionObserver" in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.getAttribute("data-src");
                    img.removeAttribute("data-src");
                    img.classList.add("lazy-loaded");
                    observer.unobserve(img);
                }
            });
        }, { rootMargin: "200px" });
        images.forEach(img => observer.observe(img));
    } else {
        images.forEach(img => {
            img.src = img.getAttribute("data-src");
            img.removeAttribute("data-src");
        });
    }
}

function renderAccordion(author, items) {
    const open = items.length <= 10;
    const headerClass = open ? "open" : "";
    const bodyClass = open ? "open" : "";
    return `
    <div class="accordion">
        <div class="accordion-header ${headerClass}" onclick="toggleAccordion(this)">
            <span class="arrow">▶</span>
            <span>${author}</span>
            <span class="count">${items.length} 篇</span>
        </div>
        <div class="accordion-body ${bodyClass}">
            ${items.map(a => renderCard(a)).join("")}
        </div>
    </div>`;
}

function toggleAccordion(header) {
    header.classList.toggle("open");
    const body = header.nextElementSibling;
    body.classList.toggle("open");
}

// --- Article filtering ---
function onSearch() {
    currentSearch = document.getElementById("search-input").value.trim().toLowerCase();
    renderAll();
}

function onFilterChange() {
    currentAuthor = document.getElementById("author-filter").value;
    const ds = document.getElementById("date-start").value;
    const de = document.getElementById("date-end").value;
    startDate = ds ? new Date(ds + "T00:00:00+08:00").getTime() / 1000 : null;
    endDate = de ? new Date(de + "T23:59:59+08:00").getTime() / 1000 : null;
    renderAll();
}

function onSortChange() {
    const sortBy = document.getElementById("sort-select").value;
    if (sortBy === "date-desc") {
        articles.sort((a, b) => (b.publish_time || 0) - (a.publish_time || 0));
    } else if (sortBy === "date-asc") {
        articles.sort((a, b) => (a.publish_time || 0) - (b.publish_time || 0));
    } else if (sortBy === "author") {
        articles.sort((a, b) => (a.author || "").localeCompare(b.author || "", "zh-Hans-CN"));
    } else if (sortBy === "recommended") {
        articles.sort((a, b) => (b.recommended ? 1 : 0) - (a.recommended ? 1 : 0));
    }
    renderAll();
}

function clearFilters() {
    document.getElementById("search-input").value = "";
    document.getElementById("author-filter").value = "";
    document.getElementById("date-start").value = "";
    document.getElementById("date-end").value = "";
    document.getElementById("sort-select").value = "date-desc";
    const cb = document.getElementById("show-recs-only");
    if (cb) cb.checked = false;
    currentSearch = "";
    currentAuthor = "";
    startDate = null;
    endDate = null;
    articles.sort((a, b) => (b.publish_time || 0) - (a.publish_time || 0));
    renderAll();
}

function applyFilters() {
    filteredArticles = articles.filter(a => {
        if (currentSearch) {
            const inTitle = (a.title || "").toLowerCase().includes(currentSearch);
            const inKw = (a.keywords || "").toLowerCase().includes(currentSearch);
            const inAuthor = (a.author || "").toLowerCase().includes(currentSearch);
            if (!inTitle && !inKw && !inAuthor) return false;
        }
        if (currentAuthor && a.author !== currentAuthor) return false;
        if (startDate !== null && (a.publish_time || 0) < startDate) return false;
        if (endDate !== null && (a.publish_time || 0) > endDate) return false;
        return true;
    });
}

function populateAuthorFilter() {
    const authors = [...new Set(articles.map(a => a.author || "未知作者"))].sort(
        (a, b) => a.localeCompare(b, "zh-Hans-CN")
    );
    const select = document.getElementById("author-filter");
    if (!select) return;
    authors.forEach(a => {
        const opt = document.createElement("option");
        opt.value = a;
        opt.textContent = a;
        select.appendChild(opt);
    });
}

function updateStats() {
    const totalEl = document.getElementById("total-count");
    const filteredEl = document.getElementById("filtered-count");
    const recEl = document.getElementById("rec-count");
    if (totalEl) totalEl.textContent = articles.length;
    if (filteredEl) filteredEl.textContent = filteredArticles.length;
    if (recEl) {
        recEl.textContent = filteredArticles.filter(a => a.recommended).length;
    }
}

// --- Task rendering ---
function parseDate(d) {
    if (!d) return null;
    return new Date(d).getTime();
}

function getDueClass(dueAt) {
    if (!dueAt) return { cls: "normal", label: "" };
    const due = new Date(dueAt).getTime();
    const now = Date.now();
    const day = 86400000;
    if (due < now) return { cls: "overdue", label: "已过期" };
    if (due - now < 2 * day) return { cls: "soon", label: "即将到期" };
    return { cls: "normal", label: "" };
}

function renderTaskCard(task, isPotential) {
    const priority = (task.priority || "medium").toLowerCase();
    const pInfo = PRIORITY_MAP[priority] || PRIORITY_MAP["medium"];
    const dueInfo = getDueClass(task.due_at || task.deadline);

    let dueHtml = "";
    if (task.due_at || task.deadline) {
        const dueDate = new Date(task.due_at || task.deadline);
        const dueStr = dueDate.toLocaleDateString("zh-CN");
        dueHtml = `<span class="task-due ${dueInfo.cls}">${dueInfo.label ? dueInfo.label + " " : ""}📅 ${dueStr}</span>`;
    }

    const icon = isPotential ? "🔍" : (task.completed ? "✅" : "📌");
    const titleHtml = task.url
        ? `<a href="${task.url}" target="_blank" rel="noopener">${htmlEscape(task.title)}</a>`
        : htmlEscape(task.title);

    let sourceHtml = "";
    if (task.source_chat) {
        sourceHtml = `<div class="task-source">📢 来自: ${htmlEscape(task.source_chat)}</div>`;
    }
    if (task.source_message_summary) {
        sourceHtml += `<div class="task-description">${htmlEscape(task.source_message_summary)}</div>`;
    }
    if (task.description && !isPotential) {
        sourceHtml += `<div class="task-description">${htmlEscape(task.description)}</div>`;
    }

    return `
    <div class="task-card priority-${priority}">
        <div class="task-icon">${icon}</div>
        <div class="task-body">
            <div class="task-title">${titleHtml}</div>
            <div class="task-meta">
                <span class="task-priority-badge" style="background:${pInfo[0]};color:${pInfo[1]}">${pInfo[2]}</span>
                ${dueHtml}
                ${task.created_at ? `<span>📅 创建: ${new Date(task.created_at).toLocaleDateString("zh-CN")}</span>` : ""}
            </div>
            ${sourceHtml}
        </div>
    </div>`;
}

function renderTasks() {
    const filterVal = document.getElementById("task-filter")?.value || "all";

    // Unfinished tasks section
    const unfinishedContainer = document.getElementById("unfinished-tasks");
    const unfinishedBadge = document.getElementById("unfinished-count");
    let unfinished = (LARK_TASKS.unfinished_tasks || []).filter(t => {
        if (filterVal === "all") return true;
        return (t.priority || "medium") === filterVal;
    });

    if (unfinished.length === 0) {
        if (filterVal !== "all") {
            unfinished = [];  // filtered to empty
        }
        document.getElementById("unfinished-section").style.display = unfinished.length === 0 && filterVal === "all" && (LARK_TASKS.unfinished_tasks || []).length === 0 ? "none" : "";
    } else {
        document.getElementById("unfinished-section").style.display = "";
    }

    if (unfinishedBadge) unfinishedBadge.textContent = unfinished.length;
    if (unfinishedContainer) {
        if (unfinished.length > 0) {
            unfinishedContainer.innerHTML = unfinished.map(t => renderTaskCard(t, false)).join("");
        } else if ((LARK_TASKS.unfinished_tasks || []).length > 0 && filterVal !== "all") {
            unfinishedContainer.innerHTML = `<div class="empty-state"><div class="icon">🔍</div><p>没有匹配的任务</p></div>`;
        } else if ((LARK_TASKS.unfinished_tasks || []).length === 0) {
            unfinishedContainer.innerHTML = `<div class="empty-state"><div class="icon">🎉</div><p>没有未完成的任务</p></div>`;
        }
    }

    // Potential tasks section
    const potentialContainer = document.getElementById("potential-tasks");
    const potentialBadge = document.getElementById("potential-count");
    let potential = (ANALYSIS_DATA.potential_tasks || []).filter(t => {
        if (filterVal === "all") return true;
        return (t.priority || "medium") === filterVal;
    });
    if (potentialBadge) potentialBadge.textContent = potential.length;
    if (potentialContainer) {
        const potSection = document.getElementById("potential-section");
        if (potential.length > 0 || (ANALYSIS_DATA.potential_tasks || []).length > 0) {
            potSection.style.display = "";
            if (potential.length > 0) {
                potentialContainer.innerHTML = potential.map(t => renderTaskCard(t, true)).join("");
            } else {
                potentialContainer.innerHTML = `<div class="empty-state"><div class="icon">🔍</div><p>没有匹配的任务</p></div>`;
            }
        } else {
            potSection.style.display = "none";
        }
    }

    // Summary
    const summaryContainer = document.getElementById("analysis-summary");
    if (summaryContainer && ANALYSIS_DATA.summary) {
        summaryContainer.textContent = ANALYSIS_DATA.summary;
        document.getElementById("summary-section").style.display = "";
    } else if (document.getElementById("summary-section")) {
        document.getElementById("summary-section").style.display = "none";
    }

    // Update task stats
    const totalTasksEl = document.getElementById("total-tasks-count");
    if (totalTasksEl) totalTasksEl.textContent = (LARK_TASKS.unfinished_tasks || []).length;
    const potentialTasksEl = document.getElementById("potential-tasks-count");
    if (potentialTasksEl) potentialTasksEl.textContent = (ANALYSIS_DATA.potential_tasks || []).length;

    // Show empty state if nothing at all
    if ((LARK_TASKS.unfinished_tasks || []).length === 0 && (ANALYSIS_DATA.potential_tasks || []).length === 0) {
        const taskEmpty = document.getElementById("tasks-empty-all");
        if (taskEmpty) taskEmpty.style.display = "";
    } else {
        const taskEmpty = document.getElementById("tasks-empty-all");
        if (taskEmpty) taskEmpty.style.display = "none";
    }
}

// --- Helpers ---
function htmlEscape(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
""".lstrip()


# ─── HTML Rendering ───────────────────────────────────────────────

def _render_html(
    articles: list[dict],
    lark_tasks: dict,
    analysis_data: dict,
    active_mode: str,
    generated_at: str,
) -> str:
    """Render the full HTML page with tabs for articles and tasks."""

    kw_bg = [c[0] for c in KEYWORD_COLORS]
    kw_fg = [c[1] for c in KEYWORD_COLORS]
    kw_colors_len = len(KEYWORD_COLORS)

    # Priority map for JS
    priority_map = {k: list(v) for k, v in PRIORITY_COLORS.items()}

    # Embed data
    articles_json = json.dumps(articles, ensure_ascii=False, indent=2)
    lark_tasks_json = json.dumps(lark_tasks, ensure_ascii=False)
    analysis_json = json.dumps(analysis_data, ensure_ascii=False)

    js_code = JS.replace("__ARTICLE_DATA_PLACEHOLDER__", articles_json)
    js_code = js_code.replace("__LARK_TASKS_PLACEHOLDER__", lark_tasks_json)
    js_code = js_code.replace("__ANALYSIS_DATA_PLACEHOLDER__", analysis_json)
    js_code = js_code.replace("__ACTIVE_MODE__", active_mode)
    js_code = js_code.replace("__GENERATED_AT__", generated_at)
    js_code = js_code.replace("__KW_COLORS_LEN__", str(kw_colors_len))
    js_code = js_code.replace("__KW_BG__", json.dumps(kw_bg))
    js_code = js_code.replace("__KW_FG__", json.dumps(kw_fg))
    js_code = js_code.replace("__PRIORITY_MAP__", json.dumps(priority_map))

    # Determine visibility
    has_articles = len(articles) > 0 or active_mode in ("wechat", "all")
    has_tasks = active_mode in ("lark", "all")
    show_tabs = active_mode == "all" and has_articles and has_tasks

    # Build subtitle
    if active_mode == "wechat":
        subtitle = "微信公众号文章智能推荐"
    elif active_mode == "lark":
        subtitle = "飞书任务与消息智能分析"
    else:
        subtitle = "微信公众号 + 飞书任务 · 智能聚合"

    # Build header stats
    stats_html = ""
    if active_mode in ("wechat", "all"):
        stats_html += """
            <span class="stat-item">📄 文章总计: <b id="total-count">0</b> 篇</span>
            <span class="stat-item">🔍 显示: <b id="filtered-count">0</b> 篇</span>
            <span class="stat-item">⭐ 推荐: <b id="rec-count">0</b> 篇</span>"""
    if active_mode in ("lark", "all"):
        stats_html += f"""
            <span class="stat-item">📋 未完成任务: <b id="total-tasks-count">{len(lark_tasks.get('unfinished_tasks', []))}</b> 个</span>
            <span class="stat-item">🔍 潜在任务: <b id="potential-tasks-count">{len(analysis_data.get('potential_tasks', []))}</b> 个</span>"""

    # Build tabs
    tabs_html = ""
    if show_tabs:
        tabs_html = """
        <div class="tabs">
            <button class="tab-btn active" id="tab-articles" onclick="switchTab('articles')">📰 文章推荐</button>
            <button class="tab-btn" id="tab-tasks" onclick="switchTab('tasks')">✅ 飞书任务</button>
        </div>"""

    # Build article panel
    article_panel = ""
    if active_mode in ("wechat", "all"):
        active_class = "active" if active_mode == "wechat" or show_tabs else ""
        article_panel = f"""
        <div class="tab-panel {active_class}" id="panel-articles">
            <div class="toolbar">
                <input type="text" id="search-input" placeholder="🔍 搜索标题、关键词、作者...">
                <select id="author-filter" aria-label="按作者筛选">
                    <option value="">全部作者</option>
                </select>
                <input type="date" id="date-start" title="开始日期" style="max-width:140px">
                <input type="date" id="date-end" title="结束日期" style="max-width:140px">
                <select id="sort-select" aria-label="排序方式">
                    <option value="date-desc">🕐 最新优先</option>
                    <option value="date-asc">🕐 最早优先</option>
                    <option value="author">📂 按作者</option>
                    <option value="recommended">⭐ 推荐优先</option>
                </select>
                <label style="font-size:0.85rem;display:flex;align-items:center;gap:4px;cursor:pointer;white-space:nowrap;color:var(--text-primary)">
                    <input type="checkbox" id="show-recs-only" onchange="renderAll()"> 仅推荐
                </label>
                <button class="btn btn-outline" id="clear-filters">重置</button>
            </div>
            <div class="container">
                <div id="rec-section">
                    <div class="section-title">
                        <span class="icon">⭐</span> 推荐阅读
                        <span class="badge" id="rec-count">0</span>
                    </div>
                    <div id="recommendations" class="rec-grid"></div>
                </div>
                <div class="section-title">
                    <span class="icon">📰</span> 全部文章
                    <span class="badge" id="all-count">0</span>
                </div>
                <div id="accordions"></div>
            </div>
        </div>"""

    # Build task panel
    task_panel = ""
    if active_mode in ("lark", "all"):
        active_class = "active" if active_mode == "lark" else ""
        unfinished_tasks = lark_tasks.get("unfinished_tasks", [])
        potential_tasks = analysis_data.get("potential_tasks", [])
        analysis_summary = analysis_data.get("summary", "")

        task_panel = f"""
        <div class="tab-panel {active_class}" id="panel-tasks">
            <div class="toolbar">
                <span style="font-size:0.9rem;font-weight:500;color:var(--text-primary)">🎯 任务筛选:</span>
                <select id="task-filter" aria-label="按优先级筛选任务">
                    <option value="all">全部优先级</option>
                    <option value="high">🔴 高优先级</option>
                    <option value="medium">🟡 中优先级</option>
                    <option value="low">🟢 低优先级</option>
                </select>
                <span style="font-size:0.8rem;color:var(--text-muted);margin-left:auto">
                    数据获取时间: {lark_tasks.get('fetched_at', generated_at)[:16] if lark_tasks.get('fetched_at') else generated_at[:16]}
                </span>
            </div>
            <div class="container">

                <div id="unfinished-section">
                    <div class="section-title">
                        <span class="icon">📋</span> 未完成任务
                        <span class="badge" id="unfinished-count">{len(unfinished_tasks)}</span>
                    </div>
                    <div id="unfinished-tasks">
                        {''.join(_render_task_html(t, False) for t in unfinished_tasks) if unfinished_tasks else '<div class="empty-state"><div class="icon">🎉</div><p>没有未完成的任务</p></div>'}
                    </div>
                </div>

                <div id="potential-section" style="{'display:none' if not potential_tasks and not analysis_summary else ''}">
                    <div class="section-title">
                        <span class="icon">🔍</span> 消息中检测到的潜在任务
                        <span class="badge" id="potential-count">{len(potential_tasks)}</span>
                    </div>
                    <div id="summary-section" style="{'display:none' if not analysis_summary else ''}">
                        <div class="summary-card" id="analysis-summary">{html_mod.escape(analysis_summary) if analysis_summary else ''}</div>
                    </div>
                    <div id="potential-tasks">
                        {''.join(_render_task_html(t, True) for t in potential_tasks) if potential_tasks else ''}
                    </div>
                </div>

                <div id="tasks-empty-all" class="empty-state" style="display:{'none' if unfinished_tasks or potential_tasks else ''}">
                    <div class="icon">📭</div>
                    <p>暂无任务数据</p>
                    <p style="font-size:0.8rem">运行飞书集成以获取任务和消息分析</p>
                </div>

            </div>
        </div>"""

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NKU-InFollows — 智能推荐</title>
<style>
{CSS}
</style>
</head>
<body>

<header class="header">
    <div class="header-left">
        <h1>📰 NKU-InFollows</h1>
        <div class="subtitle">{subtitle}</div>
        <div class="stats">
            {stats_html}
            <span class="stat-item">🕐 生成: {generated_at}</span>
        </div>
    </div>
    <div class="header-right">
        <button class="theme-toggle" id="theme-toggle" title="切换深色/浅色主题" aria-label="切换主题">☀️</button>
    </div>
</header>

{tabs_html}

{article_panel}
{task_panel}

<div class="footer">
    NKU-InFollows · Generated {generated_at} ·
    由 <a href="https://github.com/tmwgsicp/wechat-download-api" target="_blank">wechat-download-api</a> 与
    <a href="https://open.larkoffice.com" target="_blank">飞书 Lark CLI</a> 提供支持
</div>

<script>
{js_code}
</script>
</body>
</html>"""
    return page


def _render_task_html(task: dict, is_potential: bool) -> str:
    """Render a single task card as static HTML (server-side fallback)."""
    priority = (task.get("priority", "medium") or "medium").lower()
    p_info = PRIORITY_COLORS.get(priority, PRIORITY_COLORS["medium"])

    icon = "🔍" if is_potential else ("✅" if task.get("completed") else "📌")
    title = task.get("title", "未命名任务")
    url = task.get("url", "")

    title_html = f'<a href="{html_mod.escape(url)}" target="_blank" rel="noopener">{html_mod.escape(title)}</a>' if url else html_mod.escape(title)

    parts = [f"""<div class="task-card priority-{priority}">
        <div class="task-icon">{icon}</div>
        <div class="task-body">
            <div class="task-title">{title_html}</div>
            <div class="task-meta">
                <span class="task-priority-badge" style="background:{p_info[0]};color:{p_info[1]}">{p_info[2]}</span>"""]

    due_at = task.get("due_at") or task.get("deadline")
    if due_at:
        parts.append(f'<span>📅 {due_at[:10]}</span>')

    created_at = task.get("created_at")
    if created_at and not is_potential:
        parts.append(f'<span>📅 创建: {created_at[:10]}</span>')

    parts.append("</div>")

    if task.get("source_chat"):
        parts.append(f'<div class="task-source">📢 来自: {html_mod.escape(task["source_chat"])}</div>')
    if task.get("source_message_summary"):
        parts.append(f'<div class="task-description">{html_mod.escape(task["source_message_summary"])}</div>')
    if task.get("description") and not is_potential:
        parts.append(f'<div class="task-description">{html_mod.escape(task["description"])}</div>')

    parts.append("</div></div>")
    return "\n".join(parts)


# ─── Main ─────────────────────────────────────────────────────────

def _detect_mode() -> str:
    """Detect the active mode from available data and mode file."""
    # Check explicit mode file
    if MODE_FILE.exists():
        try:
            mode_data = json.loads(MODE_FILE.read_text(encoding="utf-8"))
            return mode_data.get("mode", "all")
        except Exception:
            pass

    # Auto-detect from available files
    has_articles = ARTICLES_FILE.exists()
    has_tasks = LARK_TASKS_FILE.exists()
    has_analysis = LARK_MESSAGES_FILE.exists()

    if has_articles and (has_tasks or has_analysis):
        return "all"
    elif has_articles:
        return "wechat"
    elif has_tasks or has_analysis:
        return "lark"
    else:
        return "wechat"  # default


def main() -> int:
    print_header("生成推荐页面")

    # Detect mode
    active_mode = _detect_mode()
    mode_labels = {"all": "全部 (文章 + 飞书任务)", "wechat": "仅微信公众号", "lark": "仅飞书任务"}
    print_info(f"运行模式: {mode_labels.get(active_mode, active_mode)}")

    # ── Load articles ──
    articles = []
    if active_mode in ("wechat", "all"):
        if ARTICLES_FILE.exists():
            try:
                articles = json.loads(ARTICLES_FILE.read_text(encoding="utf-8"))
                print_info(f"已加载 {len(articles)} 篇文章")
            except json.JSONDecodeError as e:
                print_err(f"文章 JSON 解析失败: {e}")
        else:
            print_info(f"文章数据文件不存在: {ARTICLES_FILE}")
    else:
        print_info("当前模式不需要文章数据")

    # Sanitize articles
    if articles:
        articles = sanitize_articles(articles)
        # Validate required fields
        required = {"id", "title", "link", "author"}
        for i, a in enumerate(articles):
            missing = required - set(a.keys())
            if missing:
                print_err(f"第 {i + 1} 篇文章缺少字段: {missing}")

    # ── Load Lark tasks ──
    lark_tasks = {"unfinished_tasks": [], "completed_tasks": [], "total": 0, "fetched_at": ""}
    if active_mode in ("lark", "all"):
        if LARK_TASKS_FILE.exists():
            try:
                lark_tasks = json.loads(LARK_TASKS_FILE.read_text(encoding="utf-8"))
                unfinished = len(lark_tasks.get("unfinished_tasks", []))
                completed = len(lark_tasks.get("completed_tasks", []))
                print_info(f"已加载飞书任务: {unfinished} 个未完成, {completed} 个已完成")
            except json.JSONDecodeError as e:
                print_err(f"飞书任务 JSON 解析失败: {e}")
        else:
            print_info(f"飞书任务数据文件不存在: {LARK_TASKS_FILE}")

    # ── Load message analysis ──
    analysis_data = {"potential_tasks": [], "summary": ""}
    if active_mode in ("lark", "all"):
        if LARK_MESSAGES_FILE.exists():
            try:
                analysis_data = json.loads(LARK_MESSAGES_FILE.read_text(encoding="utf-8"))
                potential = len(analysis_data.get("potential_tasks", []))
                print_info(f"已加载消息分析: {potential} 个潜在任务")
            except json.JSONDecodeError as e:
                print_err(f"消息分析 JSON 解析失败: {e}")
        else:
            print_info(f"消息分析数据文件不存在: {LARK_MESSAGES_FILE}")

    # ── Early exit if nothing to show ──
    if not articles and not lark_tasks.get("unfinished_tasks") and not analysis_data.get("potential_tasks"):
        print_err("没有可展示的数据！")
        print_info("请先获取微信公众号文章或飞书任务数据")
        return 1

    # ── Generate HTML ──
    generated_at = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    html = _render_html(articles, lark_tasks, analysis_data, active_mode, generated_at)

    RECOMMENDATIONS_HTML.parent.mkdir(parents=True, exist_ok=True)
    RECOMMENDATIONS_HTML.write_text(html, encoding="utf-8")

    size_kb = RECOMMENDATIONS_HTML.stat().st_size / 1024
    print_ok(f"推荐页面已生成: {RECOMMENDATIONS_HTML} ({size_kb:.1f} KB)")
    print_info("支持深色/浅色主题切换 · 文章+任务聚合视图")

    return 0


if __name__ == "__main__":
    sys.exit(main())
