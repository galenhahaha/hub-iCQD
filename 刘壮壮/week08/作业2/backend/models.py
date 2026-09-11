"""研究任务、四类产物，以及 LLM 中间 JSON 结构。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ResearchStatus = Literal["pending", "running", "completed", "failed"]
StepKind = Literal["plan", "search", "extract", "judge", "synthesize"]


class Source(BaseModel):
    id: str
    title: str
    url: str
    snippet: str = ""
    site_name: str = ""
    published: str = ""


class Conclusion(BaseModel):
    text: str
    source_ids: list[str] = Field(default_factory=list)
    inferred: bool = False


class ReportSection(BaseModel):
    heading: str
    body: str
    source_ids: list[str] = Field(default_factory=list)


class Report(BaseModel):
    title: str = ""
    summary: str = ""
    sections: list[ReportSection] = Field(default_factory=list)
    key_conclusions: list[Conclusion] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ReviewedItem(BaseModel):
    title: str
    url: str
    query: str = ""


class ProcessStep(BaseModel):
    kind: StepKind
    round: int = 0
    title: str
    detail: str = ""
    at: str = ""


class ResearchProcess(BaseModel):
    queries: list[str] = Field(default_factory=list)
    reviewed: list[ReviewedItem] = Field(default_factory=list)
    iterations: int = 0
    steps: list[ProcessStep] = Field(default_factory=list)


class Confidence(BaseModel):
    level: Literal["high", "medium", "low"] = "medium"
    as_of: str = ""
    rationale: str = ""
    inferred_count: int = 0


class ResearchRecord(BaseModel):
    id: str
    topic: str
    status: ResearchStatus = "pending"
    created_at: str
    updated_at: str
    error: Optional[str] = None
    draft: str = ""
    report: Optional[Report] = None
    sources: list[Source] = Field(default_factory=list)
    process: ResearchProcess = Field(default_factory=ResearchProcess)
    confidence: Optional[Confidence] = None


class ResearchCreate(BaseModel):
    topic: str


class ResearchCreated(BaseModel):
    id: str
    status: ResearchStatus
    topic: str


class ResearchSummary(BaseModel):
    id: str
    topic: str
    status: ResearchStatus
    created_at: str
    updated_at: str


class PlanOutput(BaseModel):
    sub_questions: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ExtractOutput(BaseModel):
    facts: list[str] = Field(default_factory=list)
    paragraph: str = ""


class JudgeOutput(BaseModel):
    sufficient: bool
    reason: str = ""
    missing: list[str] = Field(default_factory=list)
    extra_keywords: list[str] = Field(default_factory=list)


class ReportOutput(BaseModel):
    title: str
    summary: str
    sections: list[ReportSection] = Field(default_factory=list)
    key_conclusions: list[Conclusion] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence_level: Literal["high", "medium", "low"] = "medium"
    confidence_rationale: str = ""


if __name__ == "__main__":
    rec = ResearchRecord(
        id="demo",
        topic="示例主题",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    dumped = rec.model_dump()
    assert dumped["status"] == "pending"
    parsed = PlanOutput.model_validate({"keywords": ["a"], "sub_questions": ["q"]})
    print("ok", rec.id, parsed.keywords)
