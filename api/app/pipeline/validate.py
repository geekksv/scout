"""Validate: coerce extracted values to the planned types; drop incomplete rows."""

import re

from .plan import Intent

_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
_NUM = re.compile(r"-?\d[\d,]*(\.\d+)?")
_MULT = {"k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7,
         "million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9}
_SUFFIX = re.compile(r"(" + "|".join(sorted(_MULT, key=len, reverse=True)) + r")\b")


def _number(v) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).lower().replace("₹", "").replace("$", "")
    m = _NUM.search(s)
    if not m:
        return None
    n = float(m.group().replace(",", ""))
    # Word boundary so "45 members" isn't read as 45 million.
    tail = _SUFFIX.match(s[m.end():].lstrip())
    return n * _MULT[tail.group(1)] if tail else n


def coerce(value, ftype: str):
    """The value in its planned type, or None if it can't be one."""
    if ftype == "integer":
        n = _number(value)
        return int(round(n)) if n is not None else None
    if ftype == "number":
        return _number(value)
    if ftype == "url":
        s = str(value).strip().strip("<>()[]")
        m = re.search(r"https?://[^\s)\]]+", s)
        s = m.group() if m else s
        if not re.match(r"^https?://", s):
            s = "https://" + s.lstrip("/")
        return s.rstrip(".,;") if re.match(r"^https?://[^\s/]+\.[^\s/]+", s) else None
    if ftype == "email":
        s = str(value).strip().lower().removeprefix("mailto:")
        return s if _EMAIL.match(s) else None
    if ftype == "boolean":
        s = str(value).strip().lower()
        if s in ("true", "yes", "y", "1"):
            return True
        if s in ("false", "no", "n", "0"):
            return False
        return None
    if ftype == "date":
        s = str(value).strip()
        return s[:40] if re.search(r"\d", s) else None
    s = re.sub(r"\s+", " ", str(value)).strip().strip("*").strip()
    return s[:300] or None


def validate(record: dict, intent: Intent) -> dict | None:
    """{field: {"value", "quote"}} with typed values, or None if a required field is missing."""
    out = {}
    for f in intent.fields:
        cell = record.get(f.name)
        if not cell:
            continue
        v = coerce(cell["value"], f.type)
        if v is not None:
            out[f.name] = {"value": v, "quote": cell["quote"]}
    if any(f.required and f.name not in out for f in intent.fields):
        return None
    return out
