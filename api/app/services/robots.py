"""robots.txt permission checks, following RFC 9309.

4xx on robots.txt means no restrictions; 5xx or an unreachable host means
assume everything is disallowed.
"""

import asyncio
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "ScoutBot/0.1 (+hackathon research crawler)"

_parsers: dict[str, RobotFileParser | bool] = {}
_locks: dict[str, asyncio.Lock] = {}


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


async def _load(origin: str, client: httpx.AsyncClient) -> RobotFileParser | bool:
    """A parser, or True (allow all) / False (disallow all)."""
    try:
        resp = await client.get(f"{origin}/robots.txt", timeout=8, follow_redirects=True)
    except httpx.HTTPError:
        return False
    if 400 <= resp.status_code < 500:
        return True
    if resp.status_code >= 500:
        return False
    parser = RobotFileParser()
    parser.parse(resp.text.splitlines())
    return parser


async def is_allowed(url: str, client: httpx.AsyncClient) -> bool:
    origin = _origin(url)
    if origin not in _parsers:
        lock = _locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin not in _parsers:
                _parsers[origin] = await _load(origin, client)
    rules = _parsers[origin]
    if isinstance(rules, bool):
        return rules
    return rules.can_fetch(USER_AGENT, url)


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT})
