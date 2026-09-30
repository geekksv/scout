"""Starts, tracks and cancels pipeline runs as asyncio tasks."""

import asyncio
import logging
from typing import Awaitable, Callable

from sqlmodel import Session

from ..db import engine
from ..events import emit
from ..models import Run, now

log = logging.getLogger("scout.orchestrator")

_tasks: dict[int, asyncio.Task] = {}

RunFn = Callable[[int], Awaitable[None]]


def update_run(run_id: int, **fields) -> None:
    with Session(engine) as s:
        run = s.get(Run, run_id)
        for k, v in fields.items():
            setattr(run, k, v)
        s.add(run)
        s.commit()


def set_progress(run_id: int, progress: float) -> None:
    update_run(run_id, progress=round(min(max(progress, 0.0), 1.0), 3))


async def _supervise(run_id: int, fn: RunFn) -> None:
    update_run(run_id, status="running")
    emit(run_id, "run", status="running")
    try:
        await fn(run_id)
    except asyncio.CancelledError:
        update_run(run_id, status="cancelled", finished_at=now())
        emit(run_id, "run", status="cancelled")
    except Exception as e:  # surface every failure in the UI rather than dying silently
        log.exception("run %s failed", run_id)
        update_run(run_id, status="failed", error=str(e), finished_at=now())
        emit(run_id, "log", level="error", message=f"Run failed: {e}")
        emit(run_id, "run", status="failed", error=str(e))
    else:
        update_run(run_id, status="done", progress=1.0, finished_at=now())
        emit(run_id, "run", status="done")
    finally:
        _tasks.pop(run_id, None)


def start_run(run_id: int, fn: RunFn) -> None:
    _tasks[run_id] = asyncio.create_task(_supervise(run_id, fn))


def cancel_run(run_id: int) -> bool:
    task = _tasks.get(run_id)
    if not task:
        return False
    task.cancel()
    return True


def is_active(run_id: int) -> bool:
    return run_id in _tasks
