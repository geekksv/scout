"""Fetch pages and turn them into clean text.

httpx + trafilatura handles most pages quickly. Playwright is used for pages
that need JavaScript and for screenshots; it runs in a worker thread with the
sync API so it works regardless of the server's event loop type (Windows).
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
import trafilatura

from ..config import BROWSER_ENABLED, CACHE_DIR, SCREENSHOT_DIR
from .robots import USER_AGENT

log = logging.getLogger("scout.crawler")

PAGES_DIR = CACHE_DIR / "pages"
PAGES_DIR.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 3_000_000
MIN_TEXT = 400  # below this, the page probably needs JavaScript

_fetch_sem = asyncio.Semaphore(6)
BROWSER_HEADERS = {
    "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {USER_AGENT}",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
    "Accept-Language": "en-IN,en;q=0.9",
}


@dataclass
class Page:
    url: str
    text: str = ""
    title: str = ""
    error: str | None = None
    via: str = "http"  # http | browser | cache

    @property
    def ok(self) -> bool:
        return len(self.text) >= MIN_TEXT


def _key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def page_path(url: str) -> Path:
    return PAGES_DIR / f"{_key(url)}.md"


def html_to_text(html: str, url: str) -> tuple[str, str]:
    text = trafilatura.extract(
        html, url=url, output_format="markdown", include_links=True, include_tables=True,
        favor_recall=True, deduplicate=True,
    ) or ""
    meta = trafilatura.extract_metadata(html)
    return text.strip(), (meta.title if meta and meta.title else "")


def _save(page: Page) -> None:
    page_path(page.url).write_text(f"{page.title}\n\n{page.text}", encoding="utf-8")


def load_cached(url: str) -> Page | None:
    p = page_path(url)
    if not p.exists():
        return None
    title, _, text = p.read_text(encoding="utf-8").partition("\n\n")
    return Page(url=url, text=text, title=title, via="cache")


async def fetch(url: str, client: httpx.AsyncClient) -> Page:
    cached = load_cached(url)
    if cached and cached.ok:
        return cached
    async with _fetch_sem:
        try:
            resp = await client.get(url, timeout=15, follow_redirects=True, headers=BROWSER_HEADERS)
        except httpx.HTTPError as e:
            return Page(url=url, error=f"{type(e).__name__}")
    if resp.status_code >= 400:
        return Page(url=url, error=f"HTTP {resp.status_code}")
    if "html" not in resp.headers.get("content-type", "html"):
        return Page(url=url, error="not an HTML page")
    html = resp.content[:MAX_BYTES].decode(resp.encoding or "utf-8", errors="replace")
    text, title = await asyncio.to_thread(html_to_text, html, url)
    page = Page(url=url, text=text, title=title)
    if page.ok:
        _save(page)
    return page


def _launch(pw):
    """Playwright's bundled Chromium if downloaded, else the installed Chrome or Edge."""
    errors = []
    for channel in (None, "chrome", "msedge"):
        try:
            return pw.chromium.launch(channel=channel) if channel else pw.chromium.launch()
        except Exception as e:
            errors.append(f"{channel or 'bundled'}: {str(e).splitlines()[0]}")
    raise RuntimeError("; ".join(errors))


def _render_batch(urls: list[str], shots: dict[str, Path], need_text: set[str]) -> dict[str, Page]:
    """Runs in a thread. Renders pages that need JS and/or takes screenshots."""
    from playwright.sync_api import sync_playwright

    out: dict[str, Page] = {}
    with sync_playwright() as pw:
        browser = _launch(pw)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, user_agent=BROWSER_HEADERS["User-Agent"])
        for url in urls:
            page = ctx.new_page()
            try:
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                if url in need_text:
                    text, title = html_to_text(page.content(), url)
                    out[url] = Page(url=url, text=text, title=title or page.title(), via="browser")
                if url in shots:
                    page.screenshot(path=str(shots[url]), type="jpeg", quality=70)
            except Exception as e:  # one bad page must not stop the batch
                log.info("render failed for %s: %s", url, e)
                if url in need_text:
                    out[url] = Page(url=url, error="browser render failed")
            finally:
                page.close()
        browser.close()
    for p in out.values():
        if p.ok:
            _save(p)
    return out


def screenshot_file(url: str) -> Path:
    return SCREENSHOT_DIR / f"{_key(url)}.jpg"


async def render(urls_needing_text: list[str], urls_to_screenshot: list[str]) -> dict[str, Page]:
    """Browser pass. Returns rendered pages; screenshots land in SCREENSHOT_DIR."""
    if not BROWSER_ENABLED:
        return {u: Page(url=u, error="needs JavaScript (browser disabled on this server)") for u in urls_needing_text}
    shots = {u: screenshot_file(u) for u in urls_to_screenshot if not screenshot_file(u).exists()}
    urls = list(dict.fromkeys([*urls_needing_text, *shots]))
    if not urls:
        return {}
    try:
        return await asyncio.to_thread(_render_batch, urls, shots, set(urls_needing_text))
    except Exception as e:  # Playwright missing or browser not installed: degrade gracefully
        log.warning("browser pass unavailable: %s", e)
        return {u: Page(url=u, error="browser unavailable") for u in urls_needing_text}
