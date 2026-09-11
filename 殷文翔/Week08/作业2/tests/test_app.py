"""Exercise API scheduling, CORS, shutdown, and a real uvicorn process."""

import asyncio
from contextlib import AsyncExitStack
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import UUID

import httpx

from backend import config, research, storage
from backend.app import app
from backend.models import ResearchRecord, Status


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.data_dir = Path(directory) / "research"
        self.enterContext(patch.object(config, "DATA_DIR", self.data_dir))
        self.entered = asyncio.Event()

        async def blocked_run(engine, on_progress):
            on_progress({"process": {"plan": [engine.topic], "search_queries": [], "reviewed_urls": []}, "draft": [], "sources": []})
            self.entered.set()
            await asyncio.Event().wait()

        self.enterContext(patch.object(research.DeepResearch, "run", new=blocked_run))
        self.lifespan = await self.enterAsyncContext(AsyncExitStack())
        await self.lifespan.enter_async_context(app.router.lifespan_context(app))
        self.client = await self.enterAsyncContext(httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test"))

    async def test_health_and_empty_list(self) -> None:
        self.assertTrue(self.data_dir.is_dir())
        response = await self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual((await self.client.get("/api/research")).json(), [])

    async def test_frontend_is_served_at_root_and_static_path(self) -> None:
        for path in ("/", "/static/index.html"):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers["content-type"])
            self.assertIn("深度研究助手", response.text)

    async def test_post_returns_before_worker_finishes_and_progress_is_pollable(self) -> None:
        response = await self.client.post("/api/research", json={"topic": "  中文主题  "})
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "pending")
        research_id = body["research_id"]
        UUID(research_id)
        saved = storage.get(research_id)
        self.assertEqual(saved.status, Status.pending)
        self.assertEqual(saved.topic, "中文主题")
        await asyncio.wait_for(self.entered.wait(), timeout=5)
        response = await self.client.get(f"/api/research/{research_id}")
        self.assertEqual(response.status_code, 200)
        record = ResearchRecord.model_validate(response.json())
        self.assertEqual(record.status, Status.running)
        self.assertEqual(record.process.plan, ["中文主题"])
        self.assertEqual(record, ResearchRecord.model_validate_json((self.data_dir / f"{research_id}.json").read_text(encoding="utf-8")))
        self.assertEqual((await self.client.get("/api/research")).json(), [response.json()])

    async def test_invalid_topics_create_no_tasks_or_files(self) -> None:
        for body in ({}, {"topic": ""}, {"topic": " \n\t "}, {"topic": "字" * 501}, {"topic": None}, {"topic": 12}):
            with self.subTest(body=body):
                self.assertEqual((await self.client.post("/api/research", json=body)).status_code, 422)
        self.assertEqual(storage.list_all(), [])
        self.assertEqual(app.state.research_tasks, {})

    async def test_missing_and_invalid_ids_return_404(self) -> None:
        for research_id in ("missing", "id:stream", "bad%5Cid"):
            self.assertEqual((await self.client.get(f"/api/research/{research_id}")).status_code, 404)

    async def test_cors_preflight_and_actual_response(self) -> None:
        headers = {"Origin": config.FRONTEND_ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
        response = await self.client.options("/api/research", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], config.FRONTEND_ORIGIN)
        response = await self.client.get("/health", headers={"Origin": config.FRONTEND_ORIGIN})
        self.assertEqual(response.headers["access-control-allow-origin"], config.FRONTEND_ORIGIN)
        headers["Origin"] = "https://untrusted.invalid"
        response = await self.client.options("/api/research", headers=headers)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)

    async def test_shutdown_cancels_task_and_persists_failure(self) -> None:
        response = await self.client.post("/api/research", json={"topic": "关闭测试"})
        research_id = response.json()["research_id"]
        await asyncio.wait_for(self.entered.wait(), timeout=5)
        await self.lifespan.aclose()
        record = storage.get(research_id)
        self.assertEqual(record.status, Status.failed)
        self.assertIn("中断", record.error)
        self.assertEqual(record.process.plan, ["关闭测试"])
        self.assertEqual(app.state.research_tasks, {})

    async def test_shutdown_before_worker_starts_does_not_leave_pending_record(self) -> None:
        response = await self.client.post("/api/research", json={"topic": "尚未开始"})
        research_id = response.json()["research_id"]
        self.assertEqual(storage.get(research_id).status, Status.pending)
        await self.lifespan.aclose()
        self.assertEqual(storage.get(research_id).status, Status.failed)

    async def test_scheduling_failure_is_not_accepted(self) -> None:
        with patch("backend.app.asyncio.create_task", side_effect=RuntimeError("scheduler unavailable")):
            response = await self.client.post("/api/research", json={"topic": "调度失败"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(storage.list_all()[0].status, Status.failed)


class UvicornSmokeTests(unittest.TestCase):
    def test_real_http_and_persisted_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "research"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            # Only storage is redirected; import and serve the production app.
            script = (
                "import sys; from pathlib import Path; from backend import config; "
                "config.DATA_DIR = Path(sys.argv[1]); import uvicorn; "
                "uvicorn.run('backend.app:app', host='127.0.0.1', port=int(sys.argv[2]))"
            )
            env = dict(os.environ, DEEPSEEK_API_KEY="", OPENAI_API_KEY="", BOCHA_API_KEY="")
            with (Path(directory) / "uvicorn.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [sys.executable, "-c", script, str(data_dir), str(port)],
                    cwd=Path(__file__).resolve().parents[1], env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                try:
                    with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=2) as client:
                        deadline = time.monotonic() + 30
                        while True:
                            if process.poll() is not None:
                                self.fail("uvicorn exited before becoming ready")
                            try:
                                response = client.get("/health")
                                break
                            except httpx.TransportError:
                                if time.monotonic() >= deadline:
                                    self.fail("uvicorn did not start within 30 seconds")
                                time.sleep(0.1)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json(), {"status": "ok"})
                        response = client.post("/api/research", json={"topic": "HTTP 落盘验收"})
                        self.assertEqual(response.status_code, 202)
                        body = response.json()
                        self.assertEqual(body["status"], "pending")
                        UUID(body["research_id"])
                        for _ in range(100):
                            polled = client.get(f"/api/research/{body['research_id']}")
                            self.assertEqual(polled.status_code, 200)
                            if polled.json()["status"] == "failed":
                                break
                            time.sleep(0.05)
                        record = ResearchRecord.model_validate(polled.json())
                        self.assertEqual(record.status, Status.failed)
                        self.assertIn("OPENAI_API_KEY", record.error)
                        disk = json.loads((data_dir / f"{record.research_id}.json").read_text(encoding="utf-8"))
                        self.assertEqual(disk, record.model_dump(mode="json"))
                        self.assertEqual(set(disk), set(ResearchRecord.model_fields))
                finally:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
