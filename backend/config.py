"""Environment-driven configuration. Loaded once at import time."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of backend/
ROOT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(ROOT_DIR / ".env")


def _path(env_key: str, default: str) -> Path:
    raw = os.getenv(env_key, default)
    p = Path(raw)
    return p if p.is_absolute() else (ROOT_DIR / p).resolve()


MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip().strip('"').strip("'")

LLM_MODEL_LARGE = os.getenv("LLM_MODEL_LARGE", "mistral-large-latest")
LLM_MODEL_SMALL = os.getenv("LLM_MODEL_SMALL", "mistral-small-latest")
EMBED_MODEL = os.getenv("EMBED_MODEL", "mistral-embed")

CHROMA_PERSIST_DIR = _path("CHROMA_PERSIST_DIR", "./data/chroma_db")
RUNS_DIR = _path("RUNS_DIR", "./data/runs")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "learning_materials")

# Cap on the *automated* quality-gate loop — stops agents revising unattended forever.
MAX_REVISIONS = int(os.getenv("MAX_REVISIONS", "3"))
# Human rejections get their own budget: a person pressing "reject" is deliberate and
# self-rate-limiting, so it must not be blocked by an exhausted automated budget.
MAX_HUMAN_REJECTIONS = int(os.getenv("MAX_HUMAN_REJECTIONS", "2"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))

# LLM call resilience
LLM_MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "2"))
LLM_BACKOFF_SECONDS = float(os.getenv("LLM_BACKOFF_SECONDS", "2"))
LLM_TIMEOUT_MS = int(os.getenv("LLM_TIMEOUT_MS", "180000"))
# Rate limits (HTTP 429) need their own, much more patient policy: a capacity error is
# transient and retryable, unlike a bad request. The default 2 attempts x 2s gave up after
# ~2 seconds and failed a whole run on a 429.
LLM_RATE_LIMIT_ATTEMPTS = int(os.getenv("LLM_RATE_LIMIT_ATTEMPTS", "5"))
LLM_RATE_LIMIT_BACKOFF_SECONDS = float(os.getenv("LLM_RATE_LIMIT_BACKOFF_SECONDS", "10"))
LLM_RATE_LIMIT_MAX_BACKOFF_SECONDS = float(os.getenv("LLM_RATE_LIMIT_MAX_BACKOFF_SECONDS", "90"))

FRONTEND_DIR = ROOT_DIR / "frontend"

# Re-embed sample_materials/ at startup when the collection is empty. Required on hosts
# with an ephemeral filesystem (e.g. Render's free tier), where the persisted Chroma
# store is discarded on every deploy and restart.
SEED_ON_BOOT = os.getenv("SEED_ON_BOOT", "false").strip().lower() in {"1", "true", "yes"}


def ensure_dirs() -> None:
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def missing_api_key() -> bool:
    return not MISTRAL_API_KEY or MISTRAL_API_KEY == "your_key_here"
