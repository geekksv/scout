import asyncio
import os
import tempfile

os.environ.setdefault("SCOUT_DATA_DIR", tempfile.mkdtemp(prefix="scout-test-"))

import httpx  # noqa: E402
import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.pipeline.discover import DEFAULT_BLOCKED, is_blocked  # noqa: E402
from app.pipeline.plan import Intent  # noqa: E402
from app.services import robots  # noqa: E402
from app.services.search import normalize_url  # noqa: E402


def test_intent_normalizes_llm_output():
    intent = Intent.model_validate({
        "entity": "AI startup",
        "fields": [
            {"name": "Company Name", "type": "str", "required": False},
            {"name": "team size", "type": "int"},
            {"name": "careers-page", "type": "link"},
            {"name": "company_name", "type": "string"},  # duplicate after snake_casing
            {"name": "vibe", "type": "emoji"},  # unknown type falls back to string
        ],
        "queries": ["  q1 ", "q1", "", "q2"],
        "target_count": 500,
    })
    assert [f.name for f in intent.fields] == ["company_name", "team_size", "careers_page", "vibe"]
    assert [f.type for f in intent.fields] == ["string", "integer", "url", "string"]
    assert intent.fields[0].required is True  # identifying field is forced required
    assert intent.queries == ["q1", "q2"]
    assert intent.target_count == 50


def test_intent_rejects_empty_plan():
    with pytest.raises(ValidationError):
        Intent.model_validate({"entity": "x", "fields": [], "queries": ["q"]})


def test_normalize_url_strips_tracking_but_keeps_real_params():
    assert normalize_url("https://WWW.Example.com/jobs/?utm_source=x&page=2&vjk=abc#top") == \
        "https://example.com/jobs?page=2"
    assert normalize_url("https://example.com/?refinement=ai&ref=home") == "https://example.com/?refinement=ai"


def test_blocklist_matches_subdomains_only():
    assert is_blocked("in.linkedin.com", DEFAULT_BLOCKED)
    assert is_blocked("bing.com", DEFAULT_BLOCKED)
    assert not is_blocked("notlinkedin.com", DEFAULT_BLOCKED)


def _mock_client(status: int, body: str = "") -> httpx.AsyncClient:
    transport = httpx.MockTransport(lambda req: httpx.Response(status, text=body))
    return httpx.AsyncClient(transport=transport)


@pytest.mark.parametrize(
    "status,body,url,expected",
    [
        (200, "User-agent: *\nDisallow: /private", "https://a.test/private/x", False),
        (200, "User-agent: *\nDisallow: /private", "https://a.test/public", True),
        (404, "", "https://b.test/anything", True),  # RFC 9309: 4xx means no rules
        (503, "", "https://c.test/anything", False),  # 5xx means assume disallowed
    ],
)
def test_robots_rules(status, body, url, expected):
    robots._parsers.clear()

    async def check():
        async with _mock_client(status, body) as client:
            return await robots.is_allowed(url, client)

    assert asyncio.run(check()) is expected


def test_relevance_filter_drops_generic_search_padding():
    from app.pipeline.discover import is_relevant, topic_terms

    intent = Intent.model_validate({
        "entity": "AI startup", "fields": [{"name": "name"}], "queries": ["q"],
        "filters": ["located in Bangalore", "operates in AI sector"],
    })
    topic = topic_terms(intent)
    good = {"title": "Top 30 AI startups in Bengaluru 2026", "snippet": "", "url": "https://inc42.com/x"}
    assert is_relevant(good, topic)
    for junk in (
        {"title": "List - Wikipedia", "snippet": "A list is a set of items", "url": "https://en.wikipedia.org/wiki/List"},
        {"title": "Microsoft Lists", "snippet": "Track information", "url": "https://microsoft.com/lists"},
        {"title": "Bengaluru - Wikipedia", "snippet": "capital of Karnataka", "url": "https://en.wikipedia.org/wiki/Bengaluru"},
    ):
        assert not is_relevant(junk, topic), junk["title"]
