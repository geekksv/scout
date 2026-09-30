"""Extract: LLM pulls rows from a page; every value must carry a verbatim quote.

A value survives only if its quote really appears in the page text and the
value itself appears in (or is supported by) that quote. That is what makes
every cell traceable, and it filters out hallucinated values.
"""

import json
import re

from rapidfuzz import fuzz

from .. import llm
from ..config import GROQ_FAST_MODEL
from .plan import Intent

PAGE_CHAR_LIMIT = 9000
QUOTE_MATCH = 90  # partial_ratio needed for a quote to count as "in the page"

_WS = re.compile(r"\s+")
_TRANS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-",
                        "—": "-", " ": " ", "*": "", "_": " ", "#": "", "|": " "})


def norm(s: str) -> str:
    return _WS.sub(" ", str(s).translate(_TRANS)).strip().lower()


def relevant_text(text: str, intent: Intent, limit: int = PAGE_CHAR_LIMIT) -> str:
    """Trim long pages to the paragraphs most likely to mention matching entities."""
    if len(text) <= limit:
        return text
    words = {w for w in re.findall(r"[a-z0-9]{3,}", norm(
        " ".join([intent.entity, *intent.filters, *(f.name.replace("_", " ") for f in intent.fields)])))}
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    scored = sorted(range(len(paras)),
                    key=lambda i: -sum(w in norm(paras[i]) for w in words))
    keep, size = set(), 0
    for i in scored:
        if size + len(paras[i]) > limit:
            continue
        keep.add(i)
        size += len(paras[i])
    return "\n\n".join(paras[i] for i in sorted(keep))


_TOKEN = re.compile(r"[a-z0-9]+")


def quote_in_page(quote: str, page_norm: str) -> bool:
    q = norm(quote)
    if len(q) < 3:
        return False
    if q in page_norm:
        return True
    # Fuzzy matching only forgives formatting (markdown, punctuation, spacing):
    # every word and number of the quote must still be on the page, so an
    # altered value like "Series C" for "Series A" is rejected.
    page_tokens = set(_TOKEN.findall(page_norm))
    if not all(t in page_tokens for t in _TOKEN.findall(q)):
        return False
    return fuzz.partial_ratio(q, page_norm) >= QUOTE_MATCH


def value_in_quote(value, ftype: str, quote: str) -> bool:
    v, q = norm(value), norm(quote)
    if not v:
        return False
    if ftype in ("integer", "number"):
        digits = re.sub(r"[^0-9]", "", v)
        return bool(digits) and digits in re.sub(r"[^0-9]", "", q)
    if ftype == "url":
        host = re.sub(r"^https?://(www\.)?", "", v).split("/")[0]
        return host in q or v in q
    if ftype == "boolean":
        return True  # yes/no is a judgment about the quote, not a substring
    if v in q:
        return True
    # Every word of the value must be in the quote ("Series C" is not in "Series A").
    q_tokens = set(_TOKEN.findall(q))
    return all(t in q_tokens for t in _TOKEN.findall(v)) and fuzz.partial_ratio(v, q) >= 85


SYSTEM = """You are a precise data-extraction engine. Read the page and extract every {entity} it
describes or lists. The user is looking for: {filters}. Include an entity when the page presents it
in that context (e.g. a list of such entities); skip it only if the page shows it does NOT match.
Reply with JSON only:
{{"records": [{{"<field>": {{"value": <value or null>, "quote": "<exact text copied from the page>"}}}}]}}
Fields to extract:
{fields}
Rules:
- "quote" MUST be copied character-for-character from the page (at most 200 characters) and must contain or directly state the value. Never paraphrase a quote.
- If the page does not state a field, set it to null. Never guess or use outside knowledge.
- One record per distinct {entity}. Skip entities the page does not clearly describe.
- At most 25 records. If the page has no matching {entity}, return {{"records": []}}."""


async def extract(page_text: str, url: str, intent: Intent, usage: llm.Usage) -> tuple[list[dict], int]:
    """Returns (records, dropped_values). Each record: {field: {"value", "quote"}}."""
    text = relevant_text(page_text, intent)
    fields = "\n".join(
        f'- {f.name} ({f.type}{", required" if f.required else ""}): {f.description}' for f in intent.fields
    )
    system = SYSTEM.format(entity=intent.entity, filters="; ".join(intent.filters) or "none", fields=fields)
    data = await llm.complete_json(
        system, f"Page URL: {url}\n\nPage content:\n{text}",
        model=GROQ_FAST_MODEL, usage=usage, max_tokens=6000,
    )
    raw = data.get("records") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return [], 0

    page_norm = norm(text)
    types = {f.name: f.type for f in intent.fields}
    records, dropped = [], 0
    for rec in raw[:25]:
        if not isinstance(rec, dict):
            continue
        clean = {}
        for name, cell in rec.items():
            if name not in types or not isinstance(cell, dict):
                continue
            value, quote = cell.get("value"), cell.get("quote") or ""
            if value in (None, "", [], {}):
                continue
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else ", ".join(map(str, value))
            if quote_in_page(quote, page_norm) and value_in_quote(value, types[name], quote):
                clean[name] = {"value": value, "quote": str(quote).strip()[:300]}
            else:
                dropped += 1
        if clean:
            records.append(clean)
    return records, dropped
