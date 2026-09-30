import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, col, select
from sse_starlette.sse import EventSourceResponse

from . import llm
from .config import BROWSER_ENABLED, CORS_ORIGIN_REGEX, CORS_ORIGINS, REMOTE_RENDER, GROQ_API_KEY, GROQ_FAST_MODEL, GROQ_MODEL, SCREENSHOT_DIR
from .db import IS_SQLITE, engine, get_session, init_db
from .services import evidence, export
from .events import emit as _emit, subscribe
from .models import Provenance, Record, Run, ScreenshotBlob, Source, Workflow
from .pipeline import orchestrator
from .pipeline.demo import create_demo_workflow, run_demo
from .pipeline.live import run_live
from .pipeline.replay import run_replay
from .pipeline.plan import Intent, make_plan
from .pipeline.steps import graph

def emit_log(run_id: int, step: str, message: str) -> None:
    _emit(run_id, "log", step, level="info", message=message)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # Runs that were in flight when the server stopped can't resume.
    with Session(engine) as s:
        for run in s.exec(select(Run).where(col(Run.status).in_(["queued", "running"]))).all():
            run.status, run.error = "failed", "Server restarted during run"
            s.add(run)
        s.commit()
    yield


app = FastAPI(title="Scout API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/files/screenshots/{name}")
def screenshot(name: str, s: Session = Depends(get_session)):
    """From disk when present, else from the database (hosts with ephemeral disks)."""
    path = SCREENSHOT_DIR / Path(name).name
    if path.is_file():
        return FileResponse(path)
    blob = s.get(ScreenshotBlob, Path(name).name)
    if not blob:
        raise HTTPException(404, "Screenshot not found")
    return Response(blob.data, media_type=blob.content_type,
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "llm": {"provider": "groq", "model": GROQ_MODEL, "fast_model": GROQ_FAST_MODEL,
                "configured": bool(GROQ_API_KEY)},
        "database": "sqlite" if IS_SQLITE else "postgres",
        "renderer": "browser" if BROWSER_ENABLED else ("remote" if REMOTE_RENDER else "none"),
    }


@app.get("/api/graph")
def get_graph():
    return graph()


@app.post("/api/llm/ping")
async def llm_ping():
    try:
        data = await llm.complete_json(
            "You are a health check. Reply with JSON only.",
            'Return {"ok": true, "model_says": "<three words>"}',
            temperature=0,
        )
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    return data


class PromptIn(BaseModel):
    prompt: str


def _start(s: Session, wf: Workflow, mode: str) -> dict:
    run = Run(workflow_id=wf.id, mode=mode)
    s.add(run)
    s.commit()
    s.refresh(run)
    orchestrator.start_run(run.id, run_demo if mode == "demo" else run_live)
    return {"run_id": run.id, "workflow_id": wf.id}


@app.post("/api/runs")
async def create_demo_run(body: PromptIn, s: Session = Depends(get_session)):
    """Scripted run with fictional data: no LLM quota or network needed."""
    if not body.prompt.strip():
        raise HTTPException(400, "Prompt is empty")
    return _start(s, create_demo_workflow(s, body.prompt.strip()), "demo")


@app.post("/api/workflows")
async def create_workflow(body: PromptIn, s: Session = Depends(get_session)):
    """Plan a workflow from a prompt. The user reviews and edits it before running."""
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Prompt is empty")
    try:
        intent = await make_plan(prompt)
    except llm.LLMError as e:
        raise HTTPException(502, f"Planner unavailable: {e}")
    except ValidationError as e:
        raise HTTPException(502, f"Planner returned an invalid plan: {e.errors()[0]['msg']}")
    wf = Workflow(prompt=prompt, intent=intent.model_dump())
    s.add(wf)
    s.commit()
    s.refresh(wf)
    return {**wf.model_dump(), "created_at": _utc(wf.created_at)}


@app.get("/api/workflows/{wf_id}")
def get_workflow(wf_id: int, s: Session = Depends(get_session)):
    wf = s.get(Workflow, wf_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return {**wf.model_dump(), "created_at": _utc(wf.created_at)}


class IntentIn(BaseModel):
    intent: dict


@app.put("/api/workflows/{wf_id}")
def update_workflow(wf_id: int, body: IntentIn, s: Session = Depends(get_session)):
    wf = s.get(Workflow, wf_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    try:
        wf.intent = Intent.model_validate(body.intent).model_dump()
    except ValidationError as e:
        err = e.errors()[0]
        raise HTTPException(422, f"{'.'.join(map(str, err['loc']))}: {err['msg']}")
    s.add(wf)
    s.commit()
    return {**wf.model_dump(), "created_at": _utc(wf.created_at)}


class RunIn(BaseModel):
    mode: str = "live"


@app.post("/api/workflows/{wf_id}/runs")
async def run_workflow(wf_id: int, body: RunIn, s: Session = Depends(get_session)):
    wf = s.get(Workflow, wf_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    if body.mode not in ("live", "demo"):
        raise HTTPException(400, "mode must be live or demo")
    return _start(s, wf, body.mode)


def _utc(dt: datetime | None) -> str | None:
    # SQLite drops tzinfo; everything we store is UTC.
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _run_out(run: Run, wf: Workflow) -> dict:
    return {
        **run.model_dump(),
        "started_at": _utc(run.started_at),
        "finished_at": _utc(run.finished_at),
        "prompt": wf.prompt,
        "active": orchestrator.is_active(run.id),
    }


@app.get("/api/runs")
def list_runs(s: Session = Depends(get_session)):
    rows = s.exec(
        select(Run, Workflow).join(Workflow).order_by(col(Run.id).desc()).limit(100)
    ).all()
    return [_run_out(r, w) for r, w in rows]


@app.get("/api/runs/{run_id}")
def get_run(run_id: int, s: Session = Depends(get_session)):
    run = s.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    wf = s.get(Workflow, run.workflow_id)
    return {**_run_out(run, wf), "intent": wf.intent}


@app.post("/api/runs/{run_id}/cancel")
def cancel(run_id: int):
    if not orchestrator.cancel_run(run_id):
        raise HTTPException(409, "Run is not active")
    return {"ok": True}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: int):
    async def stream():
        async for evt in subscribe(run_id):
            yield {"event": "message", "id": str(evt["seq"]), "data": json.dumps(evt)}
        yield {"event": "end", "data": "{}"}

    return EventSourceResponse(stream(), ping=15)


def _data_run_id(s: Session, run_id: int) -> int:
    """A replay shows its original run's records and sources."""
    run = s.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run.replay_of or run.id


def _records(s: Session, run_id: int) -> list[Record]:
    return s.exec(select(Record).where(Record.run_id == _data_run_id(s, run_id)).order_by(Record.id)).all()


@app.get("/api/runs/{run_id}/records")
def run_records(run_id: int, s: Session = Depends(get_session)):
    return [r.model_dump() for r in _records(s, run_id)]


def _source_out(src: Source) -> dict:
    return {**src.model_dump(), "fetched_at": _utc(src.fetched_at),
            "screenshot_url": f"/files/screenshots/{src.screenshot_path}" if src.screenshot_path else None}


@app.get("/api/runs/{run_id}/sources")
def run_sources(run_id: int, s: Session = Depends(get_session)):
    rid = _data_run_id(s, run_id)
    return [_source_out(x) for x in s.exec(select(Source).where(Source.run_id == rid).order_by(Source.id)).all()]


@app.get("/api/records/{record_id}/provenance")
def record_provenance(record_id: int, s: Session = Depends(get_session)):
    """Click-to-Proof: every field's value with the quote and page excerpt behind it."""
    rec = s.get(Record, record_id)
    if not rec:
        raise HTTPException(404, "Record not found")
    wf = s.exec(select(Workflow).join(Run).where(Run.id == rec.run_id)).first()
    rows = s.exec(
        select(Provenance, Source).join(Source).where(Provenance.record_id == record_id).order_by(Provenance.id)
    ).all()
    by_field: dict[str, list] = {}
    for p, src in rows:
        by_field.setdefault(p.field, []).append({
            "value": p.value,
            "quote": p.quote,
            "context": evidence.locate(p.quote, src.markdown_path, src.page_text or src.snippet),
            "source": {k: v for k, v in _source_out(src).items()
                       if k in ("id", "url", "domain", "title", "fetched_at", "screenshot_url")},
        })
    order = [f["name"] for f in wf.intent.get("fields", [])] if wf else list(by_field)
    return {
        "record": rec.model_dump(),
        "fields": [
            {"field": f, "value": rec.data.get(f), "meta": rec.field_meta.get(f, {}), "evidence": by_field[f]}
            for f in order if f in by_field
        ],
    }


class ResolveIn(BaseModel):
    field: str
    value: str | int | float | bool


@app.post("/api/records/{record_id}/resolve")
def resolve_conflict(record_id: int, body: ResolveIn, s: Session = Depends(get_session)):
    """A person picks the right value for a conflicting field. Logged to the run history."""
    rec = s.get(Record, record_id)
    if not rec:
        raise HTTPException(404, "Record not found")
    meta = dict(rec.field_meta)
    if body.field not in meta:
        raise HTTPException(400, f"Unknown field {body.field}")
    old = rec.data.get(body.field)
    rec.data = {**rec.data, body.field: body.value}
    meta[body.field] = {**meta[body.field], "conflict": False, "resolved": True, "alternatives": []}
    rec.field_meta = meta
    if not any(m.get("conflict") for m in meta.values()):
        verified = any(m.get("sources", 1) >= 2 for m in meta.values())
        rec.status, rec.confidence = ("verified", 0.8) if verified else ("single", 0.6)
    s.add(rec)
    s.commit()
    s.refresh(rec)
    emit_log(rec.run_id, "verify", f"Conflict resolved by user: {body.field} = {body.value!r} (was {old!r})")
    return rec.model_dump()


EXPORT_TYPES = {
    "csv": "text/csv",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@app.get("/api/runs/{run_id}/export")
def export_run(run_id: int, format: str = "csv", s: Session = Depends(get_session)):
    if format not in EXPORT_TYPES:
        raise HTTPException(400, "format must be csv, json or xlsx")
    run = s.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    wf = s.get(Workflow, run.workflow_id)
    records = _records(s, run_id)
    sources = {x.id: x.url for x in s.exec(select(Source).where(Source.run_id == _data_run_id(s, run_id))).all()}
    prov = s.exec(select(Provenance).where(col(Provenance.record_id).in_([r.id for r in records]))).all()
    body = export.build(format, wf.intent, records, prov, sources)
    name = f"scout-run-{run_id}.{format}"
    return Response(body, media_type=EXPORT_TYPES[format],
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/runs/{run_id}/diff")
def run_diff(run_id: int, s: Session = Depends(get_session)):
    """Compare with the previous finished run of the same workflow (by entity name)."""
    run = s.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    prev = s.exec(
        select(Run).where(Run.workflow_id == run.workflow_id, Run.id < run.id, Run.status == "done",
                          col(Run.replay_of).is_(None), Run.mode == run.mode)
        .order_by(col(Run.id).desc())
    ).first()
    if not prev or run.replay_of:
        return {"previous_run_id": None}
    wf = s.get(Workflow, run.workflow_id)
    id_field = wf.intent["fields"][0]["name"]
    return export.diff(id_field, _records(s, prev.id), _records(s, run.id)) | {"previous_run_id": prev.id}


@app.post("/api/runs/{run_id}/replay")
async def replay(run_id: int, s: Session = Depends(get_session)):
    """Re-emit a finished run's events: the offline-safe stage demo."""
    src = s.get(Run, run_id)
    if not src:
        raise HTTPException(404, "Run not found")
    original = s.get(Run, src.replay_of) if src.replay_of else src
    if original.status != "done":
        raise HTTPException(409, "Only finished runs can be replayed")
    run = Run(workflow_id=original.workflow_id, mode="replay", replay_of=original.id)
    s.add(run)
    s.commit()
    s.refresh(run)
    orchestrator.start_run(run.id, run_replay)
    return {"run_id": run.id, "workflow_id": run.workflow_id}
