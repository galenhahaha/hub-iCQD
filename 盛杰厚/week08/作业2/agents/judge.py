"""Judge 判定 Agent：判断信息是否充分，决定补检方向。"""
from __future__ import annotations

from config import build_structured_llm
from state import ResearchState, Verdict
from writers import compact_evidence

_JUDGE_PROMPT = """你是研究质量评估员。根据当前已收集的证据，判断是否还需要补充检索。

研究主题：{topic}
子问题：
{sub_questions}

已收集证据（每条含 claim / supports / source_url）：
{evidence}

已检索过的关键词：{searched}

判断规则：
- 若关键子问题证据明显不足（缺数据、来源单一、覆盖不全），返回 need_more=true，并给出新的补充检索关键词。
- 若信息已基本充分，返回 need_more=false，new_keywords 留空。
- 只输出结构化结果。
"""


def judge_node(state: ResearchState) -> dict:
    llm = build_structured_llm(Verdict)
    prompt = _JUDGE_PROMPT.format(
        topic=state.get("topic", ""),
        sub_questions=state.get("sub_questions", []),
        evidence=compact_evidence(state.get("evidence", [])),
        searched=state.get("search_history", []),
    )
    verdict: Verdict = llm.invoke(prompt)

    print(f"  [judge] need_more={verdict.need_more}  new_keywords={verdict.new_keywords!r}")
    return {
        "need_more": verdict.need_more,
        "keywords": verdict.new_keywords if verdict.need_more else [],
    }
