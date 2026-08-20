#@mediavault
"""
Global + per-user download queue with cancel support.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional

from config import QUEUE_MAX_GLOBAL, QUEUE_MAX_PER_USER

logger = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    user_id: int
    label: str
    coro_factory: Callable[[], Coroutine]
    status: str = "queued"  # queued | running | done | cancelled | error
    position: int = 0
    error: str | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task | None = None


class DownloadQueue:
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._user_active: Dict[int, int] = {}
        self._global_active = 0
        self._lock = asyncio.Lock()
        self._waiter = asyncio.Event()

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def user_jobs(self, user_id: int) -> list[Job]:
        return [j for j in self._jobs.values() if j.user_id == user_id and j.status in ("queued", "running")]

    async def submit(self, user_id: int, label: str, coro_factory: Callable[[], Coroutine]) -> Job:
        async with self._lock:
            user_count = self._user_active.get(user_id, 0) + len(
                [j for j in self._jobs.values() if j.user_id == user_id and j.status == "queued"]
            )
            if QUEUE_MAX_PER_USER > 0 and user_count >= QUEUE_MAX_PER_USER:
                raise RuntimeError(f"Per-user queue full (max {QUEUE_MAX_PER_USER})")
            total_queued = len([j for j in self._jobs.values() if j.status == "queued"])
            if QUEUE_MAX_GLOBAL > 0 and (self._global_active + total_queued) >= QUEUE_MAX_GLOBAL * 2:
                raise RuntimeError("Global queue is full, try again later")

            job = Job(id=uuid.uuid4().hex[:10], user_id=user_id, label=label, coro_factory=coro_factory)
            self._jobs[job.id] = job
            self._recompute_positions()
        self._waiter.set()
        asyncio.create_task(self._pump())
        return job

    def _recompute_positions(self):
        queued = [j for j in self._jobs.values() if j.status == "queued"]
        for i, j in enumerate(queued, 1):
            j.position = i

    async def cancel(self, job_id: str, user_id: int | None = None) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        if user_id is not None and job.user_id != user_id:
            return False
        job.cancel_event.set()
        job.status = "cancelled"
        if job._task and not job._task.done():
            job._task.cancel()
        return True

    async def _pump(self):
        async with self._lock:
            while self._global_active < QUEUE_MAX_GLOBAL:
                next_job = next((j for j in self._jobs.values() if j.status == "queued"), None)
                if not next_job:
                    break
                # per-user running check
                if self._user_active.get(next_job.user_id, 0) >= QUEUE_MAX_PER_USER:
                    # skip for now, try another user
                    others = [j for j in self._jobs.values() if j.status == "queued" and self._user_active.get(j.user_id, 0) < QUEUE_MAX_PER_USER]
                    next_job = others[0] if others else None
                    if not next_job:
                        break
                next_job.status = "running"
                self._global_active += 1
                self._user_active[next_job.user_id] = self._user_active.get(next_job.user_id, 0) + 1
                self._recompute_positions()
                next_job._task = asyncio.create_task(self._run(next_job))

    async def _run(self, job: Job):
        try:
            if job.cancel_event.is_set():
                job.status = "cancelled"
                return
            await job.coro_factory()
            if job.cancel_event.is_set():
                job.status = "cancelled"
            else:
                job.status = "done"
        except asyncio.CancelledError:
            job.status = "cancelled"
        except Exception as e:
            logger.exception("Job %s failed", job.id)
            job.status = "error"
            job.error = str(e)[:300]
        finally:
            async with self._lock:
                self._global_active = max(0, self._global_active - 1)
                self._user_active[job.user_id] = max(0, self._user_active.get(job.user_id, 1) - 1)
                # cleanup old finished jobs
                for jid, j in list(self._jobs.items()):
                    if j.status in ("done", "cancelled", "error") and j is not job:
                        # keep recent errors briefly
                        pass
                self._recompute_positions()
            await self._pump()


queue = DownloadQueue()
