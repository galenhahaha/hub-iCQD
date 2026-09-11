"""ResearchEngine：研究流程的唯一编排者。

- Workflow 控制（顺序、轮次上限、何时停）全部集中在 `run()`；
- Agent 式判断（资料够不够、要不要补一轮）集中在 `is_sufficient()`；
- 检索能力通过构造函数注入的 `SearchService` 获得，引擎不感知具体实现。
"""

import logging
from typing import Dict, List, Optional, Sequence, Tuple

from app.models import (
    ProcessInfo,
    ResearchResponse,
    RoundDetail,
    SearchResult,
    Section,
    Source,
)
from app.llm import LLMError, LLMService
from app.services import SearchError, SearchService

logger = logging.getLogger(__name__)

#: 检索轮数的**绝对上限**（不可被配置突破），同时作为构造函数默认值。
#: 构造参数 `max_rounds` 只可**调低**（用于测试单轮路径），调高（`max_rounds > MAX_ROUNDS`）
#: 在构造期即抛 `ValueError`。轮次上限本身仍由 `range(self._max_rounds)` 在结构上保证。
MAX_ROUNDS = 2

#: 充分性判断的默认来源数阈值。
SUFFICIENCY_THRESHOLD = 2

#: 第二轮补检索关键词的派生后缀。
_FOLLOW_UP_SUFFIX = " 深入"


class ResearchEngine:
    """按"生成关键词 → 检索 → 汇总 → 判断充分性"四步编排研究流程。"""

    def __init__(self, search_service: SearchService, *,
                 max_rounds: int = MAX_ROUNDS,
                 sufficiency_threshold: int = SUFFICIENCY_THRESHOLD,
                 llm_service: Optional[LLMService] = None) -> None:
        """注入检索能力并校验构造参数。

        `MAX_ROUNDS` 是不可突破的绝对上限：`max_rounds` 只可调低、调高即构造期拒绝。
        非法取值（非整数、`< 1`、`> MAX_ROUNDS`）一律在构造期抛 `ValueError`，
        不推迟到 `run()`，且不会产生任何检索调用。
        """
        if not isinstance(max_rounds, int):
            raise ValueError(
                "max_rounds 必须为整数，实际为 {0!r}".format(max_rounds)
            )
        if max_rounds < 1:
            raise ValueError("max_rounds 必须 >= 1，实际为 {0}".format(max_rounds))
        if max_rounds > MAX_ROUNDS:
            raise ValueError(
                "max_rounds 不得超过上限 {0}（该上限不可被配置突破），"
                "实际为 {1}".format(MAX_ROUNDS, max_rounds)
            )
        self._search_service = search_service
        self._max_rounds = max_rounds
        self._sufficiency_threshold = sufficiency_threshold
        self._llm_service = llm_service

    # ------------------------------------------------------------------ #
    # 职责 1：关键词生成
    # ------------------------------------------------------------------ #
    def generate_keywords(self, topic: str, round_index: int = 0,
                          previous: Optional[Sequence[str]] = None) -> List[str]:
        """依据主题生成检索关键词；同一输入永远得到同一序列。

        第一轮直接由主题派生；后续轮次在上一轮关键词基础上追加限定词，
        使补检索既能针对资料缺口、又保持确定性。
        """
        base = (topic or "").strip()
        if not base:
            return []

        if round_index <= 0:
            return [base, "{0} 对比".format(base)]

        seeds = [item for item in (previous or []) if item and item.strip()]
        if not seeds:
            seeds = [base]
        keywords: List[str] = []
        for seed in seeds[:2]:
            candidate = "{0}{1}".format(seed, _FOLLOW_UP_SUFFIX)
            if candidate not in keywords:
                keywords.append(candidate)
        return keywords

    # ------------------------------------------------------------------ #
    # 职责 2：检索（委托 + 容错降级）
    # ------------------------------------------------------------------ #
    async def search(self, keyword: str) -> List[SearchResult]:
        """委托注入的检索服务；任何异常都降级为空结果，绝不让流程崩溃。"""
        try:
            results = await self._search_service.search(keyword)
        except SearchError as exc:
            logger.warning("检索失败，跳过关键词 %r：%s", keyword, exc)
            return []
        except Exception:
            # 兜底：把"失败不崩溃"这条硬约束收敛在唯一一处。
            logger.exception("检索关键词 %r 时发生未预期异常，降级为空结果", keyword)
            return []
        return list(results or [])

    # ------------------------------------------------------------------ #
    # 职责 3：结果汇总
    # ------------------------------------------------------------------ #
    def summarize(self, keyword: str, results: Sequence[SearchResult]) -> str:
        """整理某个关键词的检索结果；无结果时返回空串（表示该关键词无可用资料）。"""
        if not results:
            return ""
        titles = [item.title for item in results if item.title]
        joined = "、".join(titles) if titles else "无标题资料"
        return "围绕「{0}」检索到 {1} 条资料，主要来源：{2}。".format(
            keyword, len(results), joined
        )

    # ------------------------------------------------------------------ #
    # 职责 4：Agent 式判断（流程中唯一的决策点）
    # ------------------------------------------------------------------ #
    def is_sufficient(self, sections: Sequence[Section],
                      sources: Sequence[Source]) -> bool:
        """判断现有资料是否足够：至少一个非空 section 且去重来源数达到阈值。

        只依据传入的汇总结果判断，不读取流程累积状态（阈值来自构造配置
        `sufficiency_threshold`），因此可脱离流程单测。
        """
        has_content = any(
            section.content and section.content.strip() for section in sections
        )
        unique_urls = {source.url for source in sources}
        return has_content and len(unique_urls) >= self._sufficiency_threshold

    # ------------------------------------------------------------------ #
    # Workflow 控制：唯一编排入口
    # ------------------------------------------------------------------ #
    async def run(self, topic: str) -> ResearchResponse:
        """执行研究流程并组装五段式报告。"""
        normalized_topic = (topic or "").strip()
        rounds_detail: List[RoundDetail] = []
        sections: List[Section] = []
        ordered_keywords: List[str] = []
        seen_keywords = set()
        seen_urls: Dict[str, Source] = {}  # 保序去重：首次出现者胜出

        # 轮次上限由 range 对象在进入循环前固定，物理上不可能出现第三轮。
        for round_index in range(self._max_rounds):
            previous_keywords = list(ordered_keywords)
            keywords = await self._generate_keywords(
                normalized_topic, round_index, previous_keywords
            )
            if not keywords:
                logger.info("第 %d 轮未生成关键词，提前结束", round_index + 1)
                break

            for keyword in keywords:
                if keyword not in seen_keywords:
                    seen_keywords.add(keyword)
                    ordered_keywords.append(keyword)

            round_sources: List[SearchResult] = []
            keyword_counts: List[Tuple[str, int]] = []
            for keyword in keywords:
                results = await self.search(keyword)
                keyword_counts.append((keyword, len(results)))
                summary_text = await self._summarize(
                    normalized_topic, keyword, results
                )
                if summary_text:
                    sections.append(Section(keyword=keyword, content=summary_text))
                else:
                    logger.info(
                        "round=%d keyword=%r results=0 无可用资料，跳过其汇总条目",
                        round_index + 1, keyword,
                    )
                round_sources.extend(results)

            for item in round_sources:
                seen_urls.setdefault(item.url, Source(title=item.title, url=item.url))

            rounds_detail.append(RoundDetail(round=round_index + 1,
                                             keywords=list(keywords)))
            logger.info("round=%d keywords=%s", round_index + 1, keywords)
            for keyword, count in keyword_counts:
                logger.info("round=%d keyword=%r results=%d",
                            round_index + 1, keyword, count)
            logger.info(
                "round=%d done sections=%d unique_sources=%d",
                round_index + 1, len(sections), len(seen_urls),
            )

            if await self._is_sufficient(
                normalized_topic, sections, list(seen_urls.values())
            ):
                logger.info("round=%d sufficient=true 停止检索", round_index + 1)
                break

        sources = list(seen_urls.values())
        summary = await self._generate_summary(
            normalized_topic, sections, list(seen_urls.values()), len(rounds_detail)
        )
        return ResearchResponse(
            topic=normalized_topic,
            summary=summary,
            sections=sections,
            sources=sources,
            process=ProcessInfo(
                keywords=ordered_keywords,
                rounds=len(rounds_detail),
                rounds_detail=rounds_detail,
            ),
        )

    async def _generate_keywords(self, topic: str, round_index: int,
                                 previous: Sequence[str]) -> List[str]:
        if self._llm_service is None:
            return self.generate_keywords(topic, round_index, previous)
        try:
            return await self._llm_service.generate_keywords(topic, round_index, previous)
        except LLMError as exc:
            logger.warning("LLM 关键词生成失败，回退本地规则：%s", exc)
            return self.generate_keywords(topic, round_index, previous)

    async def _summarize(self, topic: str, keyword: str,
                         results: Sequence[SearchResult]) -> str:
        if not results:
            return ""
        if self._llm_service is None:
            return self.summarize(keyword, results)
        try:
            return await self._llm_service.summarize(
                topic,
                keyword,
                [
                    {"title": item.title, "url": item.url, "snippet": item.snippet}
                    for item in results
                ],
            )
        except LLMError as exc:
            logger.warning("LLM 总结失败，回退本地规则 keyword=%r：%s", keyword, exc)
            return self.summarize(keyword, results)

    async def _is_sufficient(self, topic: str, sections: Sequence[Section],
                             sources: Sequence[Source]) -> bool:
        if self._llm_service is None:
            return self.is_sufficient(sections, sources)
        try:
            return await self._llm_service.is_sufficient(
                topic,
                [section.model_dump() for section in sections],
                [source.model_dump() for source in sources],
            )
        except LLMError as exc:
            logger.warning("LLM 充分性判断失败，回退阈值规则：%s", exc)
            return self.is_sufficient(sections, sources)

    async def _generate_summary(self, topic: str, sections: Sequence[Section],
                                sources: Sequence[Source], rounds: int) -> str:
        if self._llm_service is None or not sections:
            return self._build_summary(topic, sections, sources, rounds)
        try:
            return await self._llm_service.generate_summary(
                topic,
                [section.model_dump() for section in sections],
                [source.model_dump() for source in sources],
                rounds,
            )
        except LLMError as exc:
            logger.warning("LLM 报告摘要失败，回退本地规则：%s", exc)
            return self._build_summary(topic, sections, sources, rounds)

    @staticmethod
    def _build_summary(topic: str, sections: Sequence[Section],
                       sources: Sequence[Source], rounds: int) -> str:
        """生成说明性摘要；资料为空时明确说明资料不足。"""
        if not sections:
            return (
                "针对「{0}」的检索未获得可用资料，资料不足，"
                "未能形成有效研究结论（共执行 {1} 轮检索）。".format(topic, rounds)
            )
        covered = "、".join(section.keyword for section in sections)
        return (
            "围绕「{0}」共执行 {1} 轮检索，汇总 {2} 个关键词的资料，"
            "去重后得到 {3} 条来源。覆盖关键词：{4}。".format(
                topic, rounds, len(sections), len(sources), covered
            )
        )
