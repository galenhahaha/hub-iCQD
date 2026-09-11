"""
接口数据模型（Pydantic v2）
==========================
用于 HTTP 请求的校验，以及 OpenAPI 自动文档中的类型说明。
任务结果本身是高度动态的 JSON，因此内部存 dict，仅在边界做必要约束。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatus(str, Enum):
    """任务生命周期状态机：pending → running → done / failed。"""

    PENDING = "pending"    # 已入队，等待执行
    RUNNING = "running"    # 深度研究进行中
    DONE = "done"          # 成功完成，result 可用
    FAILED = "failed"      # 执行失败，error 含原因


# ---------------------------------------------------------------------------
# 请求
# ---------------------------------------------------------------------------
class ResearchRequest(BaseModel):
    """提交一个深度研究任务所需的参数。"""

    # 忽略客户端多传的无关字段，避免把脏数据透传进引擎
    model_config = ConfigDict(extra="ignore")

    topic: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="研究主题，如：竞品分析 / 行业趋势 / 技术选型",
        examples=["2026 年国产大模型格局与头部厂商对比"],
    )
    max_rounds: Optional[int] = Field(
        None,
        ge=0,
        le=3,
        description="覆盖服务端默认配置：初始检索之外最多允许的智能补检轮数（0~3）",
    )
    results_per_query: Optional[int] = Field(
        None,
        ge=1,
        le=10,
        description="覆盖服务端默认配置：每个关键词返回几条搜索结果",
    )
    extra_instructions: str = Field(
        "",
        max_length=1000,
        description="补充要求：关注维度、目标读者、篇幅等，会一并交给模型",
    )

    @field_validator("topic")
    @classmethod
    def _strip_topic(cls, value: str) -> str:
        """去除首尾空白，避免空字符串主题。"""
        return value.strip()


# ---------------------------------------------------------------------------
# 轮询时的任务进度片段
# ---------------------------------------------------------------------------
class PhaseLog(BaseModel):
    """一条研究进展，供轮询接口实时返回。"""

    phase: str                       # 阶段名：开始/规划/检索/阅读/补检/综合/完成/失败
    message: str                     # 人类可读描述
    timestamp: str                   # ISO 8601
    round: Optional[int] = None      # 第几轮检索


# ---------------------------------------------------------------------------
# 轮询响应（task_id 对应的完整状态）
# ---------------------------------------------------------------------------
class TaskInfo(BaseModel):
    """GET /research/{task_id} 返回结构。"""

    model_config = ConfigDict(extra="allow")

    task_id: str
    topic: str
    status: TaskStatus
    created_at: str
    updated_at: str
    research_mode: Optional[str] = None     # full / offline
    phases: List[PhaseLog] = Field(default_factory=list)
    error: Optional[str] = None             # failed 时给出原因
    result: Optional[Any] = None            # done 后为结构化研究报告
