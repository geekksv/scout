# Scout — AI-Powered Data Intelligence Platform

**Describe the data you need in plain English. Scout designs the collection workflow, gathers data from permitted sources, cleans and deduplicates it, and proves every single value with a verbatim quote from its source.**

Code Cubicle 6.0 · PS 01 (AI-Powered Data Intelligence Platform) · built solo · runs entirely on free tools (Groq free tier, DuckDuckGo search, SQLite).

> *"Find AI startups in Bangalore with their funding stage, founding year, founders and website"*
> → a plan in ~3 s → 25 sources discovered → 16 pages read → **59 clean rows in about a minute**, 15 unproven values automatically dropped, every cell clickable to its evidence.

---

## Why it's different: no quote, no value

LLM scrapers hallucinate. Scout's extractor must return, for **every field**, the exact sentence it came from. A value is kept only if:

1. the quote really appears on the fetched page (formatting differences are forgiven, changed words are not: "Series C" is rejected when the page says "Series A"), and
2. the value itself appears in that quote.

Everything else is dropped and counted ("Unproven values dropped"). Then entities are merged across sites and each field is cross-checked: **Verified** (2+ independent domains agree), **Single source**, or **Conflict** (sources disagree — a person picks the right value in one click).

**Click-to-Proof:** click any cell to see the quote highlighted inside its page excerpt, the source URL, fetch time, and a screenshot of the page.

## Requirement coverage (PS 01)

| Requirement | How Scout does it |
|---|---|
| Understand requirements from natural language | LLM planner turns the prompt into an entity, typed fields, filters, target row count and search queries — shown on an **editable plan screen** before anything runs |
| Dynamically design and execute workflows | Live workflow graph (plan → discover → fetch → extract → validate → dedupe → verify) with a **gap-fill loop**: if too few rows are found, the AI writes new queries and goes back to discovery |
| Collect from multiple **permitted** sources | Free web search, **robots.txt checked for every page (RFC 9309)**, login-only/social sites and ad links always blocked, user-defined domain blocklist |
| Clean, structure, validate, deduplicate | Type coercion (integers, money like "2.5 crore", URLs, emails, dates), required-field checks, fuzzy entity matching ("Nimbus Labs Pvt Ltd" = "Nimbus Labs"), city/format aliases ("Bengaluru" = "Bangalore") |
| Source-backed, traceable data | Per-cell provenance: value, verbatim quote, source URL, fetch time, page screenshot — **Click-to-Proof** |
| Monitor and manage tasks | Live progress over Server-Sent Events, activity log, counters, cancel; runs list with status and progress |
| Interactive dashboard | Dataset grid with trust markers per cell, insights (trust breakdown, field completeness, source health), sources tab |
| Workflow and dataset history | Every run and its events are stored; **Re-run** a workflow and see a **diff** (+new / ~changed / −removed); **Edit plan** and run again; **Replay** any finished run |
| Search, filter, export | Full-text search, trust filter, sortable columns; **CSV / XLSX / JSON** export (JSON includes the evidence for each cell) |

## Architecture

```
Next.js 15 (web, :3100)  ──REST + SSE──►  FastAPI (api, :8000)
  prompt → plan editor                     orchestrator (asyncio tasks, cancel)
  live React Flow graph                    ├─ plan       Groq gpt-oss-120b, JSON mode, validated by Pydantic
  streaming dataset + Click-to-Proof       ├─ discover   ddgs search → rank → blocklist → robots.txt
  insights, export, history, replay        ├─ fetch      httpx + trafilatura; Playwright (installed Chrome) for JS pages + screenshots
                                           ├─ extract    Groq qwen3 (fast) → verbatim quote check
                                           ├─ validate   type coercion, required fields
                                           ├─ dedupe     fuzzy entity clusters (rapidfuzz)
                                           └─ verify     cross-domain agreement / conflict per field
                                           SQLite (workflows, runs, sources, records, provenance, events)
                                           disk cache for search results, pages and LLM answers
```

- **Streaming pipeline:** each page flows through extract → validate → merge as soon as it is fetched, so rows appear while the run is still going.
- **Free-tier friendly:** every LLM answer, search result and page is cached (re-runs cost ~0 quota); on a Groq 429 the call switches to the next free model (qwen3 → gpt-oss-20b → gpt-oss-120b) instead of sleeping.
- **Demo-proof:** *Replay* re-emits a recorded run's events with its original rhythm in ~40 s, with no network or AI calls, and Click-to-Proof still works on the replayed rows.

## Run locally

Requirements: Python 3.12, Node 20+, Google Chrome (or Edge) for JavaScript pages and screenshots.

**API**
```bash
cd api
py -3.12 -m venv .venv
.venv/Scripts/pip install -r requirements.txt
cp .env.example .env          # paste a free key from https://console.groq.com/keys
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

**Web**
```bash
cd web
npm install
npm run dev                   # http://localhost:3100
```

Notes
- On Windows, avoid `uvicorn --reload`: it can leave an orphaned worker on port 8000 that keeps serving old code.
- Models are set in `api/.env` (`GROQ_MODEL`, `GROQ_FAST_MODEL`). Set `NEXT_PUBLIC_API_URL` if the API is not on `http://localhost:8000`.
- The **Demo run** button on the home page plays a scripted run with fictional companies on `example.com` domains — useful without a key or network.

## Deploy (free)

**Backend → Hugging Face Spaces (Docker, free CPU tier).** Scout needs a real browser for JavaScript pages and screenshots, and Spaces gives enough memory for one; most other free tiers (512 MB) do not.
1. Create a Space at huggingface.co/new-space → SDK **Docker** → Blank → Public.
2. Upload the contents of `api/` (with `Dockerfile`) to the Space. The Space's `README.md` must start with:
   ```yaml
   ---
   title: Scout API
   sdk: docker
   app_port: 7860
   ---
   ```
3. Space → Settings → **Secrets**: `GROQ_API_KEY`. **Variables**: `CORS_ORIGIN_REGEX` = `https://.*\.vercel\.app`.
4. After the build, check `https://<user>-<space>.hf.space/api/health`.

**Frontend → Vercel (Hobby, free).** Import the GitHub repo → Root Directory **`web`** → env var `NEXT_PUBLIC_API_URL` = your Space URL → Deploy.

Notes: the free Space sleeps after inactivity (the first request wakes it) and its SQLite database resets on restart. That's fine for judging, but for the live stage demo, run locally and use **Replay**.

## Tests

```bash
cd api && .venv/Scripts/python -m pytest -q     # 38 tests, fully offline (no network, no quota)
cd web && npx tsc --noEmit && npm run lint && npx next build
```

Covered: plan validation, URL normalisation, blocklist, robots.txt rules, verbatim-quote and value checks (including hallucinated values), type coercion, entity merging, conflict detection, aliases, evidence location, CSV/XLSX/JSON export, run diffs, SSE streaming, and replay.

## 3-minute demo script

1. **Hook (0:00):** "Every business rebuilds a scraper for every question. Scout builds the workflow itself — and proves every value."
2. **Prompt (0:15):** click the first example → *Plan dataset*. Show the plan; add a field live (e.g. `headquarters`) to prove it's dynamic → *Run workflow*.
3. **Run (0:40):** the graph lights up, sources appear with robots.txt badges, rows stream in, counters tick — including **Unproven values dropped**.
4. **Click-to-Proof (1:40):** click a green-dot cell → quote highlighted in the page, "Verified by 2 sources", screenshot. Show the conflict-resolution buttons if a conflict appears.
5. **Manage (2:20):** filter "Verified only", export XLSX, *Re-run* → diff banner; show *Replay*.
6. **Close (2:45):** "No quote, no value. Built solo, runs on $0."

Stage tip: do one live run beforehand, then present with **Replay** (no Wi-Fi risk), keeping a live run ready if judges ask.

## Limits (honest list)

- Data quality depends on what public list pages state; many rows are single-source, which Scout shows rather than hides.
- Some directories (e.g. Crunchbase) block automated access; they are skipped and reported.
- Groq free-tier limits cap how many large runs can be made per day; caching makes repeat runs nearly free.

## Repo layout

```
api/app/main.py                 REST + SSE endpoints
api/app/llm.py                  Groq wrapper: JSON mode, cache, model fallback on 429
api/app/events.py               per-run event bus (persisted, replayable)
api/app/pipeline/               plan, discover, live (orchestrates), extract, validate, merge, replay, demo
api/app/services/               search, robots, crawler, evidence, export
api/tests/                      offline test suite
web/app/                        pages: home, plan/[id], runs, runs/[id]
web/components/                 RunGraph, DatasetView, ProofPanel, Insights
```
