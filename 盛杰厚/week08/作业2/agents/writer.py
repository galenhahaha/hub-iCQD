"""Writer 综合 Agent：汇总证据，生成结构化研究报告（markdown）。

注：报告是自然语言产物，故直接用 LLM 生成 markdown（而非嵌套 Pydantic schema），
以避免网关在复杂嵌套 tool-call 下返回空对象；来源列表由下游确定性追加，保证可追溯。
"""
from __future__ import annotations

from config import build_llm
from state import ResearchState
from writers import build_sources, compact_evidence

_WRITER_PROMPT = """你是资深研究分析师。请基于已收集的证据，撰写一份结构化中文研究报告（直接输出 markdown）。

研究主题：{topic}

证据（每条含 claim / supports / source_url）：
{evidence}

编号来源列表（[n] 对应 source_id=n）：
{sources}

请严格按以下结构输出 markdown：

## 摘要
（3~5 句概括核心结论）

## {{分节标题一}}
正文……（关键事实后用 [n] 标注来源编号，如 [1]）

## {{分节标题二}}
正文……

## 关键结论
1. 结论一 —— 来源 [1][3]（高置信/中置信/低置信）
2. 结论二 —— 模型推断（无来源支撑）

## 遗留问题
- 未覆盖 / 信息不足的点

## 置信度说明
一段话说明：整体置信度、信息截止时间（据来源发布时间判断）、哪些结论是模型推断（无来源）。

硬性要求：
1. 只引用 sources 列表中实际存在的编号，不得虚构 [n]。
2. 无来源支撑的判断，必须在关键结论里标注「模型推断」。
3. 置信度：high=多来源交叉验证；medium=单一来源；low=来源二手/陈旧；inference=无来源。
4. 不要输出「## 来源列表」这一节（我会在后面自动追加）。
5. 直接输出 markdown 正文，不要任何前言或客套话。
"""


def writer_node(state: ResearchState) -> dict:
    # 先生成唯一编号来源列表，保证报告引用的编号稳定且可追溯
    sources = state.get("sources") or build_sources(state)
    evidence = compact_evidence(state.get("evidence", []))

    llm = build_llm(max_tokens=8192)
    prompt = _WRITER_PROMPT.format(
        topic=state.get("topic", ""),
        evidence=evidence,
        sources=sources,
    )

    report_md = ""
    for attempt in range(2):
        try:
            msg = llm.invoke(prompt)
            text = msg.text if hasattr(msg, "text") else str(getattr(msg, "content", ""))
            if text.strip():
                report_md = text.strip()
                break
        except Exception as exc:
            print(f"  [writer] 第 {attempt + 1} 次生成失败: {exc}")

    if not report_md:
        report_md = (
            "## 摘要\n（报告生成失败，请查看研究过程记录与来源列表）\n\n"
            "## 置信度说明\n（生成失败，无置信度说明）\n"
        )

    print("  [writer] 报告生成完成")
    return {"report": report_md, "sources": sources}
