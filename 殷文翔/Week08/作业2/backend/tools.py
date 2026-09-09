"""Async Bocha search; callers decide how to recover from request failures."""

from typing import Any

import httpx

from . import config


BOCHA_SEARCH_URL = "https://api.bocha.cn/v1/web-search"


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


async def web_search(query: str) -> list[dict[str, str]]:
    """Return normalized snippets without fetching individual web pages."""
    query = query.strip()
    if not query:
        return []
    if not config.BOCHA_API_KEY:
        raise ValueError("BOCHA_API_KEY 未配置，请设置进程环境变量。")
    if config.BOCHA_SEARCH_COUNT < 1:
        raise ValueError("BOCHA_SEARCH_COUNT 必须大于 0。")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            BOCHA_SEARCH_URL,
            headers={"Authorization": f"Bearer {config.BOCHA_API_KEY}"},
            json={"query": query, "summary": True, "count": config.BOCHA_SEARCH_COUNT},
        )
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("Bocha 响应必须是 JSON 对象。")
    if payload.get("code", 200) not in (200, "200"):
        raise RuntimeError("Bocha 搜索返回业务错误。")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise ValueError("Bocha 响应 data 格式错误。")
    web_pages = data.get("webPages") or {}
    if not isinstance(web_pages, dict):
        raise ValueError("Bocha 响应 webPages 格式错误。")
    pages = web_pages.get("value") or []
    if not isinstance(pages, list):
        raise ValueError("Bocha 响应 value 必须是列表。")

    results = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        url = _text(page.get("url")).strip()
        if not url:
            continue
        results.append(
            {
                "title": _text(page.get("name")),
                "url": url,
                "snippet": (_text(page.get("snippet")) or _text(page.get("summary")))[:500],
                "site_name": _text(page.get("siteName")),
                "date": _text(page.get("datePublished")) or _text(page.get("dateLastCrawled")),
            }
        )
    return results
