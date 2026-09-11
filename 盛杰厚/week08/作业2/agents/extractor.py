"""Extractor 抽取 Agent：阅读本轮新页面，抽取与子问题相关的证据。"""
from __future__ import annotations

from config import build_structured_llm
from state import ExtractResult, ResearchState

_EXTRACT_PROMPT = """你是研究资料抽取员。下面提供了若干网页的标题、来源与摘要，以及本次研究的子问题。

任务：从这些页面中抽取**可支撑子问题的事实/结论**作为证据。要求：
1. claim 须为陈述句，忠于原文，不得编造。
2. 每条证据都要带上 source_url（来自对应页面的 url）。
3. 与子问题无关、或信息价值低的内容，不要抽取。
4. 若页面信息不足以回答子问题，宁可少抽也不要臆造。
5. 只输出结构化结果。

研究子问题：
{sub_questions}

页面列表（JSON）：
{pages}
"""


def extractor_node(state: ResearchState) -> dict:
    pages = state.get("new_pages", [])
    if not pages:
        return {"evidence": []}

    sub_questions = state.get("sub_questions", [])
    llm = build_structured_llm(ExtractResult)
    prompt = _EXTRACT_PROMPT.format(sub_questions=sub_questions, pages=pages)
    result: ExtractResult = llm.invoke(prompt)

    evidence = [e.model_dump() for e in result.evidence]
    print(f"  [extractor] 抽取证据 {len(evidence)} 条")
    return {"evidence": evidence}
