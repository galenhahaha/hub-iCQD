"""Connect the research engine to persistent task states and progress."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from . import config, storage
from .engine import DeepResearch
from .models import DraftBlock, ResearchProcess, Source, Status


logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_research(research_id: str) -> None:
    """Run a pending task once, retaining the last snapshot on failure."""
    record = storage.get(research_id)
    if record is None or record.status != Status.pending:
        return

    def on_progress(snapshot: dict[str, Any]) -> None:
        # Validate the entire snapshot before replacing the previous version.
        process = ResearchProcess.model_validate(snapshot["process"])
        draft = [DraftBlock.model_validate(block) for block in snapshot["draft"]]
        sources = [Source.model_validate(source) for source in snapshot["sources"]]
        record.process = process
        record.draft = draft
        record.sources = sources
        record.updated_at = _now()
        storage.save(record)

    try:
        storage.update_status(research_id, Status.running)
        record.status = Status.running
        result = await DeepResearch(record.topic).run(on_progress=on_progress)
        record.report = result.report
        record.report_html = result.report_html
        record.sources = result.sources
        record.draft = result.draft
        record.process = result.process
        record.confidence = result.confidence
        record.status = Status.completed
        record.error = None
        record.updated_at = _now()
        storage.save(record)
        logger.info("Research %s completed", research_id)
    except asyncio.CancelledError:
        storage.update_status(research_id, Status.failed, error="服务关闭，研究任务已中断。")
        raise
    except Exception as exc:
        # SDK exception messages can contain credentials; never persist them.
        error = str(exc) or type(exc).__name__
        for secret in (config.OPENAI_API_KEY, config.BOCHA_API_KEY):
            if secret:
                error = error.replace(secret, "[REDACTED]")
        storage.update_status(research_id, Status.failed, error=error)
        logger.error("Research %s failed (%s)", research_id, type(exc).__name__)
