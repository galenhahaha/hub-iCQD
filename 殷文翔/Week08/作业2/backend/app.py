"""HTTP API for submitting research tasks and polling persisted results."""

import asyncio
from contextlib import asynccontextmanager
import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, storage
from .models import ResearchAccepted, ResearchRecord, ResearchRequest, Status
from .research import run_research


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    config.ensure_data_dir()
    app.state.research_tasks = {}
    try:
        yield
    finally:
        # Keep strong references, cancel workers, and persist interruption state.
        tasks = list(app.state.research_tasks.items())
        for task, _ in tasks:
            task.cancel()
        await asyncio.gather(*(task for task, _ in tasks), return_exceptions=True)
        for _, research_id in tasks:
            record = storage.get(research_id)
            if record is not None and record.status in (Status.pending, Status.running):
                storage.update_status(research_id, Status.failed, error="服务关闭，研究任务已中断。")


app = FastAPI(title="深度研究助手", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(config.BASE_DIR / "static" / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/research", response_model=ResearchAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_research(body: ResearchRequest, request: Request) -> ResearchAccepted:
    research_id = str(uuid4())
    storage.create(research_id, body.topic)
    worker = run_research(research_id)
    try:
        task = asyncio.create_task(worker, name=f"research-{research_id}")
    except Exception:
        worker.close()
        storage.update_status(research_id, Status.failed, error="研究任务启动失败。")
        raise HTTPException(status_code=503, detail="研究任务启动失败，请重试。") from None
    tasks = request.app.state.research_tasks
    tasks[task] = research_id

    def on_done(completed: asyncio.Task) -> None:
        tasks.pop(completed, None)
        if not completed.cancelled() and (error := completed.exception()) is not None:
            logger.error("Research worker %s failed (%s)", research_id, type(error).__name__)

    task.add_done_callback(on_done)
    return ResearchAccepted(research_id=research_id)


@app.get("/api/research", response_model=list[ResearchRecord])
async def list_research() -> list[ResearchRecord]:
    return storage.list_all()


@app.get("/api/research/{research_id}", response_model=ResearchRecord)
async def get_research(research_id: str) -> ResearchRecord:
    try:
        record = storage.get(research_id)
    except ValueError:
        # Invalid filenames are never passed through to the filesystem.
        raise HTTPException(status_code=404, detail="研究记录不存在。") from None
    if record is None:
        raise HTTPException(status_code=404, detail="研究记录不存在。")
    return record
