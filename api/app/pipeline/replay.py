"""Replay a finished run's recorded events with (compressed) original timing.

Needs no network or LLM quota, so the stage demo cannot be broken by venue
Wi-Fi. Rows keep their original record ids, so Click-to-Proof still works.
"""

import asyncio
import os
from datetime import datetime

from sqlmodel import Session, select

from ..db import engine
from ..events import emit
from ..models import Event, Run
from .orchestrator import set_progress, update_run

# The whole replay fits a demo slot, however long the real run took.
REPLAY_SECONDS = float(os.getenv("SCOUT_REPLAY_SECONDS", "40"))
MIN_GAP = 0.02


async def run_replay(run_id: int) -> None:
    with Session(engine) as s:
        run = s.get(Run, run_id)
        original = s.get(Run, run.replay_of)
        events = s.exec(select(Event).where(Event.run_id == original.id).order_by(Event.seq)).all()
        stats = original.stats

    body = [e for e in events if e.type != "run"]  # the orchestrator emits our own lifecycle
    # Scale every gap evenly, so the replay keeps the live run's rhythm.
    real = (body[-1].ts - body[0].ts).total_seconds() if len(body) > 1 else 0
    scale = REPLAY_SECONDS / real if real > 0 else 0
    prev: datetime | None = None
    for i, e in enumerate(body):
        if prev is not None:
            gap = (e.ts - prev).total_seconds()
            await asyncio.sleep(max(gap * scale, MIN_GAP))
        prev = e.ts
        emit(run_id, e.type, e.step, **e.payload)
        if i % 10 == 0:
            set_progress(run_id, i / max(len(body), 1))
    update_run(run_id, stats=stats)
