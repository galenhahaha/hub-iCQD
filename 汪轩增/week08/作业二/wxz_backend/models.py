# -*- coding: utf-8 -*-
"""研究请求 / 报告 / 来源 / 过程 / 置信度 / 落盘记录的 Pydantic 模型。

对应产品规格的四类产物，外加研究流水线的中间结果：
- report / report_html  结构化报告 + HTML 版
- sources     来源列表（每条结论关联 URL / 标题，可追溯）
- process     研究过程记录（检索关键词、读过页面、迭代轮数、每步中间结果）
- draft       报告正文草稿（每个关键词检索内容总结出的段落，直接累积成正文）
- confidence  置信度说明（可靠程度、信息截止时间；无来源结论标注「模型推断」）
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Status(str, Enum):
    """研究任务状态。"""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ResearchRequest(BaseModel):
    """发起一次研究的请求体。"""

    topic: str = Field(..., min_length=1, max_length=500, description="研究主题")


class SourceRef(BaseModel):
    """一条结论关联的一个来源引用。"""

    url: str
    title: str = ""


class Conclusion(BaseModel):
    """一条结论；无来源支撑的结论 is_model_inference 必须为 True。"""

    text: str
    sources: list[SourceRef] = []
    is_model_inference: bool = False


class Section(BaseModel):
    """报告正文的一个分节（heading + body）。"""

    heading: str
    body: str


class ConfidenceNote(BaseModel):
    """置信度说明。"""

    overall: str = "medium"  # high / medium / low
    info_cutoff: str = ""    # 信息截止时间（来源最新发布日期）
    notes: list[str] = []


class ReportContent(BaseModel):
    """结构化研究报告（ReportOutline 元信息 + 草稿段落映射的分节正文）。"""

    title: str
    summary: str
    sections: list[Section]
    key_conclusions: list[Conclusion] = []
    open_questions: list[str] = []


class Source(BaseModel):
    """来源列表条目（含抓取信息，可追溯）。"""

    url: str
    title: str = ""
    site_name: str = ""
    snippet: str = ""
    date: str = ""         # 来源发布日期（来自搜索结果）
    accessed_at: str = ""  # 本次检索时间


class DraftBlock(BaseModel):
    """一个关键词检索内容总结出的报告正文段落（中间产物，直接累积成报告正文）。"""

    round: int = 0
    keyword: str
    text: str


class ProcessStep(BaseModel):
    """研究过程中一步的中间结果记录。"""

    type: str  # plan / search / summarize / judge
    round: int = 0
    detail: dict[str, Any] = {}


class ResearchProcess(BaseModel):
    """研究过程记录（由研究引擎逐步累积）。"""

    plan: list[str] = []          # 规划出的初始关键词
    search_queries: list[str] = []  # 实际检索过的全部关键词
    reviewed_urls: list[str] = []   # 搜索结果里使用过的来源 URL（去重）
    iterations: int = 0             # 检索/判断轮数
    steps: list[ProcessStep] = []   # 每步中间结果


class ResearchRecord(BaseModel):
    """最终落盘 / 返回的完整对象。"""

    research_id: str
    topic: str
    status: Status
    created_at: str
    updated_at: str
    error: str | None = None
    report: ReportContent | None = None
    report_html: str = ""          # 渲染好的自包含 HTML 报告
    sources: list[Source] = []
    draft: list[DraftBlock] = []   # 报告正文草稿（中间结果，逐步累积）
    process: ResearchProcess | None = None
    confidence: ConfidenceNote | None = None


# --- 中间产物（LLM 结构化输出，仅用于流水线内部）---

class KeywordOutput(BaseModel):
    """关键词 agent 的输出结构。"""

    keywords: list[str] = []


class JudgeDecision(BaseModel):
    """判断 agent 的决策。"""

    sufficient: bool = False
    reason: str = ""
    new_keywords: list[str] = []


class ReportOutline(BaseModel):
    """报告 agent 第一次调用（元信息）的输出。

    正文分节（sections）由草稿段落直接映射（heading=keyword、body=text），
    不走 LLM 重新组织；LLM 只补充标题、摘要、关键结论与遗留问题。
    """

    title: str
    summary: str
    key_conclusions: list[Conclusion] = []
    open_questions: list[str] = []


class DeepResearchResult(BaseModel):
    """研究引擎 run() 返回的完整结果。"""

    report: ReportContent
    report_html: str
    sources: list[Source]
    draft: list[DraftBlock]
    process: ResearchProcess
    confidence: ConfidenceNote


if __name__ == "__main__":
    # 自检 demo：构造一条完整研究记录并验证序列化往返（纯本地，不联网）
    req = ResearchRequest(topic="竞品分析：2026 年主流 Agent 框架")
    print("ResearchRequest:", req.model_dump())

    report = ReportContent(
        title="2026 年主流 Agent 框架对比",
        summary="对 OpenAI Agents SDK 与 LangGraph 等的对比。",
        sections=[Section(heading="OpenAI Agents SDK", body="轻量级多 agent 框架。")],
        key_conclusions=[
            Conclusion(text="各有侧重。", sources=[SourceRef(url="https://example.com/x", title="示例")]),
            Conclusion(text="未来趋于标准化。（模型推断）", is_model_inference=True),
        ],
        open_questions=["未来趋势如何？"],
    )

    rec = ResearchRecord(
        research_id="demo-id",
        topic=req.topic,
        status=Status.running,
        created_at="2026-09-10T00:00:00+00:00",
        updated_at="2026-09-10T00:00:00+00:00",
        report=report,
        report_html="<html>...</html>",
        sources=[Source(url="https://example.com/x", title="示例", date="2026-09-01", accessed_at="2026-09-10")],
        draft=[DraftBlock(round=1, keyword="OpenAI Agents SDK", text="OpenAI Agents SDK 是轻量级多 agent 框架。")],
        process=ResearchProcess(plan=["OpenAI Agents SDK"], search_queries=["OpenAI Agents SDK"], iterations=1),
        confidence=ConfidenceNote(overall="medium", info_cutoff="2026-09-01", notes=["来源有限。"]),
    )

    dumped = rec.model_dump_json(indent=2, ensure_ascii=False)
    assert len(dumped) > 100
    back = ResearchRecord.model_validate_json(dumped)
    assert back.research_id == "demo-id"
    assert back.report is not None and back.report.key_conclusions[1].is_model_inference is True
    print("ResearchRecord 序列化->反序列化 OK，字段数 =", len(back.model_dump()))
    print("models 自检 OK")
