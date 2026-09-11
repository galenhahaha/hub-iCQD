"""
内存版异步任务管理器
====================
承载“异步提交 + 结果轮询”这一产品形态：

- submit()：把一个研究任务封装成 asyncio 后台协程立即启动，马上返回 task_id；
- get()：按 task_id 轮询，能实时读到 阶段进展（phases）与最终结果（result）。

任务状态机：pending → running → done / failed

⚠️ 生产化提示：
这里用「进程内 dict」存储任务，服务重启即丢失、也不支持多实例横向扩展。
若要部署成真正的生产服务，建议把任务存储 / 队列替换为 Redis + 分布式任务队列
（如 Celery、ARQ、RQ），或至少把“进行中任务”交给后台 Worker 执行。
本实现的价值在于：以最少的复杂度演示完整的异步 + 轮询模式，便于学习与二次开发。
"""
from __future__ import annotations

import asyncio
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from .config import Settings
from .engine import ResearchEngine
from .schemas import TaskStatus


def _now_iso() -> str:
    """返回本地时区的 ISO 8601 时间字符串（供日志/展示用）。"""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class ResearchTaskManager:
    """维护一组研究任务的异步调度器。"""

    def __init__(self, settings: Settings, engine: ResearchEngine) -> None:
        self._settings = settings
        self._engine = engine
        # task_id -> 任务字典（含状态、进度、结果）
        self._tasks: Dict[str, Dict[str, Any]] = {}
        # task_id -> 创建时刻（epoch 秒），用于清理过期任务
        self._born: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def submit(
        self,
        topic: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """提交一个深度研究任务，立即返回任务描述（含 task_id）。

        注意：本方法必须在事件循环内被调用（FastAPI 的 async 路由天然满足），
        因为这里要在当前 loop 上创建后台协程。
        """
        self._purge_expired()  # 惰性清理过期任务，防止内存无限增长

        task_id = uuid.uuid4().hex[:12]
        created_at = _now_iso()
        entry: Dict[str, Any] = {
            "task_id": task_id,
            "topic": topic,
            "status": TaskStatus.PENDING,
            "research_mode": self._settings.research_mode,
            "created_at": created_at,
            "updated_at": created_at,
            "phases": [{"phase": "开始", "message": "研究任务已创建，排队中", "timestamp": created_at}],
            "error": None,
            "result": None,
        }
        self._tasks[task_id] = entry
        self._born[task_id] = time.time()

        # 在事件循环上启动后台协程——响应先返回，研究随后异步执行
        asyncio.get_running_loop().create_task(
            self._run(task_id, topic, options or {})
        )
        return entry

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """按 task_id 读取任务当前状态（轮询接口用）。"""
        return self._tasks.get(task_id)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    async def _run(self, task_id: str, topic: str, options: Dict[str, Any]) -> None:
        """后台执行体：跑引擎并回写状态。"""
        self._update(task_id, status=TaskStatus.RUNNING)

        def report(phase: str, message: str) -> None:
            """引擎每推进一步，就实时写进任务状态，供轮询接口读取。"""
            self._update(
                task_id,
                phase={"phase": phase, "message": message},
            )

        try:
            result = await self._engine.run(
                topic=topic,
                extra_instructions=options.get("extra_instructions", ""),
                options={
                    "max_rounds": options.get("max_rounds"),
                    "results_per_query": options.get("results_per_query"),
                },
                report=report,
            )
            self._update(
                task_id,
                status=TaskStatus.DONE,
                result=result,
                phase={"phase": "完成", "message": "研究报告生成完毕"},
            )
        except Exception as exc:  # noqa: BLE001 —— 后台任务必须兜住一切异常
            self._update(
                task_id,
                status=TaskStatus.FAILED,
                error=f"{exc}\n{traceback.format_exc()}",
                phase={"phase": "失败", "message": f"任务执行失败：{exc}"},
            )

    def _update(self, task_id: str, **changes: Any) -> None:
        """统一写状态：支持叠加一条 phase 进度。"""
        entry = self._tasks.get(task_id)
        if entry is None:
            return
        phase = changes.pop("phase", None)
        if phase:
            entry["phases"].append({**phase, "timestamp": _now_iso()})
        entry.update(changes)
        entry["updated_at"] = _now_iso()

    def _purge_expired(self) -> None:
        """删除已完成但超过保留时长的任务（每次提交时顺带执行）。"""
        ttl = self._settings.task_ttl_seconds
        now = time.time()
        for task_id in list(self._tasks):
            entry = self._tasks[task_id]
            if entry["status"] in (TaskStatus.DONE, TaskStatus.FAILED):
                if now - self._born.get(task_id, now) > ttl:
                    self._tasks.pop(task_id, None)
                    self._born.pop(task_id, None)
