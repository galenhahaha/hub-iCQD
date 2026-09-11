"""Verify engine-to-storage integration without calling external services."""

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from backend import config, research, storage, tools
from backend.agent import JudgeAgent, KeywordAgent, ReportAgent, SummaryAgent
from backend.models import JudgeDecision, ReportContent, ResearchRecord, Section, Status


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.data_dir = Path(directory)
        self.enterContext(patch.object(config, "DATA_DIR", self.data_dir))
        self.enterContext(patch("backend.agent.base.Runner.run", side_effect=AssertionError("LLM forbidden")))
        self.enterContext(patch.object(KeywordAgent, "generate_keywords", new=AsyncMock(return_value=["关键词"])))
        self.enterContext(patch.object(SummaryAgent, "summarize", new=AsyncMock(return_value="研究正文")))
        self.enterContext(patch.object(JudgeAgent, "judge", new=AsyncMock(return_value=JudgeDecision(sufficient=True))))
        self.enterContext(patch.object(tools, "web_search", new=AsyncMock(return_value=[{
            "url": "https://example.com/source", "title": "资料", "snippet": "摘要", "date": "2026-09-01",
        }])))

        async def generate(topic, draft, sources, confidence):
            return ReportContent(
                title=topic, summary="报告摘要", key_conclusions=[],
                sections=[Section(heading=block.keyword, body=block.text) for block in draft],
            ), "<!DOCTYPE html><html lang='zh'><body>研究报告</body></html>"

        self.report = self.enterContext(patch.object(ReportAgent, "generate", new=AsyncMock(side_effect=generate)))
        self.initial = storage.create("test", "研究主题")

    async def test_success_persists_running_snapshots_and_all_artifacts(self) -> None:
        snapshots = []
        save = storage.save

        def capture(record):
            save(record)
            snapshots.append(json.loads((self.data_dir / "test.json").read_text(encoding="utf-8")))

        with patch.object(storage, "save", side_effect=capture):
            await research.run_research("test")
        self.assertEqual([s["status"] for s in snapshots], ["running"] * 4 + ["completed"])
        self.assertEqual(snapshots[0]["process"]["plan"], ["关键词"])
        self.assertEqual(snapshots[0]["draft"], [])
        final = ResearchRecord.model_validate(snapshots[-1])
        self.assertEqual(final.created_at, self.initial.created_at)
        self.assertGreater(final.updated_at, final.created_at)
        self.assertIsNone(final.error)
        self.assertEqual(final.report.sections[0].body, "研究正文")
        self.assertIn("研究报告", final.report_html)
        self.assertEqual(final.process.reviewed_urls, [s.url for s in final.sources])
        self.assertEqual(final.process.iterations, 1)
        self.assertEqual(final.draft[0].keyword, "关键词")
        self.assertEqual(final.confidence.info_cutoff, "2026-09-01")

    async def test_report_failure_preserves_last_snapshot(self) -> None:
        self.report.side_effect = RuntimeError("报告生成失败")
        with self.assertLogs("backend.research", level="ERROR"):
            await research.run_research("test")
        record = storage.get("test")
        self.assertEqual(record.status, Status.failed)
        self.assertEqual(record.error, "报告生成失败")
        self.assertEqual(record.draft[0].text, "研究正文")
        self.assertEqual(len(record.sources), 1)
        self.assertEqual(record.process.steps[-1].type, "judge")
        self.assertIsNone(record.report)

    async def test_invalid_snapshot_does_not_replace_saved_progress(self) -> None:
        async def invalid_progress(engine, on_progress):
            on_progress({"process": {"plan": ["合法"], "search_queries": [], "reviewed_urls": []}, "draft": [], "sources": []})
            on_progress({"process": {}, "draft": [], "sources": []})

        with patch.object(research.DeepResearch, "run", new=invalid_progress), self.assertLogs("backend.research", level="ERROR"):
            await research.run_research("test")
        record = storage.get("test")
        self.assertEqual(record.status, Status.failed)
        self.assertEqual(record.process.plan, ["合法"])

    async def test_cancellation_marks_failed_and_retains_progress(self) -> None:
        entered = asyncio.Event()

        async def wait_for_cancellation(*args):
            entered.set()
            await asyncio.Event().wait()

        self.report.side_effect = wait_for_cancellation
        task = asyncio.create_task(research.run_research("test"))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        record = storage.get("test")
        self.assertEqual(record.status, Status.failed)
        self.assertIn("中断", record.error)
        self.assertEqual(record.draft[0].text, "研究正文")

    async def test_duplicate_worker_does_not_restart_running_or_terminal_task(self) -> None:
        for state in (Status.running, Status.completed, Status.failed):
            storage.update_status("test", state)
            before = storage.get("test")
            await research.run_research("test")
            self.assertEqual(storage.get("test"), before)
        await research.run_research("missing")
        self.report.assert_not_awaited()

    async def test_credentials_are_redacted_from_failure(self) -> None:
        self.report.side_effect = RuntimeError("credentials: test-llm-secret test-search-secret")
        with patch.object(config, "OPENAI_API_KEY", "test-llm-secret"), patch.object(config, "BOCHA_API_KEY", "test-search-secret"):
            with self.assertLogs("backend.research", level="ERROR"):
                await research.run_research("test")
        self.assertEqual(storage.get("test").error, "credentials: [REDACTED] [REDACTED]")
