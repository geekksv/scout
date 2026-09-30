"""Web search, cached on disk.

Tavily (free API key, built for servers) when TAVILY_API_KEY is set, otherwise
the keyless ddgs metasearch library. ddgs works well from home connections but
search engines often answer cloud servers with generic pages, so hosted
deployments should set a Tavily key.
"""

import asyncio
import hashlib
import json
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from ddgs import DDGS

from ..config import CACHE_DIR, SEARCH_ENGINES, TAVILY_API_KEY

log = logging.getLogger("scout.search")

_CACHE = CACHE_DIR / "search"
_CACHE.mkdir(parents=True, exist_ok=True)
_lock = asyncio.Lock()  # one query at a time keeps us under the engines' rate limits

_TRACKING_PREFIXES = ("utm_", "mc_")
_TRACKING_KEYS = {"fbclid", "gclid", "msclkid", "vjk", "ref", "ref_src", "trk", "si"}

# ddgs region code -> Tavily country name (Tavily boosts results from that country).
_COUNTRIES = {
    "in": "india", "us": "united states", "uk": "united kingdom", "ca": "canada",
    "au": "australia", "sg": "singapore", "de": "germany", "fr": "france", "ae": "united arab emirates",
}


def _is_tracking(key: str) -> bool:
    key = key.lower()
    return key in _TRACKING_KEYS or key.startswith(_TRACKING_PREFIXES)


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query) if not _is_tracking(k)]
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower() or "https", host, path, urlencode(query), ""))


def provider() -> str:
    return "tavily" if TAVILY_API_KEY else "ddgs"


async def _tavily(query: str, max_results: int, region: str) -> list[dict]:
    body: dict = {"query": query, "max_results": max_results, "search_depth": "basic", "topic": "general"}
    country = _COUNTRIES.get(region.split("-")[0])
    if country:
        body["country"] = country
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post("https://api.tavily.com/search", json=body,
                                     headers={"Authorization": f"Bearer {TAVILY_API_KEY}"})
    except httpx.HTTPError as e:
        log.warning("tavily failed for %r: %s", query, e)
        return []
    if resp.status_code != 200:
        log.warning("tavily HTTP %s for %r: %s", resp.status_code, query, resp.text[:200])
        return []
    return [
        {"title": r.get("title", ""), "url": r["url"], "snippet": (r.get("content") or "")[:1000]}
        for r in resp.json().get("results", [])
        if str(r.get("url", "")).startswith("http")
    ]


async def _ddgs(query: str, max_results: int, region: str) -> list[dict]:
    raw: list[dict] = []
    async with _lock:
        # Preferred engines first; if they refuse (common from cloud IPs), let ddgs pick any.
        for backend in dict.fromkeys([SEARCH_ENGINES, "auto"]):
            try:
                raw = await asyncio.to_thread(lambda b=backend: DDGS().text(
                    query, max_results=max_results, region=region, backend=b))
            except Exception as e:  # ddgs raises its own types for rate limits and timeouts
                log.warning("search via %s failed for %r: %s", backend, query, e)
                raw = []
            await asyncio.sleep(1.0)
            if raw:
                break
    return [
        {"title": r.get("title", ""), "url": r["href"], "snippet": r.get("body", "")}
        for r in raw
        if r.get("href", "").startswith("http")
    ]


async def search(query: str, max_results: int = 10, region: str = "wt-wt") -> list[dict]:
    """[{title, url, snippet}] for a query; [] if search is unavailable.

    The region matters: without it, a cloud server's results follow the server's
    country rather than the request's.
    """
    key = hashlib.sha256(f"{provider()}|{query}|{max_results}|{region}|{SEARCH_ENGINES}".encode()).hexdigest()
    path = _CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    results = await _tavily(query, max_results, region) if TAVILY_API_KEY else []
    if not results:  # no key, or Tavily is out of credits / down
        results = await _ddgs(query, max_results, region)
    if results:
        path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    return results
