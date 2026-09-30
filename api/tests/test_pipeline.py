"""Offline tests for extraction checks, validation, merging, evidence and export."""

import asyncio
import os
import tempfile

os.environ.setdefault("SCOUT_DATA_DIR", tempfile.mkdtemp(prefix="scout-test-"))

import pytest  # noqa: E402

from app import llm  # noqa: E402
from app.models import Provenance, Record  # noqa: E402
from app.pipeline import extract as extract_mod  # noqa: E402
from app.pipeline.extract import quote_in_page, value_in_quote  # noqa: E402
from app.pipeline.merge import Merger, entity_key  # noqa: E402
from app.pipeline.plan import Intent  # noqa: E402
from app.pipeline.validate import coerce, validate  # noqa: E402
from app.services import evidence, export  # noqa: E402

INTENT = Intent.model_validate({
    "entity": "AI startup",
    "fields": [
        {"name": "name", "type": "string"},
        {"name": "funding_stage", "type": "string"},
        {"name": "team_size", "type": "integer"},
        {"name": "website", "type": "url", "required": True},
    ],
    "queries": ["q"],
})

PAGE = """# Top AI startups in Bangalore

**Nimbus Labs** raised a Series A round last year and has about 45 employees.
Visit [nimbuslabs.ai](https://nimbuslabs.ai) to learn more.

Vectorleaf AI (Seed) is a 12-person team. Website: https://vectorleaf.example.com
"""


def test_quote_check_accepts_real_quotes_and_rejects_invented_ones():
    page = extract_mod.norm(PAGE)
    assert quote_in_page("Nimbus Labs raised a Series A round last year", page)  # markdown ** stripped
    assert not quote_in_page("Nimbus Labs raised a Series C round of $80M", page)
    assert value_in_quote("Series A", "string", "raised a Series A round")
    assert not value_in_quote("Series C", "string", "raised a Series A round")
    assert value_in_quote(45, "integer", "has about 45 employees")
    assert not value_in_quote(450, "integer", "has about 45 employees")
    assert value_in_quote("https://nimbuslabs.ai", "url", "[nimbuslabs.ai](https://nimbuslabs.ai)")


def test_extract_drops_hallucinated_values(monkeypatch):
    async def fake_llm(*_a, **_k):
        return {"records": [
            {"name": {"value": "Nimbus Labs", "quote": "Nimbus Labs raised a Series A round"},
             "funding_stage": {"value": "Series A", "quote": "raised a Series A round last year"},
             "team_size": {"value": 450, "quote": "has about 45 employees"},  # value not in quote
             "website": {"value": "https://nimbuslabs.ai", "quote": "Visit [nimbuslabs.ai](https://nimbuslabs.ai)"}},
            {"name": {"value": "Ghost AI", "quote": "Ghost AI is the fastest growing startup"}},  # not on page
        ]}

    monkeypatch.setattr(llm, "complete_json", fake_llm)
    records, dropped = asyncio.run(extract_mod.extract(PAGE, "https://x.test", INTENT, llm.Usage()))
    assert len(records) == 1
    assert set(records[0]) == {"name", "funding_stage", "website"}
    assert dropped == 2


@pytest.mark.parametrize("value,ftype,expected", [
    ("~45 employees", "integer", 45),
    ("1,200+", "integer", 1200),
    ("45 members", "integer", 45),
    ("2.5 crore", "number", 25_000_000),
    ("$1.2M", "number", 1_200_000),
    ("nimbuslabs.ai", "url", "https://nimbuslabs.ai"),
    ("not a url", "url", None),
    ("Mailto:Hi@Nimbus.AI", "email", "hi@nimbus.ai"),
    ("Yes", "boolean", True),
    ("  Series   A ", "string", "Series A"),
])
def test_coerce(value, ftype, expected):
    assert coerce(value, ftype) == expected


def test_validate_drops_rows_missing_required_fields():
    assert validate({"name": {"value": "X", "quote": "X"}}, INTENT) is None


def cells(**kw):
    return {k: {"value": v, "quote": str(v)} for k, v in kw.items()}


def test_merge_verifies_agreement_and_flags_conflicts():
    m = Merger(INTENT)
    m.add(1, "a.com", cells(name="Nimbus Labs Pvt Ltd", funding_stage="Series A", website="https://nimbuslabs.ai"))
    c = m.add(2, "b.com", cells(name="Nimbus Labs", funding_stage="Series A", website="https://www.nimbuslabs.ai/"))
    assert len(m.clusters) == 1
    assert c.status == "verified" and c.field_meta["funding_stage"]["sources"] == 2

    c = m.add(3, "c.com", cells(name="NIMBUS LABS", funding_stage="Series B", website="https://nimbuslabs.ai"))
    assert c.status == "conflict"
    assert c.data["funding_stage"] == "Series A"  # majority wins
    assert c.field_meta["funding_stage"]["alternatives"] == ["Series B"]

    other = m.add(1, "a.com", cells(name="Vectorleaf AI", website="https://vectorleaf.example.com"))
    assert len(m.clusters) == 2 and other.status == "single"


def test_same_page_twice_is_not_extra_evidence():
    m = Merger(INTENT)
    m.add(1, "a.com", cells(name="Nimbus", website="https://n.ai"))
    c = m.add(1, "a.com", cells(name="Nimbus", website="https://n.ai"))
    assert c.status == "single" and len(c.sightings) == 1


def test_entity_key_strips_company_suffixes():
    assert entity_key("Nimbus Labs Pvt. Ltd.") == entity_key("nimbus") == "nimbus"


def test_evidence_locates_quote_with_context(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("Title\n\n" + PAGE, encoding="utf-8")
    ctx = evidence.locate("has about 45 employees", str(page))
    assert ctx["exact"] and ctx["match"] == "has about 45 employees" and "Series A" in ctx["before"]


def test_export_formats_and_diff():
    intent = INTENT.model_dump()
    recs = [Record(id=1, run_id=1, data={"name": "Nimbus", "website": "https://n.ai"}, status="verified",
                   confidence=0.75)]
    prov = [Provenance(record_id=1, source_id=9, field="name", value="Nimbus", quote="Nimbus")]
    csv_bytes = export.build("csv", intent, recs, prov, {9: "https://src.test"})
    assert b"name,funding_stage,team_size,website,trust,confidence,sources" in csv_bytes
    assert b"https://src.test" in csv_bytes
    assert export.build("xlsx", intent, recs, prov, {9: "https://src.test"})[:2] == b"PK"  # zip container
    assert b'"evidence"' in export.build("json", intent, recs, prov, {9: "https://src.test"})

    after = recs + [Record(id=2, run_id=2, data={"name": "Vectorleaf"}, status="single", confidence=0.5)]
    d = export.diff("name", recs, after)
    assert d["added"] == ["Vectorleaf"] and d["removed"] == [] and d["unchanged"] == 1


@pytest.mark.parametrize("a,b,same", [
    ("Bengaluru", "Bangalore", True),
    ("Bengaluru, Karnataka", "Bangalore", True),
    ("Vivek Raghavan & Pratyush Kumar", "Vivek Raghavan and Pratyush Kumar", True),
    ("Series A round", "Series A", True),
    ("Series A", "Series B", False),
    ("Seed", "Pre-seed", False),
    ("Mumbai", "Bangalore", False),
])
def test_same_text_aliases_and_filler(a, b, same):
    from app.pipeline.merge import same_text
    assert same_text(a, b) is same


def test_browser_can_be_disabled(monkeypatch):
    from app.services import crawler

    monkeypatch.setattr(crawler, "BROWSER_ENABLED", False)
    out = asyncio.run(crawler.render(["https://js.test/page"], ["https://js.test/shot"]))
    assert list(out) == ["https://js.test/page"]
    assert not out["https://js.test/page"].ok and "browser disabled" in out["https://js.test/page"].error
    assert not crawler.screenshot_file("https://js.test/shot").exists()
