"""Pydantic v2 contracts for research inputs, progress, and results."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Status(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)

    @field_validator("topic", mode="before")
    @classmethod
    def strip_topic(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class ResearchAccepted(BaseModel):
    research_id: str
    status: Literal["pending"] = "pending"


class SourceRef(BaseModel):
    url: str
    title: str = ""


class JudgeDecision(BaseModel):
    sufficient: bool = False
    reason: str = ""
    new_keywords: list[str] = Field(default_factory=list)


class KeywordOutput(BaseModel):
    keywords: list[str]


class DraftBlock(BaseModel):
    round: int
    keyword: str
    text: str


class ProcessStep(BaseModel):
    type: str  # plan / search / summarize / judge
    round: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


class Conclusion(BaseModel):
    text: str
    sources: list[SourceRef] = Field(default_factory=list)
    is_model_inference: bool = False


class Section(BaseModel):
    heading: str
    body: str
    conclusions: list[Conclusion] = Field(default_factory=list)


class ConfidenceNote(BaseModel):
    overall: str = "medium"  # high / medium / low
    info_cutoff: str = ""
    notes: list[str] = Field(default_factory=list)


class ReportContent(BaseModel):
    title: str
    summary: str
    sections: list[Section]
    key_conclusions: list[Conclusion]
    open_questions: list[str] = Field(default_factory=list)


class ReportOutline(BaseModel):
    title: str
    summary: str
    key_conclusions: list[Conclusion] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class Source(BaseModel):
    url: str
    title: str = ""
    site_name: str = ""
    snippet: str = ""
    accessed_at: str = ""


class ResearchProcess(BaseModel):
    plan: list[str]
    search_queries: list[str]
    reviewed_urls: list[str]
    iterations: int = 0
    steps: list[ProcessStep] = Field(default_factory=list)


class ResearchRecord(BaseModel):
    research_id: str
    topic: str
    status: Status
    created_at: str
    updated_at: str
    error: str | None = None
    report: ReportContent | None = None
    report_html: str = ""
    sources: list[Source] = Field(default_factory=list)
    draft: list[DraftBlock] = Field(default_factory=list)
    process: ResearchProcess | None = None
    confidence: ConfidenceNote | None = None


class DeepResearchResult(BaseModel):
    report: ReportContent
    report_html: str
    sources: list[Source]
    draft: list[DraftBlock]
    process: ResearchProcess
    confidence: ConfidenceNote
