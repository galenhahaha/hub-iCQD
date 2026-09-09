"""FastAPI 应用：路由、输入校验与依赖装配。

本模块不写研究逻辑；400 校验放在路由层显式抛出（Pydantic validator 会返回 422）。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException

from app import config
from app.engine import ResearchEngine
from app.llm import LLMService, OpenAICompatibleLLMService
from app.models import ResearchRequest, ResearchResponse
from app.services import (
    BochaSearchService,
    DuckDuckGoSearchService,
    MockSearchService,
    ResilientSearchService,
    SearchService,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="简易研究助手",
    description="生成关键词 → 搜索 → 汇总 → 判断充分性 → 出报告（支持 Mock/真实模式）",
    version="0.1.0",
)


def get_search_service() -> SearchService:
    """根据 RESEARCH_MODE 装配免费 DuckDuckGo、Bocha 或离线 Mock 搜索。"""
    if config.RESEARCH_MODE == "real":
        settings = config.real_config()
        if settings.search_provider == "duckduckgo":
            delegate = DuckDuckGoSearchService(
                count=settings.bocha_search_count,
                timeout=settings.search_timeout,
            )
        else:
            delegate = BochaSearchService(
                api_key=settings.bocha_api_key,
                base_url=settings.bocha_base_url,
                count=settings.bocha_search_count,
                timeout=settings.search_timeout,
            )
        return ResilientSearchService(
            delegate,
            timeout=settings.search_timeout,
            retries=settings.search_retries,
        )
    return MockSearchService()


def get_llm_service() -> Optional[LLMService]:
    """真实模式装配 OpenAI 兼容 LLM；Mock 模式返回 None。"""
    if config.RESEARCH_MODE != "real":
        return None
    settings = config.real_config()
    return OpenAICompatibleLLMService(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout=settings.llm_timeout,
    )


def get_engine(
    search_service: SearchService = Depends(get_search_service),
    llm_service: Optional[LLMService] = Depends(get_llm_service),
) -> ResearchEngine:
    """引擎提供者：搜索和 LLM 能力均通过构造函数注入。"""
    return ResearchEngine(search_service, llm_service=llm_service)


@app.post("/api/research", response_model=ResearchResponse)
async def research(
    payload: ResearchRequest,
    engine: ResearchEngine = Depends(get_engine),
) -> ResearchResponse:
    """接收研究主题并返回五段式研究报告。"""
    topic = (payload.topic or "").strip()
    if not topic:
        # 校验发生在调用引擎之前，因此空主题不会触发任何检索。
        raise HTTPException(status_code=400, detail="topic 不能为空或仅含空白字符")
    logger.info("收到研究请求：%s", topic)
    return await engine.run(topic)
