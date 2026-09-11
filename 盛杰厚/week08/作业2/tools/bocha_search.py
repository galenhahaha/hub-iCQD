"""Bocha Web Search 工具封装。

既提供纯函数 ``web_search``（供确定性检索节点调用），也提供 LangChain
``@tool`` 包装版本 ``web_search_tool``，便于把检索步骤替换为工具调用 Agent。
"""
from __future__ import annotations

import requests
from langchain_core.tools import tool

from config import BOCHA_API_KEY, BOCHA_SEARCH_URL


class SearchError(RuntimeError):
    """Bocha 搜索失败。"""


def web_search(query: str, count: int = 6, summary: bool = True) -> list[dict]:
    """调用 Bocha Web Search，返回清洗后的结果列表。

    返回项字段：title / url / site_name / snippet / summary / date
    """
    headers = {
        "Authorization": f"Bearer {BOCHA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "summary": summary, "count": count}
    resp = requests.post(BOCHA_SEARCH_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise SearchError(f"Bocha search failed: code={data.get('code')} msg={data.get('msg')}")

    pages = ((data.get("data") or {}).get("webPages") or {}).get("value") or []
    out: list[dict] = []
    for p in pages:
        out.append({
            "title": (p.get("name") or "").strip(),
            "url": p.get("url") or p.get("displayUrl") or "",
            "site_name": p.get("siteName") or "",
            "snippet": (p.get("snippet") or "").strip(),
            "summary": (p.get("summary") or p.get("snippet") or "").strip(),
            "date": p.get("datePublished") or "",
        })
    return out


@tool
def web_search_tool(query: str, count: int = 6) -> list[dict]:
    """搜索网页，返回标题、URL、摘要、发布时间等信息。

    Args:
        query: 检索关键词。
        count: 返回条数。
    """
    return web_search(query, count=count, summary=True)
