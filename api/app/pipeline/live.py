"""The real pipeline: plan -> discover -> fetch -> extract -> validate -> dedupe -> verify,
with one gap-fill loop back to discover when too few rows were found.

Pages stream through extract/validate/merge as soon as they are fetched, so
rows appear in the UI while the run is still going.
"""

import asyncio

from sqlmodel import Session

from .. import llm
from ..config import BROWSER_ENABLED
from ..db import engine
from ..events import emit
from ..models import Provenance, Record, Run, ScreenshotBlob, Source, Workflow, now
from ..services import crawler, robots
from .discover import discover
from .extract import extract
from .merge import Cluster, Merger
from .orchestrator import set_progress, update_run
from .plan import Intent
from .validate import validate

MAX_ITERATIONS = 2  # the first pass plus one gap-fill loop
SCREENSHOTS_PER_PASS = 12
LATER_STEPS = ["fetch", "extract", "validate", "dedupe", "verify"]


def record_payload(rec: Record) -> dict:
    return {"id": rec.id, "data": rec.data, "status": rec.status, "confidence": rec.confidence,
            "field_meta": rec.field_meta}


class LiveRun:
    def __init__(self, run_id: int, intent: Intent):
        self.run_id = run_id
        self.intent = intent
        self.usage = llm.Usage()
        self.merger = Merger(intent)
        self.stats = {"sources": 0, "fetched": 0, "blocked": 0, "failed": 0, "raw": 0,
                      "duplicates": 0, "clean": 0, "rejected": 0}
        self.seen_urls: set[str] = set()
        self._prov_keys: set[tuple[int, int, str]] = set()

    # -- helpers ---------------------------------------------------------
    def log(self, step: str | None, message: str, level: str = "info") -> None:
        emit(self.run_id, "log", step, level=level, message=message)

    def push_stats(self) -> None:
        self.stats["clean"] = len(self.merger.clusters)
        self.stats["duplicates"] = max(0, self.stats["raw"] - self.stats["clean"])
        emit(self.run_id, "stats", **self.stats, llm_calls=self.usage.calls, llm_cached=self.usage.cached)

    def persist(self, cluster: Cluster, source_id: int, cells: dict) -> None:
        with Session(engine) as s:
            rec = s.get(Record, cluster.record_id) if cluster.record_id else Record(run_id=self.run_id)
            rec.data, rec.status = cluster.data, cluster.status
            rec.confidence, rec.field_meta = cluster.confidence, cluster.field_meta
            s.add(rec)
            s.commit()
            s.refresh(rec)
            cluster.record_id = rec.id
            for field, cell in cells.items():
                key = (rec.id, source_id, field)
                if key in self._prov_keys:
                    continue
                self._prov_keys.add(key)
                s.add(Provenance(record_id=rec.id, source_id=source_id, field=field,
                                 value=str(cell["value"]), quote=cell["quote"]))
            s.commit()
            emit(self.run_id, "row", "verify", record=record_payload(rec))

    # -- steps -----------------------------------------------------------
    async def handle_page(self, src: Source, page: crawler.Page) -> None:
        try:
            records, dropped = await extract(page.text, src.url, self.intent, self.usage)
        except llm.LLMError as e:
            self.log("extract", f"Extraction failed for {src.domain}: {e}", "warn")
            return
        self.stats["rejected"] += dropped
        kept = 0
        for rec in records:
            cells = validate(rec, self.intent)
            if cells is None:
                continue
            kept += 1
            self.stats["raw"] += 1
            cluster = self.merger.add(src.id, src.domain, cells)
            self.persist(cluster, src.id, cells)
        msg = f"{src.domain}: {kept} rows"
        if dropped:
            msg += f", {dropped} values dropped (quote not found on page)"
        self.log("extract", msg)
        self.push_stats()

    def mark_source(self, src: Source, page: crawler.Page) -> None:
        with Session(engine) as s:
            row = s.get(Source, src.id)
            if page.ok:
                row.status, row.fetched_at = "fetched", now()
                row.markdown_path = str(crawler.page_path(src.url))
                row.page_text = page.text[:300_000]
                if page.title and not row.title:
                    row.title = page.title[:300]
            else:
                row.status = "failed"
            s.add(row)
            s.commit()
        self.attach_screenshot(src)

    def attach_screenshot(self, src: Source) -> None:
        shot = crawler.find_screenshot(src.url)
        if not shot:
            return
        with Session(engine) as s:
            row = s.get(Source, src.id)
            if row.screenshot_path == shot.name:
                return
            row.screenshot_path = shot.name
            s.add(row)
            if not s.get(ScreenshotBlob, shot.name):
                s.add(ScreenshotBlob(name=shot.name, data=shot.read_bytes(),
                                     content_type="image/png" if shot.suffix == ".png" else "image/jpeg"))
            s.commit()

    async def process(self, sources: list[Source], iteration: int) -> None:
        for step in LATER_STEPS:
            emit(self.run_id, "step", step, status="running", iteration=iteration)

        # 1. Fast HTTP fetch of every permitted page.
        async with robots.new_client() as client:
            pages = await asyncio.gather(*(crawler.fetch(s.url, client) for s in sources))
        fetched = [(s, p) for s, p in zip(sources, pages) if p.ok]
        # Too little text (JS-rendered) or bot-blocked plain HTTP: try a real browser.
        needs_browser = [s for s, p in zip(sources, pages)
                         if not p.ok and (p.error is None or p.error in ("HTTP 403", "HTTP 429"))]
        for s, p in zip(sources, pages):
            if p.ok:
                self.stats["fetched"] += 1
                self.log("fetch", f"Fetched {s.url}" + (" (cached)" if p.via == "cache" else ""))
                self.mark_source(s, p)
            elif s not in needs_browser:
                self.stats["failed"] += 1
                self.log("fetch", f"Could not fetch {s.url}: {p.error}", "warn")
                self.mark_source(s, p)
        self.push_stats()

        # 2. Browser pass (JS pages + screenshots) runs while extraction starts.
        browser_task = asyncio.create_task(crawler.render(
            [s.url for s in needs_browser], [s.url for s, _ in fetched][:SCREENSHOTS_PER_PASS]))
        if needs_browser and BROWSER_ENABLED:
            self.log("fetch", f"Rendering {len(needs_browser)} JavaScript-heavy pages in a browser")

        await asyncio.gather(*(self.handle_page(s, p) for s, p in fetched))

        rendered = await browser_task
        late = []
        for s in needs_browser:
            p = rendered.get(s.url) or crawler.Page(url=s.url, error="browser render failed")
            if p.ok:
                self.stats["fetched"] += 1
                self.log("fetch", f"Rendered {s.url}")
                late.append((s, p))
            else:
                self.stats["failed"] += 1
                reason = p.error or "too little readable text, even in a browser"
                self.log("fetch", f"Could not fetch {s.url}: {reason}", "warn")
            self.mark_source(s, p)
        for s, _ in fetched:
            self.attach_screenshot(s)
        emit(self.run_id, "step", "fetch", status="done",
             counts={"fetched": self.stats["fetched"], "failed": self.stats["failed"]})
        await asyncio.gather(*(self.handle_page(s, p) for s, p in late))
        self.push_stats()

        n = len(self.merger.clusters)
        emit(self.run_id, "step", "extract", status="done", counts={"rows": self.stats["raw"]})
        emit(self.run_id, "step", "validate", status="done", counts={"dropped": self.stats["rejected"]})
        emit(self.run_id, "step", "dedupe", status="done", counts={"merged": self.stats["duplicates"]})
        verified = sum(c.status == "verified" for c in self.merger.clusters)
        conflicts = sum(c.status == "conflict" for c in self.merger.clusters)
        emit(self.run_id, "step", "verify", status="done",
             message=f"{n} rows · {verified} verified · {conflicts} conflicts")

    async def gapfill_queries(self) -> list[str]:
        names = [c.data.get(self.merger.id_field) for c in self.merger.clusters][:40]
        data = await llm.complete_json(
            "You improve web search strategies. Reply with JSON only: {\"queries\": [str, str, str]}",
            f"Goal: find more {self.intent.entity} matching: {'; '.join(self.intent.filters) or 'any'}.\n"
            f"Queries already tried: {self.intent.queries}\n"
            f"Already found: {names}\n"
            "Write 3 NEW, different search queries likely to surface list pages or directories "
            "with additional matching entities not yet found.",
            usage=self.usage, temperature=0.4,
        )
        qs = [q for q in data.get("queries", []) if isinstance(q, str) and q.strip()]
        return qs[:3]

    async def run(self) -> None:
        intent = self.intent
        emit(self.run_id, "step", "plan", status="running")
        emit(self.run_id, "plan", "plan", intent=intent.model_dump())
        emit(self.run_id, "step", "plan", status="done",
             message=f"{len(intent.fields)} fields, {len(intent.queries)} queries")
        set_progress(self.run_id, 0.08)

        queries = intent.queries
        for iteration in range(MAX_ITERATIONS):
            if iteration > 0:
                emit(self.run_id, "step", "gapfill", status="running")
                self.log("verify", f"Found {len(self.merger.clusters)}/{intent.target_count}. "
                                   "Gap-fill: writing new search queries")
                try:
                    queries = await self.gapfill_queries()
                except llm.LLMError as e:
                    self.log("verify", f"Gap-fill skipped: {e}", "warn")
                    queries = []
                emit(self.run_id, "step", "gapfill", status="done", message=f"{len(queries)} new queries")
                if not queries:
                    break

            emit(self.run_id, "step", "discover", status="running", iteration=iteration)
            sources = await discover(self.run_id, intent, queries, self.seen_urls, self.stats)
            allowed = [s for s in sources if s.robots_allowed]
            emit(self.run_id, "step", "discover", status="done" if allowed or iteration else "failed",
                 counts={"sources": len(allowed), "blocked": len(sources) - len(allowed)})
            set_progress(self.run_id, 0.2 + iteration * 0.4)
            if not allowed:
                if iteration == 0:
                    raise RuntimeError("No permitted sources found. Try broader wording or different queries.")
                break

            await self.process(allowed, iteration)
            set_progress(self.run_id, 0.55 + iteration * 0.4)
            if len(self.merger.clusters) >= intent.target_count:
                break

        final = {**self.stats, **{f"llm_{k}": v for k, v in self.usage.as_dict().items()}}
        update_run(self.run_id, stats=final)
        emit(self.run_id, "stats", **final)
        self.log(None, f"Done: {self.stats['raw']} raw rows -> {len(self.merger.clusters)} clean, "
                       f"{self.stats['duplicates']} duplicates merged, "
                       f"{self.stats['rejected']} unverifiable values dropped")


async def run_live(run_id: int) -> None:
    with Session(engine) as s:
        run = s.get(Run, run_id)
        wf = s.get(Workflow, run.workflow_id)
        intent = Intent.model_validate(wf.intent)
    await LiveRun(run_id, intent).run()
