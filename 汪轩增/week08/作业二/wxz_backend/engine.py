# -*- coding: utf-8 -*-
"""研究引擎：组合 agent/ 各角色的编排器（不是 agent，不参与 LLM 调用）。

控制流：规划（KeywordAgent）→ 逐关键词 web_search → 总结成一段正文并累积进 draft
（SummaryAgent）→ 判断补检（JudgeAgent，不足则新关键词进下一轮，最多 max_rounds 轮）
→ 收集来源 + 确定性计算置信度 → 报告（ReportAgent）产出结构化报告 + HTML。
"""
from __future__ import annotations

import inspect
import logging

from . import config, tools
from .agent import JudgeAgent, KeywordAgent, ReportAgent, SummaryAgent
from .models import (
    ConfidenceNote,
    DeepResearchResult,
    DraftBlock,
    ProcessStep,
    ResearchProcess,
    Source,
)

logger = logging.getLogger(__name__)


class DeepResearch:
    """研究引擎（编排器）：只做确定性控制流，不发起任何 LLM 调用。"""

    def __init__(self):
        self.keyword_agent = KeywordAgent()
        self.summary_agent = SummaryAgent()
        self.judge_agent = JudgeAgent()
        self.report_agent = ReportAgent()

    async def run(
        self,
        topic: str,
        max_rounds: int | None = None,
        on_progress=None,
    ) -> DeepResearchResult:
        max_rounds = max_rounds or config.MAX_ROUNDS
        process = ResearchProcess()
        sources: list[Source] = []
        seen_urls: set[str] = set()
        draft: list[DraftBlock] = []

        # 1. 规划
        keywords = await self.keyword_agent.generate_keywords(topic)
        process.plan = keywords
        process.steps.append(ProcessStep(type="plan", round=0, detail={"keywords": keywords}))
        logger.info("规划出 %d 个关键词: %s", len(keywords), keywords)
        await self._progress(on_progress, process, draft, sources)

        # 2. 循环：检索 → 阅读抽取 → 判断补检
        todo = list(keywords)
        round_no = 0
        while round_no < max_rounds:
            round_no += 1
            process.iterations = round_no
            logger.info("=== 第 %d/%d 轮 ===", round_no, max_rounds)

            for kw in todo:
                if kw in process.search_queries:
                    continue
                process.search_queries.append(kw)
                try:
                    results = await tools.web_search(kw)
                except Exception:
                    logger.exception("检索失败（关键词=%r），跳过继续", kw)
                    results = []
                self._collect_sources(results, sources, seen_urls, process)
                text = await self.summary_agent.summarize(topic, kw, results)
                draft.append(DraftBlock(round=round_no, keyword=kw, text=text))
                process.steps.append(
                    ProcessStep(type="summarize", round=round_no, detail={"keyword": kw, "chars": len(text)})
                )

            decision = await self.judge_agent.judge(topic, self._join_draft(draft), sources, process.search_queries)
            process.steps.append(ProcessStep(type="judge", round=round_no, detail=decision.model_dump()))
            await self._progress(on_progress, process, draft, sources)

            if decision.sufficient:
                logger.info("判断 sufficient，提前结束（第 %d 轮）", round_no)
                break
            todo = [k for k in decision.new_keywords if k not in process.search_queries]
            if not todo:
                break

        # 3. 置信度（确定性计算）
        confidence = self._compute_confidence(sources)

        # 4. 报告
        report, html = await self.report_agent.generate(topic, draft, sources, confidence)

        result = DeepResearchResult(
            report=report,
            report_html=html,
            sources=sources,
            draft=draft,
            process=process,
            confidence=confidence,
        )
        await self._progress(on_progress, process, draft, sources)
        logger.info("研究完成：%d 个来源，%d 轮迭代", len(sources), process.iterations)
        return result

    # ---- helpers ----

    @staticmethod
    def _collect_sources(results: list[dict], sources: list[Source], seen_urls: set[str], process: ResearchProcess) -> None:
        """把搜索结果里的新来源去重后收进来源列表，并登记到过程记录。"""
        for r in results:
            url = (r.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            process.reviewed_urls.append(url)
            sources.append(
                Source(
                    url=url,
                    title=r.get("title") or "",
                    site_name=r.get("site_name") or "",
                    snippet=r.get("snippet") or "",
                    date=r.get("date") or "",
                    accessed_at=config.today_str(),
                )
            )

    @staticmethod
    def _join_draft(draft: list[DraftBlock]) -> str:
        """把草稿段落拼成一段文本，供判断 agent 阅读。"""
        return "\n\n".join(f"【{d.keyword}】\n{d.text}" for d in draft)

    @staticmethod
    def _compute_confidence(sources: list[Source]) -> ConfidenceNote:
        """确定性计算置信度：来源数量 -> 可靠程度，最新来源日期 -> 信息截止时间。"""
        n = len(sources)
        overall = "high" if n >= 12 else "medium" if n >= 5 else "low"
        dates = [s.date for s in sources if s.date]
        info_cutoff = max(dates) if dates else config.today_str()
        notes = [
            f"共引用 {n} 个来源。",
            f"信息截止时间取来源最新发布日期 {info_cutoff}。",
            "未关联来源的结论已在报告中标注为「模型推断」。",
        ]
        return ConfidenceNote(overall=overall, info_cutoff=info_cutoff, notes=notes)

    async def _progress(self, on_progress, process: ResearchProcess, draft: list[DraftBlock], sources: list[Source]) -> None:
        """把中间结果回调出去（供上层落盘，实现过程可见）；回调支持同步或异步。"""
        if on_progress is None:
            return
        result = on_progress(
            {
                "process": process.model_dump(),
                "draft": [d.model_dump() for d in draft],
                "sources": [s.model_dump() for s in sources],
            }
        )
        if inspect.isawaitable(result):
            await result


if __name__ == "__main__":
    # 自检 demo：完整研究流水线（端到端，需要 .env 密钥与网络，人工验证用）
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    async def main():
        result = await DeepResearch().run("2026 年 AI Agent 开发框架对比")
        print("标题:", result.report.title)
        print("分节数:", len(result.report.sections))
        print("来源数:", len(result.sources))
        print("HTML 长度:", len(result.report_html))

    asyncio.run(main())
