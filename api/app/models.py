from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


def json_col() -> Any:
    return Field(default_factory=dict, sa_column=Column(JSON))


class Workflow(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    prompt: str
    intent: dict = json_col()
    parent_id: Optional[int] = Field(default=None, foreign_key="workflow.id")
    created_at: datetime = Field(default_factory=now)


class Run(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    workflow_id: int = Field(foreign_key="workflow.id", index=True)
    mode: str = "live"  # live | demo | replay
    replay_of: Optional[int] = Field(default=None, foreign_key="run.id")
    status: str = "queued"  # queued | running | done | failed | cancelled
    progress: float = 0.0
    stats: dict = json_col()
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=now)
    finished_at: Optional[datetime] = None


class Source(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    url: str
    domain: str
    title: str = ""
    snippet: str = ""  # search-engine summary, used as a fallback when the page can't be fetched
    robots_allowed: bool = True
    status: str = "pending"  # pending | fetched | blocked | failed
    screenshot_path: Optional[str] = None
    markdown_path: Optional[str] = None
    fetched_at: Optional[datetime] = None


class Record(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    data: dict = json_col()
    status: str = "single"  # verified | single | conflict
    confidence: float = 0.5
    # field -> {"sources": n, "conflict": bool, "alternatives": [...]}
    field_meta: dict = json_col()


class Provenance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: int = Field(foreign_key="record.id", index=True)
    source_id: int = Field(foreign_key="source.id", index=True)
    field: str
    value: str
    quote: str


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    seq: int
    ts: datetime = Field(default_factory=now)
    type: str  # run | step | log | row | stats
    step: Optional[str] = None
    payload: dict = json_col()
