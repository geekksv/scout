"""Click-to-Proof: locate each quote inside its stored page text for a highlighted excerpt."""

import re
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

CONTEXT = 240


@lru_cache(maxsize=256)
def _page_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return re.sub(r"\s+", " ", p.read_text(encoding="utf-8"))


def locate(quote: str, markdown_path: str | None, fallback_text: str = "") -> dict:
    """{"before", "match", "after", "exact"} around the quote; the page text if stored, else the snippet."""
    text = _page_text(markdown_path) if markdown_path else ""
    text = text or re.sub(r"\s+", " ", fallback_text)
    q = re.sub(r"\s+", " ", quote).strip()
    if not text or not q:
        return {"before": "", "match": q, "after": "", "exact": False}

    pattern = r"\s*".join(re.escape(w) for w in q.split(" "))
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if m:
        start, end, exact = m.start(), m.end(), True
    else:
        # The extractor accepted it as a near-verbatim match; find where it aligns best.
        al = fuzz.partial_ratio_alignment(q.lower(), text.lower())
        if al is None or al.score < 80:
            return {"before": "", "match": q, "after": "", "exact": False}
        start, end, exact = al.dest_start, al.dest_end, False
    return {
        "before": ("…" if start > CONTEXT else "") + _plain(text[max(0, start - CONTEXT):start]),
        "match": _plain(text[start:end]),
        "after": _plain(text[end:end + CONTEXT]) + ("…" if end + CONTEXT < len(text) else ""),
        "exact": exact,
    }


def _plain(s: str) -> str:
    """Drop markdown emphasis markers so excerpts read like the page does."""
    return re.sub(r"\*\*|__", "", s)
