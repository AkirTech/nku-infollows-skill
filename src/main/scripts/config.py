"""
Shared configuration for nku-infollows-skill scripts.

Reads environment variables with sensible defaults.
All other scripts in this directory import from here.
"""
import os
import sys
from pathlib import Path

# --- Backend connection ---
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000").rstrip("/")

# --- Rate limits (mirrors backend env.example) ---
RATE_LIMIT_GLOBAL = int(os.getenv("RATE_LIMIT_GLOBAL", "10"))       # requests/min
RATE_LIMIT_PER_IP = int(os.getenv("RATE_LIMIT_PER_IP", "5"))       # requests/min per IP
RATE_LIMIT_ARTICLE_INTERVAL = int(os.getenv("RATE_LIMIT_ARTICLE_INTERVAL", "3"))  # seconds

# --- Temp directory for generated files ---
SCRIPTS_DIR = Path(__file__).parent.resolve()
TEMP_DIR = SCRIPTS_DIR / "temp"

# --- Standard file paths ---
ARTICLES_FILE = TEMP_DIR / "articles_with_keywords.json"
STATE_FILE = TEMP_DIR / ".state.json"
RECOMMENDATIONS_HTML = TEMP_DIR / "recommendations.html"
LARK_TASKS_FILE = TEMP_DIR / "lark_tasks.json"
LARK_MESSAGES_FILE = TEMP_DIR / "lark_messages_analysis.json"
MODE_FILE = TEMP_DIR / ".mode.json"

# --- Ensure temp directory exists ---
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# --- Unicode console output (Windows) ---
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass  # already UTF-8 or platform doesn't support reconfigure

# --- Utility ---
def print_header(title: str) -> None:
    """Print a formatted section header."""
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")

def print_ok(msg: str) -> None:
    """Print a success message."""
    print(f"  [OK] {msg}")

def print_err(msg: str) -> None:
    """Print an error message."""
    print(f"  [ERROR] {msg}", file=sys.stderr)

def print_info(msg: str) -> None:
    """Print an info message."""
    print(f"  [INFO] {msg}")
