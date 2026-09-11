# -*- coding: utf-8 -*-
"""研究记录落盘：wxz_backend/data/research/{research_id}.json，一个研究一个文件。

状态流转 pending -> running -> completed / failed，每次变化整文件覆盖写。
用一把线程锁串行化磁盘写入，避免并发请求下的写冲突。
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from . import config
from .models import ResearchRecord, Status

_LOCK = threading.Lock()


def _path(rid: str):
    config.ensure_data_dir()
    return config.DATA_DIR / f"{rid}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(rid: str, topic: str) -> ResearchRecord:
    """新建一条 pending 记录并落盘。"""
    rec = ResearchRecord(
        research_id=rid,
        topic=topic,
        status=Status.pending,
        created_at=_now(),
        updated_at=_now(),
    )
    save(rec)
    return rec


def save(rec: ResearchRecord) -> None:
    """整文件覆盖写入一条记录，并刷新 updated_at。"""
    rec.updated_at = _now()
    with _LOCK:
        _path(rec.research_id).write_text(
            rec.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def get(rid: str) -> ResearchRecord | None:
    """按 research_id 读取，不存在返回 None。"""
    p = _path(rid)
    if not p.exists():
        return None
    return ResearchRecord.model_validate_json(p.read_text(encoding="utf-8"))


def update_status(rid: str, status: str, error: str | None = None) -> None:
    """更新记录状态，可选附带错误信息。"""
    rec = get(rid)
    if rec is None:
        return
    rec.status = Status(status)
    if error:
        rec.error = error
    save(rec)


def list_all() -> list[ResearchRecord]:
    """按创建时间升序返回全部记录。

    排序依据是记录里的 created_at（ISO 8601 字符串，同格式按字典序即时间序），
    而不是文件名——文件名是 uuid 十六进制，与时间无关。
    """
    if not config.DATA_DIR.exists():
        return []
    records = [
        ResearchRecord.model_validate_json(p.read_text(encoding="utf-8"))
        for p in config.DATA_DIR.glob("*.json")
    ]
    records.sort(key=lambda r: r.created_at)
    return records


if __name__ == "__main__":
    # 自检 demo：create -> get -> update_status -> list_all -> 清理（纯本地，不联网）
    rid = "demo-storage-test"
    p = config.DATA_DIR / f"{rid}.json"
    try:
        created = create(rid, "存储模块自检主题")
        print("create:", created.status, created.topic)

        got = get(rid)
        assert got is not None and got.topic == "存储模块自检主题"
        print("get   :", got.research_id, got.status)

        update_status(rid, "running")
        assert get(rid) is not None and get(rid).status == Status.running
        print("update_status:", get(rid).status)

        assert any(r.research_id == rid for r in list_all())
        print("list_all 包含该记录 OK")
        print("存储自检 OK")
    finally:
        if p.exists():
            p.unlink()
        print("已清理测试记录:", not p.exists())
