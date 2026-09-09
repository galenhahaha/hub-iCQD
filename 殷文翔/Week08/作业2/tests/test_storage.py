"""Use temporary directories to verify persistence and failure recovery."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import config, storage
from backend.models import DraftBlock, ResearchProcess, Status


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.data_dir = Path(directory) / "research"
        self.enterContext(patch.object(config, "DATA_DIR", self.data_dir))

    def test_create_and_round_trip(self) -> None:
        record = storage.create("test-id", "中文主题")
        self.assertEqual(record.status, Status.pending)
        self.assertEqual(record.created_at, record.updated_at)
        record.draft = [DraftBlock(round=1, keyword="关键词", text="正文")]
        record.process = ResearchProcess(plan=["关键词"], search_queries=["关键词"], reviewed_urls=[])
        storage.save(record)
        self.assertEqual(storage.get("test-id"), record)
        self.assertIn("中文主题", (self.data_dir / "test-id.json").read_text(encoding="utf-8"))

    def test_status_update_preserves_saved_progress(self) -> None:
        record = storage.create("test", "主题")
        record.draft = [DraftBlock(round=1, keyword="词", text="已保存的草稿")]
        storage.save(record)
        storage.update_status("test", "running")
        self.assertEqual(storage.get("test").status, Status.running)
        storage.update_status("test", "failed", error="模拟失败")
        failed = storage.get("test")
        self.assertEqual(failed.status, Status.failed)
        self.assertEqual(failed.error, "模拟失败")
        self.assertEqual(failed.draft, record.draft)
        self.assertEqual(failed.created_at, record.created_at)

    def test_missing_records_and_empty_directory(self) -> None:
        self.assertIsNone(storage.get("missing"))
        self.assertEqual(storage.list_all(), [])
        storage.update_status("missing", "running")
        self.assertFalse(self.data_dir.exists())

    def test_duplicate_creation_preserves_existing_record(self) -> None:
        original = storage.create("same", "原主题")
        with self.assertRaises(FileExistsError):
            storage.create("same", "不应覆盖")
        self.assertEqual(storage.get("same"), original)

    def test_list_is_sorted_by_creation_time(self) -> None:
        with patch.object(storage, "_now", side_effect=["2026-09-01T00:00:00+00:00", "2026-09-02T00:00:00+00:00"]):
            storage.create("z-old", "旧")
            storage.create("a-new", "新")
        self.assertEqual([r.research_id for r in storage.list_all()], ["a-new", "z-old"])

    def test_invalid_ids_cannot_escape_data_directory(self) -> None:
        for rid in ("", "../escape", "a/b", "a\\b", "C:\\escape", ".", "id:stream"):
            with self.subTest(rid=rid):
                with self.assertRaises(ValueError):
                    storage.create(rid, "主题")
                with self.assertRaises(ValueError):
                    storage.get(rid)
        self.assertFalse(self.data_dir.exists())

    def test_failed_replacement_keeps_old_snapshot(self) -> None:
        original = storage.create("safe", "旧快照")
        changed = original.model_copy(update={"topic": "新快照"})
        with patch.object(storage.os, "replace", side_effect=OSError("simulated disk error")):
            with self.assertRaises(OSError):
                storage.save(changed)
        self.assertEqual(storage.get("safe"), original)
        self.assertEqual([p.name for p in self.data_dir.iterdir()], ["safe.json"])

    def test_concurrent_readers_see_complete_records(self) -> None:
        original = storage.create("shared", "初始")

        def write_and_read(index):
            storage.save(original.model_copy(update={"topic": str(index)}))
            record = storage.get("shared")
            self.assertEqual(record.research_id, "shared")
            self.assertEqual(len(storage.list_all()), 1)

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(write_and_read, range(24)))
        self.assertIsNotNone(storage.get("shared"))
