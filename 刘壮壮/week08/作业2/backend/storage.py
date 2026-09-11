"""研究记录 JSON 落盘。"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from .core import config
from .models import ResearchRecord, ResearchSummary

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def _path(rid: str):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return config.DATA_DIR / f"{rid}.json"


def save(record: ResearchRecord) -> None:
    path = _path(record.id)
    with _lock:
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    logger.debug("saved %s status=%s", record.id, record.status)


def load(rid: str) -> Optional[ResearchRecord]:
    path = _path(rid)
    if not path.exists():
        return None
    with _lock:
        raw = path.read_text(encoding="utf-8")
    return ResearchRecord.model_validate_json(raw)


def list_records() -> list[ResearchSummary]:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    items: list[ResearchSummary] = []
    with _lock:
        paths = sorted(config.DATA_DIR.glob("*.json"))
        for path in paths:
            try:
                rec = ResearchRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("skip corrupt %s: %s", path.name, exc)
                continue
            items.append(
                ResearchSummary(
                    id=rec.id,
                    topic=rec.topic,
                    status=rec.status,
                    created_at=rec.created_at,
                    updated_at=rec.updated_at,
                )
            )
    items.sort(key=lambda x: x.updated_at, reverse=True)
    return items


if __name__ == "__main__":
    from datetime import datetime, timezone

    rid = "_storage_demo"
    path = _path(rid)
    try:
        rec = ResearchRecord(
            id=rid,
            topic="storage demo",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        save(rec)
        loaded = load(rid)
        assert loaded and loaded.topic == rec.topic
        assert any(x.id == rid for x in list_records())
        print("ok", loaded.id)
    finally:
        if path.exists():
            path.unlink()
