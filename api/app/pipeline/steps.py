"""The workflow graph shown in the UI and the event contract steps follow.

Event types (see events.emit):
  run    {status, error?}                       run lifecycle
  plan   {intent}                               planner output
  step   {status: running|done|failed, message?, counts?, iteration?}
  log    {level: info|warn|error, message}
  row    {record: {id, data, status, confidence}}
  stats  {raw, clean, duplicates, sources, fetched, blocked, ...}
"""

STEPS = [
    {"id": "plan", "label": "Plan", "description": "Understand the request and design a schema"},
    {"id": "discover", "label": "Discover", "description": "Search the web for candidate sources"},
    {"id": "fetch", "label": "Fetch", "description": "Check robots.txt, crawl pages, take screenshots"},
    {"id": "extract", "label": "Extract", "description": "Pull fields with a verbatim quote for each"},
    {"id": "validate", "label": "Validate", "description": "Type-check, normalize, drop incomplete rows"},
    {"id": "dedupe", "label": "Dedupe", "description": "Merge duplicate entities across sources"},
    {"id": "verify", "label": "Verify", "description": "Cross-check fields across independent sources"},
]

EDGES = [
    {"id": f"{a['id']}-{b['id']}", "source": a["id"], "target": b["id"]}
    for a, b in zip(STEPS, STEPS[1:])
] + [{"id": "gapfill", "source": "verify", "target": "discover", "loop": True, "label": "gap-fill"}]


def graph() -> dict:
    return {"nodes": STEPS, "edges": EDGES}
