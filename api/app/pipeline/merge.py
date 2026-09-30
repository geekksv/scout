"""Dedupe + verify: cluster sightings of the same entity and cross-check fields.

A cluster collects every sighting of one entity across pages. For each field
we group the values that agree; distinct domains backing the winning value
decide the trust level:
  verified  some field is backed by 2+ independent domains, with no disagreement
  conflict  independent domains disagree on a field's value
  single    everything comes from one domain
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .extract import norm
from .plan import Intent

NAME_MATCH = 90
_SUFFIXES = re.compile(
    r"\b(private limited|pvt\.? ltd\.?|pvt|ltd\.?|limited|inc\.?|llc|llp|corp\.?|co\.?|technologies|technology|labs?|ai|india)\b"
)


def entity_key(name) -> str:
    s = norm(name)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    stripped = _SUFFIXES.sub(" ", s)
    s = " ".join(stripped.split()) or " ".join(s.split())
    return s


_ALIASES = {
    "bengaluru": "bangalore", "bombay": "mumbai", "gurugram": "gurgaon", "madras": "chennai",
    "calcutta": "kolkata", "&": "and", "usa": "us", "uk": "gb",
}
# Words that add no information when one value merely has more of them.
_FILLER = {"karnataka", "maharashtra", "india", "city", "the", "funding", "round", "stage",
           "inc", "ltd", "pvt", "limited", "co", "and", "state"}


def _tokens(s) -> list[str]:
    return [_ALIASES.get(t, t) for t in re.findall(r"[a-z0-9&]+", norm(s))]


def same_text(a, b) -> bool:
    """Equal up to aliases ("Bengaluru" = "Bangalore") and filler ("Series A round" = "Series A")."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    sa, sb = set(ta), set(tb)
    small, big = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    if small <= big and not (big - small - _FILLER):
        return True
    return fuzz.token_sort_ratio(" ".join(ta), " ".join(tb)) >= 90


def same_value(a, b, ftype: str, is_id: bool = False) -> bool:
    if is_id:  # "Nimbus Labs Pvt Ltd" and "Nimbus Labs" name the same entity
        ka, kb = entity_key(a), entity_key(b)
        return ka == kb or fuzz.token_sort_ratio(ka, kb) >= NAME_MATCH
    if ftype in ("integer", "number"):
        return abs(float(a) - float(b)) <= max(1.0, 0.1 * max(abs(float(a)), abs(float(b))))
    if ftype == "url":
        strip = lambda u: re.sub(r"^https?://(www\.)?", "", str(u).lower()).rstrip("/")  # noqa: E731
        return strip(a) == strip(b)
    if ftype == "boolean":
        return a == b
    return same_text(a, b)


@dataclass
class Sighting:
    source_id: int
    domain: str
    cells: dict  # field -> {"value", "quote"}


@dataclass
class Cluster:
    key: str
    sightings: list[Sighting] = field(default_factory=list)
    record_id: int | None = None
    data: dict = field(default_factory=dict)
    field_meta: dict = field(default_factory=dict)
    status: str = "single"
    confidence: float = 0.5
    resolved: dict = field(default_factory=dict)  # field -> value chosen by a person

    def recompute(self, intent: Intent) -> None:
        data, meta = {}, {}
        any_verified, any_conflict = False, False
        for i, f in enumerate(intent.fields):
            groups: list[dict] = []  # {"value", "domains": set}
            for s in self.sightings:
                cell = s.cells.get(f.name)
                if not cell:
                    continue
                for g in groups:
                    if same_value(g["value"], cell["value"], f.type, is_id=i == 0):
                        g["domains"].add(s.domain)
                        break
                else:
                    groups.append({"value": cell["value"], "domains": {s.domain}})
            if not groups:
                continue
            groups.sort(key=lambda g: -len(g["domains"]))
            best = groups[0]
            n = len(best["domains"])
            # Disagreement only counts when a different domain backs the other value.
            conflict = len(groups) > 1 and any(g["domains"] - best["domains"] for g in groups[1:])
            if f.name in self.resolved:
                data[f.name] = self.resolved[f.name]
                conflict = False
            else:
                data[f.name] = best["value"]
            meta[f.name] = {"sources": n, "conflict": conflict,
                            "alternatives": [g["value"] for g in groups[1:]][:3] if conflict else []}
            any_verified |= n >= 2
            any_conflict |= conflict
        max_domains = max((m["sources"] for m in meta.values()), default=1)
        self.data, self.field_meta = data, meta
        if any_conflict:
            self.status, self.confidence = "conflict", 0.4
        elif any_verified:
            self.status, self.confidence = "verified", min(1.0, 0.5 + 0.25 * (max_domains - 1))
        else:
            self.status, self.confidence = "single", 0.5


class Merger:
    def __init__(self, intent: Intent):
        self.intent = intent
        self.id_field = intent.fields[0].name
        self.clusters: list[Cluster] = []

    def add(self, source_id: int, domain: str, cells: dict) -> Cluster:
        key = entity_key(cells[self.id_field]["value"])
        cluster = next((c for c in self.clusters if c.key == key), None)
        if cluster is None:
            cluster = next(
                (c for c in self.clusters if len(key) > 3 and fuzz.token_sort_ratio(c.key, key) >= NAME_MATCH),
                None,
            )
        if cluster is None:
            cluster = Cluster(key=key)
            self.clusters.append(cluster)
        # The same page listing an entity twice is not extra evidence.
        existing = next((s for s in cluster.sightings if s.source_id == source_id), None)
        if existing:
            for k, v in cells.items():
                existing.cells.setdefault(k, v)
        else:
            cluster.sightings.append(Sighting(source_id, domain, cells))
        cluster.recompute(self.intent)
        return cluster
