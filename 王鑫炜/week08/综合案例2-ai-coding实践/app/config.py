"""真实服务配置。

默认保持离线 Mock 模式，避免测试或启动服务时意外产生外部 API 费用。
设置 RESEARCH_MODE=real 后，会启用免费 DuckDuckGo（或可选的 Bocha）+ OpenAI 兼容 LLM。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


RESEARCH_MODE = _env("RESEARCH_MODE", "mock").lower()
SEARCH_PROVIDER = _env("SEARCH_PROVIDER", "duckduckgo").lower()
BOCHA_API_KEY = _env("BOCHA_API_KEY")
BOCHA_BASE_URL = _env("BOCHA_BASE_URL", "https://api.bocha.cn/v1/web-search")
SEARCH_COUNT = int(_env("SEARCH_COUNT", _env("BOCHA_SEARCH_COUNT", "8")))
BOCHA_SEARCH_COUNT = SEARCH_COUNT  # 兼容旧配置名

LLM_API_KEY = _env("LLM_API_KEY", _env("OPENAI_API_KEY"))
LLM_BASE_URL = _env("LLM_BASE_URL", _env("OPENAI_BASE_URL", "https://api.deepseek.com/v1"))
LLM_MODEL = _env("LLM_MODEL", _env("MODEL_NAME", "deepseek-chat"))
LLM_TIMEOUT = float(_env("LLM_TIMEOUT", "60"))
SEARCH_TIMEOUT = float(_env("SEARCH_TIMEOUT", "30"))
SEARCH_RETRIES = int(_env("SEARCH_RETRIES", "1"))


@dataclass(frozen=True)
class RealConfig:
    """已校验的真实服务配置，避免适配器各自读取环境变量。"""

    search_provider: str
    bocha_api_key: str
    bocha_base_url: str
    bocha_search_count: int
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_timeout: float
    search_timeout: float
    search_retries: int


def real_config() -> RealConfig:
    """读取并校验真实模式所需配置，不打印密钥。"""
    if SEARCH_PROVIDER not in {"duckduckgo", "bocha"}:
        raise RuntimeError("SEARCH_PROVIDER 必须是 duckduckgo 或 bocha")
    missing = []
    if SEARCH_PROVIDER == "bocha" and not BOCHA_API_KEY:
        missing.append("BOCHA_API_KEY")
    if not LLM_API_KEY:
        missing.append("LLM_API_KEY（或 OPENAI_API_KEY）")
    if missing:
        raise RuntimeError(
            "真实模式缺少环境变量：{0}。请复制 .env.example 为 .env 并填写，"
            "或暂时使用 RESEARCH_MODE=mock。".format("、".join(missing))
        )
    if SEARCH_COUNT < 1:
        raise RuntimeError("SEARCH_COUNT 必须为正整数")
    if LLM_TIMEOUT <= 0 or SEARCH_TIMEOUT <= 0:
        raise RuntimeError("LLM_TIMEOUT 和 SEARCH_TIMEOUT 必须为正数")
    if SEARCH_RETRIES < 0:
        raise RuntimeError("SEARCH_RETRIES 不能为负数")
    return RealConfig(
        search_provider=SEARCH_PROVIDER,
        bocha_api_key=BOCHA_API_KEY,
        bocha_base_url=BOCHA_BASE_URL,
        bocha_search_count=SEARCH_COUNT,
        llm_api_key=LLM_API_KEY,
        llm_base_url=LLM_BASE_URL,
        llm_model=LLM_MODEL,
        llm_timeout=LLM_TIMEOUT,
        search_timeout=SEARCH_TIMEOUT,
        search_retries=SEARCH_RETRIES,
    )
