"""Bocha 网页搜索。第一版只用标题 / 摘要 / snippet，不抓全文。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .core import config

logger = logging.getLogger(__name__)

BOCHA_URL = "https://api.bocha.cn/v1/web-search"


def _as_dict(item: Any) -> dict[str, Any]:
    return item if isinstance(item, dict) else {}


def _pick_pages(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    pages = data.get("webPages") if isinstance(data, dict) else None
    if isinstance(pages, dict):
        value = pages.get("value")
        if isinstance(value, list):
            return [p for p in value if isinstance(p, dict)]
    if isinstance(data, dict) and isinstance(data.get("value"), list):
        return [p for p in data["value"] if isinstance(p, dict)]
    return []


def normalize_hit(item: dict[str, Any]) -> dict[str, str]:
    title = str(item.get("name") or item.get("title") or "").strip()
    url = str(item.get("url") or item.get("displayUrl") or "").strip()
    snippet = str(
        item.get("summary") or item.get("snippet") or item.get("description") or ""
    ).strip()
    site = str(item.get("siteName") or item.get("site_name") or "").strip()
    published = str(item.get("datePublished") or item.get("date") or "").strip()
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "site_name": site,
        "published": published,
    }


async def web_search(
    query: str, *, count: int | None = None, freshness: str | None = None
) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    if not config.BOCHA_API_KEY:
        raise RuntimeError("BOCHA_API_KEY is missing")
    body: dict[str, Any] = {
        "query": q,
        "summary": True,
        "count": count or config.BOCHA_SEARCH_COUNT,
    }
    fresh = (freshness or "").strip()
    if fresh and fresh not in {"noLimit", "auto"}:
        body["freshness"] = fresh
    headers = {
        "Authorization": f"Bearer {config.BOCHA_API_KEY}",
        "Content-Type": "application/json",
    }
    logger.info("bocha search query=%s freshness=%s", q, body.get("freshness", "noLimit"))
    async with httpx.AsyncClient(timeout=45.0) as http:
        resp = await http.post(BOCHA_URL, headers=headers, json=body)
        resp.raise_for_status()
        payload = resp.json()
    hits = [normalize_hit(p) for p in _pick_pages(payload)]
    hits = [h for h in hits if h["url"]]
    logger.info("bocha hits=%s", len(hits))
    return hits


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    sample = _pick_pages({"data": {"webPages": {"value": [{"name": "t", "url": "https://x"}]}}})
    print("parse", normalize_hit(sample[0]))

    async def _live() -> None:
        if not config.BOCHA_API_KEY:
            print("skip live search: no BOCHA_API_KEY")
            return
        rows = await web_search("天空为什么是蓝色的")
        print("live", len(rows), rows[:1])

    asyncio.run(_live())
