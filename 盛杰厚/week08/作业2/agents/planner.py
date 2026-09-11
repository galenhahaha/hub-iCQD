"""Planner 规划 Agent：把研究主题拆解为子问题 + 初版检索关键词。"""
from __future__ import annotations

from config import build_structured_llm
from state import ResearchPlan, ResearchState

_PLANNER_PROMPT = """你是一名资深市场研究员，负责把一个研究主题拆解成可独立检索的子问题。

要求：
1. 拆出 2~4 个互不重叠的子问题，尽量覆盖主题的不同维度（如市场规模、竞争格局、技术路线、政策、区域等）。
2. 每个子问题给出 2~3 个适合搜索引擎检索的中文关键词。
3. 只输出结构化结果，不要输出任何解释文字。

研究主题：{topic}
"""


def planner_node(state: ResearchState) -> dict:
    """langgraph 节点：规划，产出子问题与初版关键词。"""
    llm = build_structured_llm(ResearchPlan)
    prompt = _PLANNER_PROMPT.format(topic=state["topic"])
    plan: ResearchPlan = llm.invoke(prompt)

    sub_questions = [sq.text for sq in plan.sub_questions]
    keywords: list[str] = []
    for sq in plan.sub_questions:
        for kw in sq.keywords:
            if kw not in keywords:
                keywords.append(kw)

    return {
        "sub_questions": sub_questions,
        "keywords": keywords,
    }
