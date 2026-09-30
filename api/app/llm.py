"""Groq wrapper: JSON output, disk cache, concurrency cap, and 429 backoff.

Every call is cached by (model, messages) hash, so re-running a workflow or a
demo costs zero quota.
"""

import asyncio
import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass

from groq import APIConnectionError, APIStatusError, AsyncGroq, RateLimitError

from .config import CACHE_DIR, GROQ_API_KEY, GROQ_FAST_MODEL, GROQ_MODEL, LLM_CONCURRENCY

log = logging.getLogger("scout.llm")

_LLM_CACHE = CACHE_DIR / "llm"
_LLM_CACHE.mkdir(parents=True, exist_ok=True)
_sem = asyncio.Semaphore(LLM_CONCURRENCY)
_client: AsyncGroq | None = None
_cooldown: dict[str, float] = {}  # model -> monotonic time it may be used again


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    cached: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "cached": self.cached,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


def _get_client() -> AsyncGroq:
    global _client
    if not GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is not set (put it in api/.env)")
    if _client is None:
        # We do our own retry/backoff so it is visible and tunable.
        _client = AsyncGroq(api_key=GROQ_API_KEY, max_retries=0, timeout=60)
    return _client


def _cache_key(model: str, messages: list[dict], temperature: float) -> str:
    raw = json.dumps([model, messages, temperature], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _chain(model: str) -> list[str]:
    """The requested model first, then the other free models, as rate-limit fallbacks."""
    return [model] + [m for m in (GROQ_FAST_MODEL, "openai/gpt-oss-20b", GROQ_MODEL) if m != model]


def _pick(chain: list[str]) -> tuple[str, float]:
    """The first model not cooling down, else the one that frees up soonest (and its wait)."""
    t = time.monotonic()
    for m in chain:
        if _cooldown.get(m, 0) <= t:
            return m, 0.0
    m = min(chain, key=lambda m: _cooldown[m])
    return m, _cooldown[m] - t


async def complete_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    usage: Usage | None = None,
    retries: int = 8,
) -> dict:
    """Return a JSON object from the model. The system prompt must mention JSON.

    On a 429 the call moves to the next free model instead of sleeping; it only
    waits when every model in the chain is cooling down.
    """
    model = model or GROQ_MODEL
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    # Cached under the requested model, whichever model ends up answering.
    key = _cache_key(model, messages, temperature)
    path = _LLM_CACHE / f"{key}.json"
    if path.exists():
        if usage:
            usage.cached += 1
        return json.loads(path.read_text(encoding="utf-8"))

    client = _get_client()
    chain = _chain(model)
    delay = 2.0
    for attempt in range(retries + 1):
        current, wait = _pick(chain)
        if wait > 0:
            await asyncio.sleep(min(wait, 30) + random.uniform(0, 0.5))
        try:
            async with _sem:
                resp = await client.chat.completions.create(
                    model=current,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
            data = _parse_json(resp.choices[0].message.content or "{}")
            if usage:
                usage.calls += 1
                if resp.usage:
                    usage.prompt_tokens += resp.usage.prompt_tokens
                    usage.completion_tokens += resp.usage.completion_tokens
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except RateLimitError as e:
            retry_after = e.response.headers.get("retry-after")
            cool = float(retry_after) if retry_after else delay
            _cooldown[current] = time.monotonic() + cool
            log.warning("Groq 429 on %s (cooling %.0fs), attempt %d", current, cool, attempt + 1)
            delay = min(delay * 2, 30)
            continue  # _pick moves to another model or waits for the soonest one
        except (APIConnectionError, json.JSONDecodeError) as e:
            log.warning("LLM call failed (%s), retrying in %.1fs", type(e).__name__, delay)
        except APIStatusError as e:
            if e.status_code < 500:
                raise LLMError(f"Groq error {e.status_code}: {e.message}") from e
        if attempt == retries:
            break
        await asyncio.sleep(delay + random.uniform(0, 0.5))
        delay = min(delay * 2, 30)
    raise LLMError(f"LLM call failed after {retries + 1} attempts")
