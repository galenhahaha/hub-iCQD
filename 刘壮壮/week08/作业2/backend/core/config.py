"""从项目根目录的 .env 读取配置。"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# backend/core/config.py → 项目根
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid int for %s=%r, using %s", name, raw, default)
        return default


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4-flash").strip()

BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", "").strip()
BOCHA_SEARCH_COUNT = _int("BOCHA_SEARCH_COUNT", 10)
# auto：时效主题默认先搜一年内，没查到再放开；也可填 oneYear / oneMonth / noLimit
BOCHA_FRESHNESS = os.getenv("BOCHA_FRESHNESS", "auto").strip() or "auto"

RESEARCH_MAX_ROUNDS = max(1, _int("RESEARCH_MAX_ROUNDS", 3))
LLM_RETRIES = max(1, _int("LLM_RETRIES", 3))

BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1").strip() or "127.0.0.1"
BACKEND_PORT = _int("BACKEND_PORT", 8000)
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").strip()

DATA_DIR = ROOT / "backend" / "data" / "research"


def cors_origins() -> list[str]:
    origins = {FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000"}
    return [o for o in origins if o]


if __name__ == "__main__":
    print("ROOT", ROOT)
    print("MODEL_NAME", MODEL_NAME)
    print("OPENAI_BASE_URL", OPENAI_BASE_URL)
    print("OPENAI_API_KEY set", bool(OPENAI_API_KEY))
    print("BOCHA_API_KEY set", bool(BOCHA_API_KEY))
    print("BOCHA_FRESHNESS", BOCHA_FRESHNESS)
    print("RESEARCH_MAX_ROUNDS", RESEARCH_MAX_ROUNDS)
    print("LLM_RETRIES", LLM_RETRIES)
    print("DATA_DIR", DATA_DIR)
    print("cors", cors_origins())
