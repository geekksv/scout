import json
import os
import tempfile
import time

# Isolate the test database and cache before the app is imported.
os.environ["SCOUT_DATA_DIR"] = tempfile.mkdtemp(prefix="scout-test-")

from fastapi.testclient import TestClient  # noqa: E402

from app.llm import _parse_json  # noqa: E402
from app.main import app  # noqa: E402
from app.pipeline.steps import graph  # noqa: E402


def test_parse_json_handles_fences_and_chatter():
    assert _parse_json('{"a": 1}') == {"a": 1}
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json('Sure! Here it is: {"a": {"b": 2}} Hope that helps.') == {"a": {"b": 2}}


def test_graph_has_linear_chain_and_loop():
    g = graph()
    ids = [n["id"] for n in g["nodes"]]
    assert ids[0] == "plan" and ids[-1] == "verify"
    loops = [e for e in g["edges"] if e.get("loop")]
    assert loops == [{"id": "gapfill", "source": "verify", "target": "discover", "loop": True, "label": "gap-fill"}]


def test_demo_run_streams_to_completion():
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"prompt": "AI startups in Bangalore"}).json()["run_id"]

        deadline = time.time() + 60
        while client.get(f"/api/runs/{run_id}").json()["status"] == "running":
            assert time.time() < deadline, "demo run did not finish"
            time.sleep(0.5)

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["status"] == "done"
        assert run["stats"]["clean"] == 12
        assert run["started_at"].endswith("+00:00")

        # A finished run replays its full event history over SSE.
        with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
            events = [json.loads(line[6:]) for line in resp.iter_lines() if line.startswith("data: {\"seq")]
        seqs = [e["seq"] for e in events]
        assert seqs == list(range(len(seqs)))
        assert events[-1]["type"] == "run" and events[-1]["payload"]["status"] == "done"
        assert sum(e["type"] == "row" for e in events) == 12

        records = client.get(f"/api/runs/{run_id}/records").json()
        proof = client.get(f"/api/records/{records[0]['id']}/provenance").json()
        assert proof["record"]["id"] == records[0]["id"]
        evidence = [e for f in proof["fields"] for e in f["evidence"]]
        assert evidence and all(e["quote"] and e["source"]["url"] for e in evidence)


def test_empty_prompt_rejected():
    with TestClient(app) as client:
        assert client.post("/api/runs", json={"prompt": "  "}).status_code == 400


def test_replay_reemits_events_and_shares_records(monkeypatch):
    from app.pipeline import replay as replay_mod

    monkeypatch.setattr(replay_mod, "REPLAY_SECONDS", 1)
    with TestClient(app) as client:
        src = client.post("/api/runs", json={"prompt": "AI startups"}).json()["run_id"]
        _wait(client, src)
        rid = client.post(f"/api/runs/{src}/replay").json()["run_id"]
        run = _wait(client, rid)
        assert run["status"] == "done" and run["mode"] == "replay" and run["replay_of"] == src
        assert client.get(f"/api/runs/{rid}/records").json() == client.get(f"/api/runs/{src}/records").json()
        with client.stream("GET", f"/api/runs/{rid}/events") as resp:
            rows = [line for line in resp.iter_lines() if '"type": "row"' in line]
        assert len(rows) == 12


def _wait(client, run_id, timeout=60):
    deadline = time.time() + timeout
    while (run := client.get(f"/api/runs/{run_id}").json())["status"] in ("queued", "running"):
        assert time.time() < deadline, "run did not finish"
        time.sleep(0.3)
    return run


def test_old_database_gets_new_columns(tmp_path, monkeypatch):
    import sqlite3

    from sqlalchemy import create_engine, inspect

    from app import db as db_mod

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, run_id INTEGER, url TEXT, domain TEXT)")
    con.commit()
    con.close()
    monkeypatch.setattr(db_mod, "engine", create_engine(f"sqlite:///{path.as_posix()}"))
    db_mod.init_db()
    cols = {c["name"] for c in inspect(db_mod.engine).get_columns("source")}
    assert {"page_text", "snippet", "screenshot_path", "robots_allowed"} <= cols
