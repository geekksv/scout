"""A scripted run with fictional data.

It drives the UI end to end (graph animation, streaming rows, provenance)
without spending LLM quota or needing the network. All companies and URLs are
made up and use reserved example domains.
"""

import asyncio
import random
from urllib.parse import urlparse

from sqlmodel import Session

from ..db import engine
from ..events import emit
from ..models import Provenance, Record, Source, Workflow, now
from .orchestrator import set_progress, update_run

DEMO_INTENT = {
    "entity": "AI startup",
    "fields": [
        {"name": "name", "type": "string", "required": True, "description": "Company name"},
        {"name": "funding_stage", "type": "string", "required": False, "description": "Latest round"},
        {"name": "team_size", "type": "integer", "required": False, "description": "Employees"},
        {"name": "careers_page", "type": "url", "required": True, "description": "Careers URL"},
    ],
    "filters": ["based in Bangalore", "hiring ML engineers"],
    "target_count": 12,
    "queries": [
        "AI startups Bangalore hiring machine learning engineer",
        "Bangalore generative AI startup careers ML",
        "Series A AI companies Bengaluru jobs",
    ],
}

_COMPANIES = [
    ("Nimbus Labs", "Series A", 45),
    ("Vectorleaf AI", "Seed", 18),
    ("Kaveri Robotics", "Series B", 120),
    ("Tessellate", "Series A", 60),
    ("Monsoon Data", "Seed", 12),
    ("Garuda Vision", "Series B", 150),
    ("Lotus Neural", "Pre-seed", 7),
    ("Indigo Signal", "Series A", 38),
    ("Coralgrid", "Seed", 22),
    ("Saffron Speech", "Series C", 310),
    ("Parrot Ops", "Series A", 51),
    ("Banyan Health AI", "Seed", 26),
]

_SOURCE_DOMAINS = [
    "startups.example.com",
    "jobs.example.org",
    "funding-news.example.net",
    "techweekly.example.com",
    "careers.example.org",
    "blocked.example.net",
]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "")


async def _pause(lo: float = 0.25, hi: float = 0.6) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


async def run_demo(run_id: int) -> None:
    rnd = random.Random(run_id)

    # plan
    emit(run_id, "step", "plan", status="running")
    emit(run_id, "log", "plan", level="info", message="Reading the request and designing a schema")
    await _pause(0.8, 1.2)
    emit(run_id, "plan", "plan", intent=DEMO_INTENT)
    emit(run_id, "step", "plan", status="done", message=f"{len(DEMO_INTENT['fields'])} fields, 3 queries")
    set_progress(run_id, 0.08)

    sources: list[Source] = []
    raw_count = 0
    stats = {"raw": 0, "clean": 0, "duplicates": 0, "sources": 0, "fetched": 0, "blocked": 0}
    companies = _COMPANIES[:]
    rnd.shuffle(companies)
    batches = [companies[:8], companies[8:]]  # second batch arrives via the gap-fill loop

    for iteration, batch in enumerate(batches):
        # discover
        if iteration > 0:
            emit(run_id, "step", "gapfill", status="done", message="3 new queries")
        emit(run_id, "step", "discover", status="running", iteration=iteration)
        new_sources = []
        with Session(engine) as s:
            for i, domain in enumerate(_SOURCE_DOMAINS if iteration == 0 else _SOURCE_DOMAINS[:3]):
                url = f"https://{domain}/list/{iteration}-{i}"
                src = Source(run_id=run_id, url=url, domain=urlparse(url).netloc,
                             title=f"{domain.split('.')[0].title()} directory")
                s.add(src)
                new_sources.append(src)
            s.commit()
            for src in new_sources:
                s.refresh(src)
        for src in new_sources:
            await _pause(0.1, 0.25)
            emit(run_id, "log", "discover", level="info", message=f"Found {src.url}")
        sources.extend(new_sources)
        stats["sources"] = len(sources)
        emit(run_id, "stats", **stats)
        emit(run_id, "step", "discover", status="done", counts={"sources": len(new_sources)})
        set_progress(run_id, 0.15 + iteration * 0.4)

        # fetch
        emit(run_id, "step", "fetch", status="running", iteration=iteration)
        with Session(engine) as s:
            for src in new_sources:
                await _pause(0.15, 0.35)
                src = s.get(Source, src.id)
                if src.domain.startswith("blocked"):
                    src.robots_allowed, src.status = False, "blocked"
                    stats["blocked"] += 1
                    emit(run_id, "log", "fetch", level="warn", message=f"robots.txt disallows {src.url}, skipped")
                else:
                    src.status, src.fetched_at = "fetched", now()
                    stats["fetched"] += 1
                    emit(run_id, "log", "fetch", level="info", message=f"Fetched {src.url}")
                s.add(src)
                s.commit()
                emit(run_id, "stats", **stats)
        emit(run_id, "step", "fetch", status="done", counts={"fetched": stats["fetched"]})
        usable = [x for x in new_sources if not x.domain.startswith("blocked")]

        # extract: each company is seen on 1-3 sources, so raw > clean
        emit(run_id, "step", "extract", status="running", iteration=iteration)
        sightings = []
        for name, stage, size in batch:
            seen_on = rnd.sample(usable, k=rnd.randint(1, min(3, len(usable))))
            for src in seen_on:
                sightings.append((name, stage, size, src))
                raw_count += 1
                stats["raw"] = raw_count
                await _pause(0.05, 0.15)
                emit(run_id, "stats", **stats)
        emit(run_id, "log", "extract", level="info",
             message=f"Extracted {len(sightings)} candidate rows, every field backed by a quote")
        emit(run_id, "step", "extract", status="done", counts={"raw": len(sightings)})

        # validate
        emit(run_id, "step", "validate", status="running", iteration=iteration)
        await _pause(0.5, 0.8)
        emit(run_id, "step", "validate", status="done", message="All rows passed schema checks")

        # dedupe + verify, streaming merged rows into the grid
        emit(run_id, "step", "dedupe", status="running", iteration=iteration)
        await _pause(0.4, 0.7)
        emit(run_id, "step", "dedupe", status="done")
        emit(run_id, "step", "verify", status="running", iteration=iteration)
        for name, stage, size in batch:
            seen = [x[3] for x in sightings if x[0] == name]
            conflict = len(seen) >= 2 and rnd.random() < 0.2
            status = "conflict" if conflict else ("verified" if len(seen) >= 2 else "single")
            confidence = 0.4 if conflict else min(1.0, 0.5 + 0.25 * (len(seen) - 1))
            data = {"name": name, "funding_stage": stage, "team_size": size,
                    "careers_page": f"https://{_slug(name)}.example.com/careers"}
            with Session(engine) as s:
                rec = Record(run_id=run_id, data=data, status=status, confidence=confidence)
                s.add(rec)
                s.commit()
                s.refresh(rec)
                for j, src in enumerate(seen):
                    alt_stage = "Series B" if (conflict and j == 1 and stage != "Series B") else stage
                    for field, value in data.items():
                        v = alt_stage if field == "funding_stage" else value
                        s.add(Provenance(
                            record_id=rec.id, source_id=src.id, field=field, value=str(v),
                            quote=f"{name} ({alt_stage}, ~{size} people) is hiring ML engineers in Bangalore."
                            if field != "careers_page" else f"Apply at {value}",
                        ))
                s.commit()
                emit(run_id, "row", "verify", record={"id": rec.id, "data": data, "status": status,
                                                     "confidence": confidence})
            stats["clean"] += 1
            stats["duplicates"] = raw_count - stats["clean"]
            emit(run_id, "stats", **stats)
            await _pause(0.15, 0.3)
        emit(run_id, "step", "verify", status="done",
             counts={"clean": stats["clean"]})
        set_progress(run_id, 0.5 + iteration * 0.45)

        if iteration == 0:
            target = DEMO_INTENT["target_count"]
            emit(run_id, "log", "verify", level="info",
                 message=f"Found {stats['clean']}/{target}. Gap-fill: writing new search queries")
            emit(run_id, "step", "gapfill", status="running")
            await _pause(0.6, 0.9)

    update_run(run_id, stats=stats)
    emit(run_id, "log", None, level="info",
         message=f"Done: {stats['raw']} raw -> {stats['clean']} clean, {stats['duplicates']} duplicates merged")


def create_demo_workflow(session: Session, prompt: str) -> Workflow:
    wf = Workflow(prompt=prompt, intent=DEMO_INTENT)
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf
