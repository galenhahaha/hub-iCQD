"""请求/响应契约模型与领域 DTO。

本模块只描述数据结构，不含业务流程、不发 IO。
"""

from typing import List, Optional

from pydantic import BaseModel, Field, PrivateAttr


class ResearchRequest(BaseModel):
    """`POST /api/research` 的请求体。

    `topic` 默认空串：字段缺失时保持为空，由路由层统一判空并返回 400。
    `Optional` 是为了让显式传入的 `null` 也走 400 分支，而不是被 Pydantic 判为 422。
    """

    topic: Optional[str] = ""


class Section(BaseModel):
    """某个关键词的汇总结果。"""

    keyword: str
    content: str


class Source(BaseModel):
    """一条去重后的资料来源。"""

    title: str
    url: str


class RoundDetail(BaseModel):
    """一轮检索的执行记录（用于过程追溯）。"""

    round: int
    keywords: List[str] = Field(default_factory=list)


class ProcessInfo(BaseModel):
    """流程元信息：已执行轮次的关键词有序去重并集与实际执行轮数。

    `rounds_detail` 为新增的**可选**附加字段，用于暴露每轮关键词；
    既有字段 `keywords`（字符串数组）与 `rounds`（整数）的名称与类型保持不变。
    """

    keywords: List[str] = Field(default_factory=list)
    rounds: int = 0
    rounds_detail: Optional[List[RoundDetail]] = None


class SearchResult(BaseModel):
    """检索服务返回的单条结果（领域 DTO）。"""

    title: str
    url: str
    # 真实搜索服务的摘要只供 LLM 使用，不暴露到现有 API 契约中。
    _snippet: str = PrivateAttr(default="")

    @property
    def snippet(self) -> str:
        """真实搜索结果的摘要文本（Mock 结果为空）。"""
        return self._snippet


class ResearchResponse(BaseModel):
    """五段式研究报告契约：topic / summary / sections / sources / process。"""

    topic: str
    summary: str
    sections: List[Section] = Field(default_factory=list)
    sources: List[Source] = Field(default_factory=list)
    process: ProcessInfo = Field(default_factory=ProcessInfo)
