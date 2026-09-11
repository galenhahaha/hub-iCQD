"""Load project configuration and expose shared runtime paths."""

from datetime import date
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "research"
TEMPLATE_DIR = BASE_DIR / "templates"

# Read configuration only from the process environment; never load .env files.

# Prefer the provider-specific name while retaining OpenAI-compatible setups.
OPENAI_API_KEY = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/")
MODEL_NAME = os.environ.get("MODEL_NAME", "deepseek-v4-flash")

BOCHA_API_KEY = os.environ.get("BOCHA_API_KEY", "")
BOCHA_SEARCH_COUNT = int(os.environ.get("BOCHA_SEARCH_COUNT", "10"))
MAX_ROUNDS = int(os.environ.get("RESEARCH_MAX_ROUNDS", "3"))
LLM_RETRIES = int(os.environ.get("LLM_RETRIES", "3"))
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")


def ensure_data_dir() -> None:
    """Create the research storage directory when the application starts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def today_str() -> str:
    """Return today's date in the local timezone as YYYY-MM-DD."""
    return date.today().isoformat()
