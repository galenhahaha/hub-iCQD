"""共享状态（langgraph）与各 Agent 的结构化输出 Schema。"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


# ---------- Agent 输出 Schema（structured output） ----------

class SubQuestion(BaseModel):
    """Planner 拆解出的一个子问题。"""
    text: str = Field(description="子问题")
    keywords: list[str] = Field(description="该子问题的检索关键词")


class ResearchPlan(BaseModel):
    """Planner 输出：子问题列表 + 初版关键词。"""
    sub_questions: list[SubQuestion] = Field(description="拆解出的子问题列表")


class ExtractedEvidence(BaseModel):
    """Extractor 从单个页面抽取的一条证据。"""
    claim: str = Field(description="从来源页面中抽取到的事实/结论，须为陈述句")
    source_url: str = Field(description="支撑该事实的来源页面 URL")
    supports: str = Field(description="该证据对应/支撑的子问题或主题")


class ExtractResult(BaseModel):
    """Extractor 输出：本轮新页面抽取出的证据列表。"""
    evidence: list[ExtractedEvidence] = Field(default_factory=list)


class Verdict(BaseModel):
    """Judge 输出：是否补检 + 补充关键词。"""
    need_more: bool = Field(description="是否还需要补充检索")
    reasoning: str = Field(description="判断理由（简短）")
    new_keywords: list[str] = Field(default_factory=list, description="补充检索关键词")


class ReportSection(BaseModel):
    """报告的一个分节。"""
    heading: str = Field(description="分节标题")
    body: str = Field(description="正文（markdown），关键事实后标注来源编号 [n]")


class Conclusion(BaseModel):
    """一条关键结论，含来源编号与置信度。"""
    statement: str = Field(description="关键结论")
    sources: list[int] = Field(default_factory=list, description="支撑该结论的来源编号列表")
    confidence: Literal["high", "medium", "low", "inference"] = Field(description="置信度")


class Report(BaseModel):
    """Writer 输出的结构化研究报告。"""
    summary: str = Field(description="摘要，3~5 句")
    sections: list[ReportSection] = Field(description="分节正文")
    key_conclusions: list[Conclusion] = Field(description="关键结论")
    open_questions: list[str] = Field(default_factory=list, description="遗留问题")
    confidence_notes: str = Field(description="置信度说明（含哪些结论为模型推断）")


# ---------- 共享状态（langgraph） ----------

def _concat(a: list, b: list) -> list:
    """list 字段的累加 reducer：跨轮次不断追加。"""
    return (a or []) + (b or [])


class ResearchState(TypedDict, total=False):
    topic: str
    sub_questions: list[str]
    keywords: list[str]                        # 当前轮待检索关键词（每轮覆盖）
    search_history: Annotated[list[str], _concat]   # 已检索关键词（去重用）
    pages_read: Annotated[list[dict], _concat]      # 去重后的已读页面
    new_pages: list[dict]                      # 本轮新增页面（供抽取 Agent）
    rounds: Annotated[list[dict], _concat]     # 每轮检索记录 [{round, keywords}]
    evidence: Annotated[list[dict], _concat]   # 已抽取证据
    iteration: int                             # 当前轮数
    max_iterations: int
    need_more: bool
    sources: list[dict]                        # 编号来源列表（确定性生成）
    report: str                                # 最终报告（markdown）
