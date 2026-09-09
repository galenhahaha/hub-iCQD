"""
Bocha 网页搜索客户端
====================
对 Bocha Web Search API 做最小封装，返回统一的、易用的结果结构。
接口文档：https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK

调用示例（对应 README 里的 curl）：
    POST https://api.bocha.cn/v1/web-search
    Authorization: Bearer <BOCHA_API_KEY>
    {"query": "...", "summary": true, "count": 10}

解析做保守处理：优先按官方结构 data.webPages.value 解析；
取不到时再递归扫描响应体找“含 url 的对象数组”，尽量降低接口小改动带来的崩溃风险。
"""
from __future__ import annotations

from typing import Any, Dict, List

import httpx

from .config import Settings


class SearchError(RuntimeError):
    """搜索接口调用 / 解析失败。"""


async def bocha_search(
    query: str,
    count: int,
    settings: Settings,
) -> List[Dict[str, Any]]:
    """异步执行一次网页搜索，返回规范化后的结果列表。

    每个结果至少含字段：name / url / snippet / summary / site_name / date
    （缺字段时已归一化为空字符串，方便后续统一拼接使用）。
    """
    if not settings.bocha_api_key:
        raise SearchError("未配置 BOCHA_API_KEY，无法调用网页搜索")

    payload: Dict[str, Any] = {"query": query, "summary": True, "count": count}
    headers = {
        "Authorization": f"Bearer {settings.bocha_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.bocha_timeout) as client:
            resp = await client.post(settings.bocha_url, headers=headers, json=payload)
            resp.raise_for_status()
            body: Dict[str, Any] = resp.json()
    except httpx.HTTPError as exc:
        raise SearchError(f"搜索请求失败（query={query}）：{exc}") from exc
    except ValueError as exc:
        raise SearchError(f"搜索返回非 JSON（query={query}）：{exc}") from exc

    pages = _extract_pages(body)
    return pages[:count]  # 以 count 为最终上限，防止接口返回异常多


def _extract_pages(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 Bocha 响应体中抽取网页结果列表（多级兜底）。"""
    data = body.get("data") or {}
    if isinstance(data, dict):
        web_pages = data.get("webPages") or {}
        value = web_pages.get("value") if isinstance(web_pages, dict) else None
        if isinstance(value, list) and value:
            return [_normalize(p) for p in value if isinstance(p, dict)]

    # 兜底：递归扫描整棵 data，寻找第一个“看起来像网页列表”的数组
    found = _find_page_list(data)
    if found:
        return [_normalize(p) for p in found]

    # 明确报错，便于排查
    message = body.get("msg") or body.get("message") or body.get("log_id")
    raise SearchError(f"搜索结果解析失败，响应中没有找到网页结果：{message}")


def _find_page_list(node: Any) -> List[Any]:
    """递归查找最像“网页列表”的对象数组（含 url/link 字段）。"""
    if isinstance(node, dict):
        for key in ("value", "items", "results", "list", "webPages"):
            child = node.get(key)
            if (
                isinstance(child, list)
                and child
                and all(
                    isinstance(x, dict) and ("url" in x or "link" in x) for x in child[:3]
                )
            ):
                return child
        for child in node.values():
            found = _find_page_list(child)
            if found:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_page_list(child)
            if found:
                return found
    return []


def _normalize(item: Dict[str, Any]) -> Dict[str, Any]:
    """把接口字段统一成内部约定字段名，缺失给空串。"""
    return {
        "name": str(item.get("name") or item.get("title") or ""),
        "url": str(item.get("url") or item.get("link") or ""),
        "snippet": str(item.get("snippet") or ""),
        "summary": str(item.get("summary") or ""),
        "site_name": str(item.get("siteName") or item.get("site_name") or ""),
        "date": str(item.get("dateLastCrawled") or item.get("date") or ""),
        "language": str(item.get("language") or ""),
    }
