"""Discover: run the plan's search queries, rank candidate pages, check robots.txt."""

import asyncio
from collections import defaultdict
from urllib.parse import urlsplit

from sqlmodel import Session

from ..db import engine
from ..events import emit
from ..models import Source
from ..services import robots
from ..services.search import normalize_url, search
from .plan import Intent

MAX_SOURCES = 25
RESULTS_PER_QUERY = 10

# Sites whose terms forbid automated collection, or that need a login.
DEFAULT_BLOCKED = {
    "linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com",
    "youtube.com", "pinterest.com", "quora.com", "glassdoor.com", "glassdoor.co.in",
    # Search engines' own ad and redirect links.
    "bing.com", "duckduckgo.com", "google.com", "yahoo.com", "yandex.com", "brave.com",
}


def domain_of(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def is_blocked(domain: str, blocked: set[str]) -> bool:
    return any(domain == b or domain.endswith("." + b) for b in blocked)


async def discover(
    run_id: int, intent: Intent, queries: list[str], seen_urls: set[str], stats: dict
) -> list[Source]:
    """Search, rank and robots-check new candidate URLs; returns persisted sources."""
    blocked = DEFAULT_BLOCKED | {d.lower().removeprefix("www.") for d in intent.blocked_domains}

    # Rank by how many queries surfaced a page, then by its best position.
    hits: dict[str, int] = defaultdict(int)
    best_rank: dict[str, int] = {}
    meta: dict[str, dict] = {}
    skipped_blocked = 0
    for q in queries:
        emit(run_id, "log", "discover", level="info", message=f'Searching: "{q}"')
        results = await search(q, RESULTS_PER_QUERY)
        if not results:
            emit(run_id, "log", "discover", level="warn", message=f'No results for "{q}"')
        for rank, r in enumerate(results):
            url = normalize_url(r["url"])
            if url in seen_urls:
                continue
            if is_blocked(domain_of(url), blocked):
                skipped_blocked += 1
                continue
            hits[url] += 1
            best_rank[url] = min(best_rank.get(url, rank), rank)
            meta.setdefault(url, r)

    ranked = sorted(hits, key=lambda u: (-hits[u], best_rank[u]))
    # Keep the source list diverse: at most 3 pages per domain.
    per_domain: dict[str, int] = defaultdict(int)
    chosen = []
    for url in ranked:
        d = domain_of(url)
        if per_domain[d] < 3:
            per_domain[d] += 1
            chosen.append(url)
        if len(chosen) == MAX_SOURCES:
            break

    if skipped_blocked:
        emit(run_id, "log", "discover", level="info",
             message=f"Skipped {skipped_blocked} results from blocked or login-only sites")

    async with robots.new_client() as client:
        allowed = await asyncio.gather(*(robots.is_allowed(u, client) for u in chosen))

    sources = []
    with Session(engine) as s:
        for url, ok in zip(chosen, allowed):
            r = meta[url]
            src = Source(
                run_id=run_id, url=url, domain=domain_of(url), title=r["title"][:300],
                snippet=r["snippet"][:1000], robots_allowed=ok,
                status="pending" if ok else "blocked",
            )
            s.add(src)
            sources.append(src)
        s.commit()
        for src in sources:
            s.refresh(src)

    for src in sources:
        seen_urls.add(src.url)
        if src.robots_allowed:
            emit(run_id, "log", "discover", level="info", message=f"Found {src.url}")
        else:
            emit(run_id, "log", "discover", level="warn", message=f"robots.txt disallows {src.url}")
    stats["sources"] = stats.get("sources", 0) + len(sources)
    stats["blocked"] = stats.get("blocked", 0) + sum(not s.robots_allowed for s in sources)
    emit(run_id, "stats", **stats)
    return sources
