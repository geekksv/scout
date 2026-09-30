"""Free web search via the ddgs metasearch library, cached on disk."""

import asyncio
import hashlib
import json
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ddgs import DDGS

from ..config import CACHE_DIR, SEARCH_ENGINES

log = logging.getLogger("scout.search")

_CACHE = CACHE_DIR / "search"
_CACHE.mkdir(parents=True, exist_ok=True)
_lock = asyncio.Lock()  # one query at a time keeps us under the engines' rate limits

_TRACKING_PREFIXES = ("utm_", "mc_")
_TRACKING_KEYS = {"fbclid", "gclid", "msclkid", "vjk", "ref", "ref_src", "trk", "si"}


def _is_tracking(key: str) -> bool:
    key = key.lower()
    return key in _TRACKING_KEYS or key.startswith(_TRACKING_PREFIXES)


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query) if not _is_tracking(k)]
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower() or "https", host, path, urlencode(query), ""))


async def search(query: str, max_results: int = 10, region: str = "wt-wt") -> list[dict]:
    """[{title, url, snippet}] for a query; [] if the search engines refuse.

    The region matters: without it, a cloud server's results follow the server's
    country rather than the request's.
    """
    key = hashlib.sha256(f"{query}|{max_results}|{region}|{SEARCH_ENGINES}".encode()).hexdigest()
    path = _CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    async with _lock:
        try:
            raw = await asyncio.to_thread(lambda: DDGS().text(
                query, max_results=max_results, region=region, backend=SEARCH_ENGINES))
        except Exception as e:  # ddgs raises its own types for rate limits and timeouts
            log.warning("search failed for %r: %s", query, e)
            return []
        await asyncio.sleep(1.0)

    results = [
        {"title": r.get("title", ""), "url": r["href"], "snippet": r.get("body", "")}
        for r in raw
        if r.get("href", "").startswith("http")
    ]
    path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    return results
