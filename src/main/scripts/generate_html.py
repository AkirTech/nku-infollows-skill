"""
Generate a standalone HTML recommendation page from articles JSON.

Reads articles_with_keywords.json and produces recommendations.html.
The generated HTML is fully self-contained (inline CSS + JS, no external deps).

Features:
- Dark/light theme with auto-detection (prefers-color-scheme) + manual toggle
- Theme preference persisted in localStorage
- Smart article card rendering with keyword tags and star-based recommendations
- Search, filter by author/date, sort, and accordion grouping
"""

import sys
import json
import html as html_mod
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure clean Unicode output on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import (
    ARTICLES_FILE,
    RECOMMENDATIONS_HTML,
    TEMP_DIR,
    print_header,
    print_ok,
    print_err,
    print_info,
)

# Timezone for China (UTC+8)
CST = timezone(timedelta(hours=8))

# Keyword tag color palette (light-theme pairs; dark theme adjusts via CSS opacity)
KEYWORD_COLORS = [
    ("#e8f5e9", "#2e7d32"),  # green
    ("#e3f2fd", "#1565c0"),  # blue
    ("#fff3e0", "#e65100"),  # orange
    ("#fce4ec", "#c62828"),  # red/pink
    ("#f3e5f5", "#6a1b9a"),  # purple
    ("#e0f7fa", "#00695c"),  # teal
    ("#fff8e1", "#f9a825"),  # amber
    ("#f1f8e9", "#558b2f"),  # light green
]


# ─── Sanitization ─────────────────────────────────────────────────

def sanitize_text(s: str) -> str:
    """Replace smart/curly quotes with corner brackets to avoid JSON breakage."""
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
    text_fields = ("title", "author", "keywords", "digest", "nickname")
    for a in articles:
        for field in text_fields:
            if field in a and isinstance(a[field], str):
                a[field] = sanitize_text(a[field])
    return articles


# ─── CSS ──────────────────────────────────────────────────────────

CSS = r"""
/* === Theme Variables === */
:root {
    --bg-primary: #f5f7fa;
    --bg-secondary: #ffffff;
    --bg-tertiary: #f8f9fa;
    --bg-recommended: #fffde7;
    --bg-hover: #f1f3f4;
    --text-primary: #202124;
    --text-secondary: #5f6368;
    --text-muted: #9aa0a6;
    --link-color: #1a73e8;
    --border: #e8eaed;
    --border-light: #dadce0;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
    --shadow-md: 0 2px 8px rgba(0,0,0,0.10);
    --shadow-lg: 0 2px 8px rgba(0,0,0,0.12);
    --header-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    --header-text: #ffffff;
    --header-stat-bg: rgba(255,255,255,0.18);
    --accent: #667eea;
    --accent-hover: #5a6fd6;
    --accent-light: rgba(102,126,234,0.12);
    --star-color: #f9a825;
    --star-inactive: #dadce0;
    --badge-bg: #e8eaed;
    --badge-text: #5f6368;
    --rec-border: #f9a825;
    --toolbar-shadow: 0 1px 3px rgba(0,0,0,0.06);
    --card-border-left: transparent;
    --input-focus-ring: rgba(102,126,234,0.12);
    --accordion-border: #e8eaed;
    --empty-color: #9aa0a6;
}

/* === Dark Theme === */
[data-theme="dark"] {
    --bg-primary: #1a1a2e;
    --bg-secondary: #252540;
    --bg-tertiary: #2a2a48;
    --bg-recommended: #2d2a18;
    --bg-hover: #303055;
    --text-primary: #e8eaed;
    --text-secondary: #9aa0a6;
    --text-muted: #6e7380;
    --link-color: #8ab4f8;
    --border: #3c3c5c;
    --border-light: #4a4a6a;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.25);
    --shadow-md: 0 2px 8px rgba(0,0,0,0.35);
    --shadow-lg: 0 2px 12px rgba(0,0,0,0.40);
    --header-gradient: linear-gradient(135deg, #4a54b8 0%, #5c3a7a 100%);
    --header-text: #e8eaed;
    --header-stat-bg: rgba(255,255,255,0.10);
    --accent: #8e99f0;
    --accent-hover: #7a86e0;
    --accent-light: rgba(142,153,240,0.15);
    --star-color: #fdd835;
    --star-inactive: #4a4a6a;
    --badge-bg: #3c3c5c;
    --badge-text: #9aa0a6;
    --rec-border: #fdd835;
    --toolbar-shadow: 0 1px 3px rgba(0,0,0,0.3);
    --card-border-left: transparent;
    --input-focus-ring: rgba(142,153,240,0.18);
    --accordion-border: #3c3c5c;
    --empty-color: #6e7380;
}

/* Auto-detect system preference (overridden by manual toggle) */
@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
        --bg-primary: #1a1a2e;
        --bg-secondary: #252540;
        --bg-tertiary: #2a2a48;
        --bg-recommended: #2d2a18;
        --bg-hover: #303055;
        --text-primary: #e8eaed;
        --text-secondary: #9aa0a6;
        --text-muted: #6e7380;
        --link-color: #8ab4f8;
        --border: #3c3c5c;
        --border-light: #4a4a6a;
        --shadow-sm: 0 1px 3px rgba(0,0,0,0.25);
        --shadow-md: 0 2px 8px rgba(0,0,0,0.35);
        --shadow-lg: 0 2px 12px rgba(0,0,0,0.40);
        --header-gradient: linear-gradient(135deg, #4a54b8 0%, #5c3a7a 100%);
        --header-text: #e8eaed;
        --header-stat-bg: rgba(255,255,255,0.10);
        --accent: #8e99f0;
        --accent-hover: #7a86e0;
        --accent-light: rgba(142,153,240,0.15);
        --star-color: #fdd835;
        --star-inactive: #4a4a6a;
        --badge-bg: #3c3c5c;
        --badge-text: #9aa0a6;
        --rec-border: #fdd835;
        --toolbar-shadow: 0 1px 3px rgba(0,0,0,0.3);
        --card-border-left: transparent;
        --input-focus-ring: rgba(142,153,240,0.18);
        --accordion-border: #3c3c5c;
        --empty-color: #6e7380;
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
.toolbar input[type="text"]::placeholder {
    color: var(--text-muted);
}
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
    max-width: 900px;
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
    border-left: 4px solid var(--card-border-left);
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.2s, border-color 0.2s, background 0.3s;
    display: flex;
    align-items: flex-start;
    gap: 12px;
}
.article-card:hover {
    box-shadow: var(--shadow-md);
}
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
.article-card .star-btn.starred {
    color: var(--star-color);
}
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

/* Dark theme: lighten keyword tag backgrounds for readability */
[data-theme="dark"] .keyword-tag {
    filter: brightness(1.35) saturate(0.85);
}
@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) .keyword-tag {
        filter: brightness(1.35) saturate(0.85);
    }
}

/* === Accordion === */
.accordion {
    margin-bottom: 6px;
}
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
.accordion-body {
    display: none;
    padding: 4px 0 4px 38px;
}
.accordion-body.open { display: block; }

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
    .toolbar { padding: 10px 14px; flex-direction: column; }
    .toolbar input[type="text"] { width: 100%; }
    .toolbar select { width: 100%; }
    .article-card { padding: 12px 14px; }
    .article-card .card-title { font-size: 0.88rem; }
}
"""


# ─── JavaScript ───────────────────────────────────────────────────

JS = r"""
// --- Data ---
const ARTICLE_DATA = __ARTICLE_DATA_PLACEHOLDER__;
const GENERATED_AT = "__GENERATED_AT__";
const KW_BG = __KW_BG__;
const KW_FG = __KW_FG__;
const KW_COLORS_LEN = __KW_COLORS_LEN__;

// --- Theme ---
(function initTheme() {
    const saved = localStorage.getItem("nku_infollows_theme");
    if (saved) {
        document.documentElement.setAttribute("data-theme", saved);
    }
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
    const current = document.documentElement.getAttribute("data-theme");
    // If no manual toggle set, check system preference
    if (!current) {
        const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        btn.textContent = prefersDark ? "☽" : "☀️";
        return;
    }
    btn.textContent = (current === "dark") ? "☽" : "☀️";
}

// Listen for system theme changes (only matters when no manual override)
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!localStorage.getItem("nku_infollows_theme")) {
        updateThemeIcon();
    }
});

// --- State ---
let articles = ARTICLE_DATA;
let userStars = JSON.parse(localStorage.getItem("nku_infollows_stars") || "{}");
let filteredArticles = [...articles];
let currentSearch = "";
let currentAuthor = "";
let startDate = null;
let endDate = null;

// --- Init ---
document.addEventListener("DOMContentLoaded", () => {
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
    // Re-render the specific card
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

// --- Render ---
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
        container.innerHTML = recs.map(a => renderCard(a)).join("");
    }
}

function renderAccordions() {
    const container = document.getElementById("accordions");
    const showRecsOnly = document.getElementById("show-recs-only").checked;

    let list = filteredArticles;
    if (showRecsOnly) {
        list = list.filter(a => a.recommended);
    }

    // Group by author
    const groups = {};
    list.forEach(a => {
        const author = a.author || "未知作者";
        if (!groups[author]) groups[author] = [];
        groups[author].push(a);
    });

    // Sort groups alphabetically
    const sortedAuthors = Object.keys(groups).sort((a, b) =>
        a.localeCompare(b, "zh-Hans-CN")
    );

    let html = "";
    sortedAuthors.forEach(author => {
        const items = groups[author];
        html += renderAccordion(author, items);
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

function renderAccordion(author, items) {
    const open = items.length <= 10; // auto-open small groups
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

// --- Filtering ---
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
    document.getElementById("show-recs-only").checked = false;
    currentSearch = "";
    currentAuthor = "";
    startDate = null;
    endDate = null;
    articles.sort((a, b) => (b.publish_time || 0) - (a.publish_time || 0));
    renderAll();
}

function applyFilters() {
    filteredArticles = articles.filter(a => {
        // Text search
        if (currentSearch) {
            const inTitle = (a.title || "").toLowerCase().includes(currentSearch);
            const inKw = (a.keywords || "").toLowerCase().includes(currentSearch);
            const inAuthor = (a.author || "").toLowerCase().includes(currentSearch);
            if (!inTitle && !inKw && !inAuthor) return false;
        }
        // Author filter
        if (currentAuthor && a.author !== currentAuthor) return false;
        // Date range
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
    authors.forEach(a => {
        const opt = document.createElement("option");
        opt.value = a;
        opt.textContent = a;
        select.appendChild(opt);
    });
}

function updateStats() {
    document.getElementById("total-count").textContent = articles.length;
    document.getElementById("filtered-count").textContent = filteredArticles.length;
    const recCount = filteredArticles.filter(a => a.recommended).length;
    document.getElementById("rec-count").textContent = recCount;
}

// --- Helpers ---
function htmlEscape(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
""".lstrip()


# ─── HTML Rendering ───────────────────────────────────────────────

def _render_html(articles: list[dict], generated_at: str) -> str:
    """Render the full HTML page."""
    kw_bg = [c[0] for c in KEYWORD_COLORS]
    kw_fg = [c[1] for c in KEYWORD_COLORS]
    kw_colors_len = len(KEYWORD_COLORS)

    # Escape article data for embedding in HTML
    articles_json = json.dumps(articles, ensure_ascii=False, indent=2)

    js_code = JS.replace("__ARTICLE_DATA_PLACEHOLDER__", articles_json)
    js_code = js_code.replace("__GENERATED_AT__", generated_at)
    js_code = js_code.replace("__KW_COLORS_LEN__", str(kw_colors_len))
    js_code = js_code.replace("__KW_BG__", json.dumps(kw_bg))
    js_code = js_code.replace("__KW_FG__", json.dumps(kw_fg))

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>nku-inFollows — 文章推荐</title>
<style>
{CSS}
</style>
</head>
<body>

<header class="header">
    <div class="header-left">
        <h1>📰 nku-inFollows</h1>
        <div class="subtitle">微信公众号文章智能推荐</div>
        <div class="stats">
            <span class="stat-item">📄 总计: <b id="total-count">0</b> 篇</span>
            <span class="stat-item">🔍 显示: <b id="filtered-count">0</b> 篇</span>
            <span class="stat-item">⭐ 推荐: <b id="rec-count">0</b> 篇</span>
            <span class="stat-item">🕐 生成: {generated_at}</span>
        </div>
    </div>
    <div class="header-right">
        <button class="theme-toggle" id="theme-toggle" title="切换深色/浅色主题" aria-label="切换主题">☀️</button>
    </div>
</header>

<div class="toolbar">
    <input type="text" id="search-input"
           placeholder="🔍 搜索标题、关键词、作者...">
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

<main class="container">

    <div id="rec-section">
        <div class="section-title">
            <span class="icon">⭐</span> 推荐阅读
            <span class="badge" id="rec-count">0</span>
        </div>
        <div id="recommendations"></div>
    </div>

    <div class="section-title">
        <span class="icon">📰</span> 全部文章
        <span class="badge" id="all-count">0</span>
    </div>
    <div id="accordions"></div>

    <div class="footer">
        nku-inFollows · Generated {generated_at} ·
        由 <a href="https://github.com/tmwgsicp/wechat-download-api" target="_blank">wechat-download-api</a> 提供支持
    </div>

</main>

<script>
{js_code}
</script>
</body>
</html>"""
    return page


# ─── Main ─────────────────────────────────────────────────────────

def main() -> int:
    print_header("生成推荐页面")

    # Check input file
    if not ARTICLES_FILE.exists():
        print_err(f"找不到数据文件: {ARTICLES_FILE}")
        print_info("请先获取文章并生成 articles_with_keywords.json")
        return 1

    # Load articles
    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except json.JSONDecodeError as e:
        print_err(f"JSON 解析失败: {e}")
        print_info("提示: 检查文章标题中是否含有特殊引号字符 (\"\") — 脚本已自动清理，请重新生成 JSON")
        return 1

    if not articles:
        print_info("文章列表为空，将生成空页面")

    # Sanitize text fields (curly quotes → corner brackets)
    articles = sanitize_articles(articles)

    print_info(f"已加载 {len(articles)} 篇文章")

    # Validate required fields
    required = {"id", "title", "link", "author"}
    for i, a in enumerate(articles):
        missing = required - set(a.keys())
        if missing:
            print_err(f"第 {i + 1} 篇文章缺少字段: {missing}")

    # Generate HTML
    generated_at = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    html = _render_html(articles, generated_at)

    with open(RECOMMENDATIONS_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = RECOMMENDATIONS_HTML.stat().st_size / 1024
    print_ok(f"推荐页面已生成: {RECOMMENDATIONS_HTML} ({size_kb:.1f} KB)")
    print_info("支持深色/浅色主题切换（自动检测系统偏好 + 手动切换按钮）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
