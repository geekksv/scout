from pathlib import Path
import os

from dotenv import load_dotenv

API_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = API_DIR.parent
load_dotenv(API_DIR / ".env")

DATA_DIR = Path(os.getenv("SCOUT_DATA_DIR", ROOT_DIR / "data"))
CACHE_DIR = DATA_DIR / "cache"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
for d in (DATA_DIR, CACHE_DIR, SCREENSHOT_DIR):
    d.mkdir(parents=True, exist_ok=True)

DB_URL = f"sqlite:///{(DATA_DIR / 'scout.db').as_posix()}"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Big model for planning/verification, fast model for bulk extraction.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_FAST_MODEL = os.getenv("GROQ_FAST_MODEL", "qwen/qwen3.8-27b")
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "3"))
# Headless browser for JS pages and screenshots. Turn off on small hosts (e.g. 512 MB free tiers).
BROWSER_ENABLED = os.getenv("SCOUT_BROWSER", "on").lower() not in ("off", "0", "false", "no")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3100").split(",")
# e.g. https://.*\.vercel\.app so every Vercel preview deployment can reach the API
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX") or None
