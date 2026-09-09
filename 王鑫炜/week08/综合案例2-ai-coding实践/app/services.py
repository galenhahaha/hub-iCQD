"""检索能力的抽象接口与本地确定性实现。

本模块只知道"关键词 -> 结果列表"，不知道"轮次""充分性"，也不拼装报告。
"""

import asyncio
import hashlib
import logging
import math
from typing import List, Optional, Protocol, Sequence, Tuple
from urllib.parse import parse_qs, urlparse

import httpx
from lxml import html as lxml_html

from app.models import SearchResult

logger = logging.getLogger(__name__)


class SearchError(Exception):
    """检索服务自身可预期的失败（网络错误、超时、上游 5xx 等）。"""


class SearchService(Protocol):
    """检索服务抽象。

    结构化子类型（Protocol）：任何实现了 `search(keyword) -> List[SearchResult]`
    的对象都满足契约，测试桩无需继承即可注入。
    """

    async def search(self, keyword: str) -> List[SearchResult]:
        """返回该关键词的检索结果，可能为空列表。"""
        ...


# 固定 URL 池：不同关键词可能命中同一个 URL，用于构造去重场景。
_URL_POOL: Tuple[str, ...] = (
    "https://example.com/agent-frameworks",
    "https://example.com/agent-orchestration",
    "https://example.com/tool-use",
    "https://example.com/multi-agent-systems",
    "https://example.com/llm-evaluation",
)

_TITLE_POOL: Tuple[str, ...] = (
    "主流 Agent 框架综述",
    "Agent 编排与工作流实践",
    "工具调用与函数调用指南",
    "多智能体系统设计要点",
    "大模型应用评测方法",
)


class MockSearchService:
    """确定性本地模拟检索：同一 keyword 永远返回同一组结果。

    结果由 keyword 的稳定哈希（sha256，不用内置 hash()，避免 PYTHONHASHSEED 随机化）
    派生 1~3 条，URL 从固定池中取，因此不同关键词可能返回相同 URL。
    """

    def __init__(self, url_pool: Sequence[str] = _URL_POOL,
                 title_pool: Sequence[str] = _TITLE_POOL) -> None:
        if not url_pool:
            raise ValueError("url_pool 不能为空")
        self._url_pool = tuple(url_pool)
        self._title_pool = tuple(title_pool)

    async def search(self, keyword: str) -> List[SearchResult]:
        normalized = (keyword or "").strip()
        if not normalized:
            return []

        digest = hashlib.sha256(normalized.encode("utf-8")).digest()
        count = 1 + digest[0] % 3
        results: List[SearchResult] = []
        for offset in range(count):
            index = digest[1 + offset] % len(self._url_pool)
            title = self._title_pool[index] if index < len(self._title_pool) else "参考资料"
            results.append(
                SearchResult(title="{0}（{1}）".format(title, normalized),
                             url=self._url_pool[index])
            )
        logger.debug("mock search for %r -> %d results", normalized, len(results))
        return results


class BochaSearchService:
    """Bocha 网页搜索真实适配器。

    只负责把上游响应转换为领域 DTO；超时、重试和降级由
    ``ResilientSearchService`` 统一处理。
    """

    def __init__(self, *, api_key: str, base_url: str,
                 count: int = 8, timeout: float = 30) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._count = count
        self._timeout = timeout

    async def search(self, keyword: str) -> List[SearchResult]:
        normalized = (keyword or "").strip()
        if not normalized:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._base_url,
                    headers={
                        "Authorization": "Bearer {0}".format(self._api_key),
                        "Content-Type": "application/json",
                    },
                    json={"query": normalized, "summary": True, "count": self._count},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001 - 由外层重试包装器处理
            raise SearchError("Bocha 搜索失败：{0}".format(exc)) from exc

        pages = payload.get("data", {}).get("webPages", {}).get("value", [])
        results: List[SearchResult] = []
        for page in pages:
            url = (page.get("url") or "").strip()
            title = (page.get("name") or "").strip()
            if not url:
                continue
            item = SearchResult(title=title or "未命名来源", url=url)
            item._snippet = (page.get("snippet") or page.get("summary") or "")[:1200]
            results.append(item)
        logger.info("Bocha 搜索 keyword=%r results=%d", normalized, len(results))
        return results


class DuckDuckGoSearchService:
    """免费 DuckDuckGo HTML 搜索适配器。

    不需要 API Key，但它依赖公开搜索页面，可能受到限流或页面变更影响，
    因此仍由 ``ResilientSearchService`` 负责重试和降级。解析只保留标题、
    最终 URL 和摘要，避免把 HTML 细节泄漏到领域层。
    """

    def __init__(self, *, count: int = 8, timeout: float = 30,
                 base_url: str = "https://html.duckduckgo.com/html/") -> None:
        self._count = count
        self._timeout = timeout
        self._base_url = base_url

    async def search(self, keyword: str) -> List[SearchResult]:
        normalized = (keyword or "").strip()
        if not normalized:
            return []

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": "Mozilla/5.0 (AI Coding Research Assistant)"},
            ) as client:
                response = await client.get(
                    self._base_url,
                    params={"q": normalized, "kl": "cn-zh"},
                )
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - 由外层重试包装器处理
            raise SearchError("DuckDuckGo 搜索失败：{0}".format(exc)) from exc

        root = lxml_html.fromstring(response.text)
        cards = root.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' result ')]"
        )
        results: List[SearchResult] = []
        for card in cards[:self._count]:
            title_nodes = card.xpath(
                ".//a[contains(concat(' ', normalize-space(@class), ' '), ' result__a ')]"
            )
            if not title_nodes:
                continue
            title_node = title_nodes[0]
            title = " ".join(title_node.text_content().split())
            raw_url = (title_node.get("href") or "").strip()
            query = parse_qs(urlparse(raw_url).query)
            url = (query.get("uddg", [raw_url])[0] or "").strip()
            if url.startswith("//"):
                url = "https:" + url
            if not url:
                continue
            item = SearchResult(title=title or "未命名来源", url=url)
            snippets = card.xpath(
                ".//*[contains(concat(' ', normalize-space(@class), ' '), ' result__snippet ')]"
            )
            item._snippet = " ".join(snippets[0].text_content().split())[:1200] if snippets else ""
            results.append(item)
        logger.info("DuckDuckGo 搜索 keyword=%r results=%d", normalized, len(results))
        return results


class ResilientSearchService:
    """超时/重试/降级包装器，实现同一 `SearchService` 协议，对引擎完全透明。

    - 每次尝试用 `asyncio.wait_for` 施加超时；
    - 失败（超时或异常）后最多再重试 `retries` 次，共 `retries + 1` 次尝试；
    - 全部尝试失败后抛 `SearchError`，由 `ResearchEngine.search()` 统一降级为空结果。
    """

    def __init__(self, delegate: SearchService, *, timeout: float = 2.0,
                 retries: int = 1) -> None:
        """校验构造参数：`timeout` 必须是有限正数，`retries` 必须是非负整数。

        `math.isfinite` 一次判掉 `NaN` 与 `±Inf`（`NaN <= 0` 恒为 `False`，只用比较
        运算符会让 `NaN` 漏网）；非法取值在构造期抛 `ValueError`，不推迟到检索调用。
        """
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool)
                or not math.isfinite(timeout)
                or timeout <= 0):
            raise ValueError(
                "timeout 必须为有限正数（拒绝 NaN / ±Inf / 0 / 负数），"
                "实际为 {0!r}".format(timeout)
            )
        if not isinstance(retries, int) or retries < 0:
            raise ValueError(
                "retries 必须为非负整数，实际为 {0!r}".format(retries)
            )
        self._delegate = delegate
        self._timeout = timeout
        self._retries = retries

    @property
    def max_attempts(self) -> int:
        """总尝试次数 = 首次 + 重试次数。"""
        return self._retries + 1

    async def search(self, keyword: str) -> List[SearchResult]:
        last_error: Optional[BaseException] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await asyncio.wait_for(
                    self._delegate.search(keyword), timeout=self._timeout
                )
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "检索超时（第 %d/%d 次）keyword=%r，timeout=%ss",
                    attempt, self.max_attempts, keyword, self._timeout,
                )
            except Exception as exc:  # 含 SearchError：一律重试，最终由引擎降级
                last_error = exc
                logger.warning(
                    "检索失败（第 %d/%d 次）keyword=%r：%s",
                    attempt, self.max_attempts, keyword, exc,
                )
        raise SearchError(
            "检索在 {0} 次尝试后仍失败（keyword={1!r}）：{2!r}".format(
                self.max_attempts, keyword, last_error
            )
        )
