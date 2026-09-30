"""Per-run event bus: every pipeline step emits events here.

Events are persisted (so finished runs can be replayed) and fanned out to live
SSE subscribers. A late subscriber first receives the history, then live events.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlmodel import Session, select

from .db import engine
from .models import Event

TERMINAL_RUN_STATUSES = {"done", "failed", "cancelled"}


@dataclass
class _Channel:
    history: list[dict] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    closed: bool = False


_channels: dict[int, _Channel] = defaultdict(_Channel)


def emit(run_id: int, type: str, step: str | None = None, **payload) -> dict:
    if run_id not in _channels:
        # e.g. a user action on a run finished before a restart: continue its sequence.
        history = _load_history(run_id)
        _channels[run_id] = _Channel(history=history, closed=any(
            e["type"] == "run" and e["payload"].get("status") in TERMINAL_RUN_STATUSES for e in history))
    ch = _channels[run_id]
    evt = {
        "seq": len(ch.history),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": type,
        "step": step,
        "payload": payload,
    }
    ch.history.append(evt)
    with Session(engine) as s:
        s.add(Event(run_id=run_id, seq=evt["seq"], type=type, step=step, payload=payload))
        s.commit()
    for q in ch.subscribers:
        q.put_nowait(evt)
    if type == "run" and payload.get("status") in TERMINAL_RUN_STATUSES:
        ch.closed = True
        for q in ch.subscribers:
            q.put_nowait(None)
    return evt


def _load_history(run_id: int) -> list[dict]:
    with Session(engine) as s:
        rows = s.exec(select(Event).where(Event.run_id == run_id).order_by(Event.seq)).all()
    return [
        {"seq": e.seq, "ts": e.ts.replace(tzinfo=timezone.utc).isoformat(), "type": e.type,
         "step": e.step, "payload": e.payload}
        for e in rows
    ]


async def subscribe(run_id: int) -> AsyncIterator[dict]:
    if run_id not in _channels:
        # Not active in this process (e.g. after a restart): serve what was stored.
        for evt in _load_history(run_id):
            yield evt
        return

    ch = _channels[run_id]
    q: asyncio.Queue = asyncio.Queue()
    history = list(ch.history)
    closed = ch.closed
    if not closed:
        ch.subscribers.add(q)
    try:
        for evt in history:
            yield evt
        if closed:
            return
        last_seq = history[-1]["seq"] if history else -1
        while True:
            evt = await q.get()
            if evt is None:
                return
            if evt["seq"] > last_seq:
                yield evt
    finally:
        ch.subscribers.discard(q)
