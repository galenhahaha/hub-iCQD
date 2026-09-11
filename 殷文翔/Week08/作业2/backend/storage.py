"""Thread-safe JSON persistence with atomic whole-record replacement."""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import tempfile
import threading

from . import config
from .models import ResearchRecord, Status


_LOCK = threading.Lock()
_RESEARCH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def _path(rid: str) -> Path:
    """Keep record identifiers inside the configured storage directory."""
    if not _RESEARCH_ID.fullmatch(rid):
        raise ValueError("research_id 只能包含字母、数字、下划线和连字符，长度为 1–128。")
    path = config.DATA_DIR / f"{rid}.json"
    if path.resolve().parent != config.DATA_DIR.resolve():
        raise ValueError("研究记录路径超出了数据目录。")
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_unlocked(rid: str) -> ResearchRecord | None:
    path = _path(rid)
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return ResearchRecord.model_validate_json(content)


def _write_unlocked(rec: ResearchRecord) -> None:
    path = _path(rec.research_id)
    payload = rec.model_dump_json(indent=2, ensure_ascii=False)
    config.ensure_data_dir()
    temporary: Path | None = None
    try:
        # A failed write must leave the last complete progress snapshot intact.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config.DATA_DIR,
            prefix=f".{rec.research_id}-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create(rid: str, topic: str) -> ResearchRecord:
    """Create a pending record without overwriting an existing research task."""
    timestamp = _now()
    record = ResearchRecord(
        research_id=rid,
        topic=topic,
        status=Status.pending,
        created_at=timestamp,
        updated_at=timestamp,
    )
    with _LOCK:
        if _path(rid).exists():
            raise FileExistsError(f"研究记录已存在：{rid}")
        _write_unlocked(record)
    return record


def save(rec: ResearchRecord) -> None:
    with _LOCK:
        _write_unlocked(rec)


def get(rid: str) -> ResearchRecord | None:
    with _LOCK:
        return _read_unlocked(rid)


def update_status(rid: str, status: str, error: str | None = None) -> None:
    """Update status under one lock, preserving all saved research artifacts."""
    next_status = Status(status)
    with _LOCK:
        record = _read_unlocked(rid)
        if record is None:
            return
        record.status = next_status
        record.updated_at = _now()
        record.error = error
        _write_unlocked(record)


def list_all() -> list[ResearchRecord]:
    """Return records in descending creation order, with stable ID tie-breaking."""
    with _LOCK:
        records = []
        for path in config.DATA_DIR.glob("*.json"):
            record = _read_unlocked(path.stem)
            if record is not None:
                records.append(record)
        return sorted(records, key=lambda record: (record.created_at, record.research_id), reverse=True)
