# -*- coding: utf-8 -*-
"""Bocha 网页搜索工具。"""
from __future__ import annotations

import httpx

from . import config


async def web_search(query: str) -> list[dict]:
    """调用 Bocha 网页搜索，返回解析后的结果列表。

    每项含 title / url / snippet / site_name / date 五个字段，供来源收集与正文抽取使用。
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.bocha.cn/v1/web-search",
            headers={
                "Authorization": f"Bearer {config.BOCHA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"query": query, "summary": True, "count": config.BOCHA_SEARCH_COUNT},
        )
        resp.raise_for_status()
        data = resp.json()

    pages = data.get("data", {}).get("webPages", {}).get("value", [])
    out = []
    for p in pages:
        snippet = (p.get("snippet") or p.get("summary") or "").strip()
        out.append(
            {
                "title": p.get("name") or "",
                "url": p.get("url") or "",
                "snippet": snippet[:500],
                "site_name": p.get("siteName") or "",
                "date": p.get("datePublished") or p.get("dateLastCrawled") or "",
            }
        )
    return out


if __name__ == "__main__":
    # 自检 demo：单次 Bocha 搜索（需要 .env 里的 Bocha key 与网络，人工验证用）
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    results = asyncio.run(web_search("天空为什么是蓝色的？"))
    print(f"返回 {len(results)} 条结果")
    for r in results[:3]:
        print(f"- {r['title'][:40]} | {r['url'][:50]}")
