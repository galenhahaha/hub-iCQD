"""Test deterministic orchestration without LLM calls or network requests."""

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from backend import config, storage, tools
from backend.engine import DeepResearch, _compute_confidence
from backend.models import (
    DraftBlock,
    JudgeDecision,
    ReportContent,
    ResearchProcess,
    Section,
    Source,
    Status,
)


def result(url, title="来源", date="2026-09-01"):
    return {"url": url, "title": title, "snippet": "摘要", "site_name": "站点", "date": date}


class ConfidenceTests(unittest.TestCase):
    def test_all_threshold_boundaries(self) -> None:
        for count, expected in ((0, "low"), (4, "low"), (5, "medium"), (11, "medium"), (12, "high"), (13, "high")):
            with self.subTest(count=count):
                sources = [Source(url=f"https://example.com/{i}") for i in range(count)]
                with patch.object(config, "today_str", return_value="2026-09-08"):
                    confidence = _compute_confidence(sources, [], [])
                self.assertEqual(confidence.overall, expected)
                self.assertEqual(confidence.info_cutoff, "2026-09-08")
                self.assertIn("模型推断", "".join(confidence.notes))

    def test_repeated_sources_do_not_inflate_confidence(self) -> None:
        self.assertEqual(_compute_confidence([Source(url="https://example.com")] * 12, [], []).overall, "low")

    def test_latest_valid_source_date(self) -> None:
        dates = ["2026-01-01", "2026-09-02T15:30:00+08:00", "2026-08-31", "unknown", "2026-02-30", ""]
        self.assertEqual(_compute_confidence([], [], dates).info_cutoff, "2026-09-02")

    def test_invalid_dates_fall_back_to_today(self) -> None:
        with patch.object(config, "today_str", return_value="2026-09-08"):
            confidence = _compute_confidence([], [], ["invalid", "2026-99-99"])
        self.assertEqual(confidence.info_cutoff, "2026-09-08")
        self.assertIn("代替", "".join(confidence.notes))


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch("backend.agent.base.Runner.run", side_effect=AssertionError("LLM forbidden")))
        self.enterContext(patch.object(config, "today_str", return_value="2026-09-08"))
        self.search = self.enterContext(patch.object(tools, "web_search", new_callable=AsyncMock))
        self.search.return_value = []
        self.engine = DeepResearch("研究主题")
        self.engine.keyword_agent.generate_keywords = AsyncMock(return_value=["初始词"])
        self.engine.summary_agent.summarize = AsyncMock(side_effect=lambda topic, kw, results: f"{kw}正文")
        self.engine.judge_agent.judge = AsyncMock(return_value=JudgeDecision(sufficient=True))

        async def report(topic, draft, sources, confidence):
            return ReportContent(
                title=topic, summary="摘要", key_conclusions=[],
                sections=[Section(heading=b.keyword, body=b.text) for b in draft],
            ), "<!DOCTYPE html><html></html>"

        self.engine.report_agent.generate = AsyncMock(side_effect=report)

    async def test_empty_plan_and_search_still_produce_result(self) -> None:
        self.engine.keyword_agent.generate_keywords.return_value = []
        snapshots = []
        output = await self.engine.run(on_progress=snapshots.append)
        self.search.assert_awaited_once_with("研究主题")
        self.assertEqual(output.sources, [])
        self.assertEqual(output.process.plan, ["研究主题"])
        self.assertEqual(output.process.reviewed_urls, [])
        self.assertEqual(output.process.iterations, 1)
        self.assertEqual(output.confidence.overall, "low")
        self.assertEqual(output.draft[0].text, "研究主题正文")
        self.assertEqual([s.type for s in output.process.steps], ["plan", "search", "summarize", "judge"])
        self.assertEqual(snapshots[0]["draft"], [])
        self.assertEqual(snapshots[-1]["process"], output.process.model_dump())

    async def test_search_exception_is_recorded_and_nonfatal(self) -> None:
        self.search.side_effect = RuntimeError("test failure")
        with self.assertLogs("backend.engine", level="WARNING"):
            output = await self.engine.run()
        self.engine.summary_agent.summarize.assert_awaited_once_with("研究主题", "初始词", [])
        self.assertEqual(output.sources, [])
        self.assertIn("RuntimeError", output.process.steps[1].detail["error"])
        self.engine.report_agent.generate.assert_awaited_once()

    async def test_keywords_and_sources_accumulate_without_duplicates(self) -> None:
        self.engine.keyword_agent.generate_keywords.return_value = [" 甲 ", "甲", "乙", ""]
        self.search.side_effect = [
            [result(" https://example.com/a ", "最初标题"), result("https://example.com/a"), result("", date="2099-01-01")],
            [result("https://example.com/a", "重复标题"), result("https://example.com/b")],
            [result("https://example.com/b", date="2026-09-03"), result("https://example.com/c")],
        ]
        self.engine.judge_agent.judge.side_effect = [
            JudgeDecision(sufficient=False, new_keywords=["甲", " 丙 ", "丙", ""]),
            JudgeDecision(sufficient=True),
        ]
        output = await self.engine.run()
        self.assertEqual([c.args[0] for c in self.search.await_args_list], ["甲", "乙", "丙"])
        self.assertEqual(output.process.plan, ["甲", "乙"])
        self.assertEqual(output.process.search_queries, ["甲", "乙", "丙"])
        self.assertEqual(output.process.iterations, 2)
        self.assertEqual([b.round for b in output.draft], [1, 1, 2])
        self.assertEqual([s.url for s in output.sources], [f"https://example.com/{x}" for x in "abc"])
        self.assertEqual(output.process.reviewed_urls, [s.url for s in output.sources])
        self.assertEqual(output.sources[0].title, "最初标题")
        self.assertTrue(all(s.accessed_at == "2026-09-08" for s in output.sources))
        self.assertEqual(output.confidence.info_cutoff, "2026-09-03")
        judge_calls = self.engine.judge_agent.judge.await_args_list
        self.assertEqual(len(judge_calls), 2)
        self.assertIn("甲正文", judge_calls[0].args[1])
        self.assertIn("乙正文", judge_calls[0].args[1])
        self.assertEqual(judge_calls[0].args[3], ["甲", "乙"])

    async def test_sufficient_stops_even_with_new_keywords(self) -> None:
        self.engine.judge_agent.judge.return_value = JudgeDecision(sufficient=True, new_keywords=["不应检索"])
        self.assertEqual((await self.engine.run()).process.iterations, 1)
        self.search.assert_awaited_once()

    async def test_no_new_keywords_stops_without_empty_round(self) -> None:
        for keywords in ([], ["初始词", " 初始词 ", ""]):
            with self.subTest(keywords=keywords):
                self.search.reset_mock()
                self.engine.judge_agent.judge.return_value = JudgeDecision(new_keywords=keywords)
                self.assertEqual((await self.engine.run()).process.iterations, 1)
                self.search.assert_awaited_once()

    async def test_round_limit_is_enforced(self) -> None:
        self.engine.judge_agent.judge.side_effect = [JudgeDecision(new_keywords=[f"补检{i}"]) for i in range(3)]
        output = await self.engine.run(max_rounds=2)
        self.assertEqual(output.process.iterations, 2)
        self.assertEqual(output.process.search_queries, ["初始词", "补检0"])
        self.assertEqual(self.engine.judge_agent.judge.await_count, 2)

    async def test_default_round_limit_uses_configuration(self) -> None:
        self.engine.judge_agent.judge.return_value = JudgeDecision(new_keywords=["补检"])
        with patch.object(config, "MAX_ROUNDS", 1):
            self.assertEqual((await self.engine.run()).process.iterations, 1)
        self.search.assert_awaited_once()

    async def test_invalid_round_limit_fails_before_calls(self) -> None:
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                await self.engine.run(max_rounds=limit)
        self.engine.keyword_agent.generate_keywords.assert_not_awaited()
        self.search.assert_not_awaited()

    async def test_async_callback_and_snapshots_are_independent(self) -> None:
        snapshots = []

        async def callback(snapshot):
            snapshots.append(snapshot)
            snapshot["process"]["plan"].append("外部修改")
            snapshot["process"]["steps"][0]["detail"]["keywords"].clear()

        output = await self.engine.run(on_progress=callback)
        self.assertEqual(len(snapshots), 4)
        self.assertEqual(output.process.plan, ["初始词"])
        self.assertEqual(output.process.steps[0].detail["keywords"], ["初始词"])
        self.assertEqual(snapshots[0]["process"]["iterations"], 0)
        self.assertEqual(snapshots[0]["draft"], [])

    async def test_callback_failure_propagates(self) -> None:
        callback = AsyncMock(side_effect=OSError("cannot persist"))
        with self.assertRaisesRegex(OSError, "cannot persist"):
            await self.engine.run(on_progress=callback)
        self.search.assert_not_awaited()

    async def test_cancellation_is_not_treated_as_empty_search(self) -> None:
        self.search.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.engine.run()
        self.engine.report_agent.generate.assert_not_awaited()

    async def test_summary_failure_preserves_search_progress(self) -> None:
        self.search.return_value = [result("https://example.com/a")]
        self.engine.summary_agent.summarize.side_effect = RuntimeError("summary failed")
        snapshots = []
        with self.assertRaisesRegex(RuntimeError, "summary failed"):
            await self.engine.run(on_progress=snapshots.append)
        self.assertEqual(snapshots[-1]["sources"][0]["url"], "https://example.com/a")
        self.assertEqual(snapshots[-1]["process"]["steps"][-1]["type"], "search")

    async def test_report_failure_preserves_progress_on_disk(self) -> None:
        self.search.return_value = [result("https://example.com/a")]
        self.engine.report_agent.generate.side_effect = RuntimeError("report failed")
        with tempfile.TemporaryDirectory() as directory, patch.object(config, "DATA_DIR", Path(directory)):
            storage.create("test", "研究主题")
            storage.update_status("test", "running")

            def persist(snapshot):
                record = storage.get("test")
                record.process = ResearchProcess.model_validate(snapshot["process"])
                record.draft = [DraftBlock.model_validate(b) for b in snapshot["draft"]]
                record.sources = [Source.model_validate(s) for s in snapshot["sources"]]
                storage.save(record)

            with self.assertRaisesRegex(RuntimeError, "report failed"):
                await self.engine.run(on_progress=persist)
            storage.update_status("test", "failed", error="report failed")
            saved = storage.get("test")
            self.assertEqual(saved.status, Status.failed)
            self.assertEqual(saved.draft[0].text, "初始词正文")
            self.assertEqual(len(saved.sources), 1)
            self.assertEqual(saved.process.iterations, 1)
            self.assertEqual(saved.process.steps[-1].type, "judge")
