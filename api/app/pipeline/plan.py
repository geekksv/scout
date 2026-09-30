"""Planner: turn a plain-English request into an editable collection plan."""

import re
from datetime import date

from pydantic import BaseModel, Field, field_validator

from .. import llm

FIELD_TYPES = ["string", "integer", "number", "url", "email", "date", "boolean"]


class IntentField(BaseModel):
    name: str
    type: str = "string"
    required: bool = False
    description: str = ""

    @field_validator("name")
    @classmethod
    def snake_case(cls, v: str) -> str:
        v = re.sub(r"[^a-z0-9]+", "_", v.strip().lower()).strip("_")
        if not v:
            raise ValueError("field name is empty")
        return v

    @field_validator("type")
    @classmethod
    def known_type(cls, v: str) -> str:
        v = v.strip().lower()
        aliases = {"str": "string", "text": "string", "int": "integer", "float": "number",
                   "link": "url", "uri": "url", "bool": "boolean", "datetime": "date"}
        v = aliases.get(v, v)
        return v if v in FIELD_TYPES else "string"


class Intent(BaseModel):
    entity: str
    fields: list[IntentField] = Field(min_length=1)
    filters: list[str] = []
    target_count: int = 20
    queries: list[str] = Field(min_length=1)
    blocked_domains: list[str] = []

    @field_validator("target_count")
    @classmethod
    def clamp_count(cls, v: int) -> int:
        return max(5, min(v, 50))

    @field_validator("fields")
    @classmethod
    def unique_fields(cls, v: list[IntentField]) -> list[IntentField]:
        seen, out = set(), []
        for f in v:
            if f.name not in seen:
                seen.add(f.name)
                out.append(f)
        # The first field identifies the entity (used for dedupe), so it is always required.
        out[0].required = True
        return out[:12]

    @field_validator("queries", "filters", "blocked_domains")
    @classmethod
    def clean_list(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(s.strip() for s in v if s and s.strip()))


SYSTEM = f"""You are the planning engine of a web data-collection platform.
Given a user's request, design a collection plan. Reply with JSON only, matching:
{{
  "entity": "singular noun for one row, e.g. 'AI startup'",
  "fields": [{{"name": "snake_case", "type": one of {FIELD_TYPES}, "required": bool, "description": "what to extract"}}],
  "filters": ["conditions every row must satisfy, taken from the request"],
  "target_count": integer number of rows wanted (default 20 if unspecified),
  "queries": ["6 diverse web search queries likely to surface pages listing or describing matching entities"]
}}
Rules:
- The FIRST field must be the entity's name/title (it identifies a row).
- Include every field the user asked for; add at most 2 obviously useful extras.
- Only the first field is required. Mark another field required only if the user explicitly says rows without it are useless (most web pages will not state every field).
- Filters describe what the user is looking for; keep them short.
- Queries should target list pages, directories, news roundups and official sites, not social media.
- Vary query wording; include location/time constraints from the request."""


async def make_plan(prompt: str, usage: llm.Usage | None = None) -> Intent:
    # Without today's date the model anchors queries on its training year.
    system = f"{SYSTEM}\n- Today is {date.today():%d %B %Y}; use the current year when a year helps."
    data = await llm.complete_json(system, f"Request: {prompt}", usage=usage, temperature=0.2)
    intent = Intent.model_validate(data)
    # Models often mark every field required despite the prompt, which silently
    # empties the dataset (few pages state every field). Only the identifying
    # field is required in a generated plan; people can still require more on
    # the plan screen, which goes through the Intent model directly.
    for f in intent.fields[1:]:
        f.required = False
    return intent
