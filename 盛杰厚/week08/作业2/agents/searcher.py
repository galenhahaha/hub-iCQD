"""Searcher 检索节点：调用 Bocha 搜索、去重、记录过程。

说明：检索本身是确定性动作（无需 LLM 决策），故实现为普通函数节点；
「检索什么」的智能由 Planner / Judge 提供关键词。也可用 tools 包中的
``web_search_tool`` 把该步骤替换为工具调用 Agent。
"""
from __future__ import annotations

from config import (
    MAX_KEYWORDS_PER_ROUND,
    MAX_PAGES_PER_EXTRACT,
    MAX_SUMMARY_CHARS,
    SEARCH_COUNT_PER_KEYWORD,
)
from state import ResearchState
from tools.bocha_search import web_search


def searcher_node(state: ResearchState) -> dict:
    iteration = int(state.get("iteration", 0)) + 1
    keywords = state.get("keywords", [])
    search_history = state.get("search_history", [])

    # 本轮只检索未检索过的新关键词，并限制数量
    new_keywords = [k for k in keywords if k not in search_history]
    new_keywords = new_keywords[:MAX_KEYWORDS_PER_ROUND]

    fetched: list[dict] = []
    for kw in new_keywords:
        try:
            fetched.extend(web_search(kw, count=SEARCH_COUNT_PER_KEYWORD))
        except Exception as exc:  # 单个关键词失败不中断整体
            print(f"    [search] 关键词 {kw!r} 检索失败: {exc}")

    # 按 URL 去重（保留最早出现的）
    seen_urls = {p["url"] for p in state.get("pages_read", [])}
    new_pages: list[dict] = []
    for p in fetched:
        url = p.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        p["summary"] = (p.get("summary") or p.get("snippet") or "")[:MAX_SUMMARY_CHARS]
        new_pages.append(p)

    new_pages = new_pages[:MAX_PAGES_PER_EXTRACT]
    print(f"  [searcher] 第 {iteration} 轮：关键词 {new_keywords!r}，新增页面 {len(new_pages)} 个")

    return {
        "iteration": iteration,
        "keywords": new_keywords,
        "new_pages": new_pages,
        "pages_read": new_pages,
        "rounds": [{"round": iteration, "keywords": new_keywords}],
    }
