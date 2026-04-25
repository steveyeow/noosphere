"""Application configuration loaded from environment."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("NOOSPHERE_DATA_DIR", "data"))
DB_PATH = DATA_DIR / "noosphere.db"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8420"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Gemini supports comma-separated keys for quota stacking across Google accounts.
# Keys from the SAME Google Cloud project share a single quota pool — for real
# capacity stacking, supply keys from DIFFERENT projects/accounts.
# Example: GEMINI_API_KEY=AIzaSy...key1,AIzaSy...key2
GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEY", "").split(",") if k.strip()]
# Back-compat alias — callers that just need "is gemini configured?" can keep
# reading the singular form. Code that wants to rotate/fallback reads the list.
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""

DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

CHUNK_MIN_TOKENS = int(os.getenv("CHUNK_MIN_TOKENS", "100"))
CHUNK_MAX_TOKENS = int(os.getenv("CHUNK_MAX_TOKENS", "800"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "50"))

ENABLE_CLOUD = os.getenv("ENABLE_CLOUD", "").lower() in ("1", "true", "yes")

import getpass as _getpass
import subprocess as _sp


def _git_user_name() -> str:
    """Try `git config user.name` — usually set to 'Steve Yao' (with space),
    which gives us a reliable first-name extraction downstream.
    """
    try:
        r = _sp.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=2)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


_raw = os.getenv("OWNER_NAME", "")
if not _raw:
    # Prefer git config (often includes full name with space) over Unix
    # username (often concatenated, e.g. "steveyao").
    _raw = _git_user_name()
if not _raw:
    _email = os.getenv("OWNER_EMAIL", "")
    if _email and "@" in _email:
        _raw = _email.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ")
OWNER_NAME = _raw.strip().title() if _raw.strip() else _getpass.getuser().title()

GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

# Optional OpenAI-compatible providers (DeepSeek, Moonshot/Kimi).
# Useful as fallbacks when Gemini is geo-blocked or OpenAI quota is exhausted.
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_CHAT_MODEL = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat")

KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
KIMI_CHAT_MODEL = os.getenv("KIMI_CHAT_MODEL", "moonshot-v1-8k")

# Zhipu AI (智谱) — provides BOTH chat (glm-*) and embeddings (embedding-3).
# Fills the embedding gap DeepSeek/Kimi don't cover, works in China, very cheap.
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
ZHIPU_BASE_URL = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
ZHIPU_CHAT_MODEL = os.getenv("ZHIPU_CHAT_MODEL", "glm-4.5-flash")
ZHIPU_EMBED_MODEL = os.getenv("ZHIPU_EMBED_MODEL", "embedding-3")
ZHIPU_EMBED_DIM = int(os.getenv("ZHIPU_EMBED_DIM", "1024"))

# Preferred embedding provider for NEW corpora ("zhipu", "gemini", "openai").
# Leave empty to auto-pick based on which API keys are configured.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "").lower()

# App URL — used to build redirect URLs for Stripe, etc.
APP_URL = os.getenv("APP_URL", f"http://localhost:{PORT}")

# Stripe — self-hosted creators use their own keys, keep 100%
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", f"{APP_URL}/?payment=success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", f"{APP_URL}/?payment=cancel")

# Registry — set NOOSPHERE_REGISTRY to the registry URL to join the Noosphere.
# Self-hosted nodes register metadata with the registry for discovery.
# Leave empty or "none" to run as a standalone node.
DEFAULT_REGISTRY = "https://noosphere.wiki"
NOOSPHERE_REGISTRY = os.getenv("NOOSPHERE_REGISTRY", DEFAULT_REGISTRY)
if NOOSPHERE_REGISTRY.lower() == "none":
    NOOSPHERE_REGISTRY = ""

# Is this deployment the shared registry itself? Auto-detected by comparing
# APP_URL to the canonical registry URL — saves operators from a redundant
# env var and keeps a single source of truth. Self-hosted nodes have a
# different APP_URL, so they register normally. The cloud node serving
# noosphere.wiki recognises itself and skips outbound registration; its
# corpora are already on the registry's own DB, so the Discovery UI can
# say "Live on registry — discoverable" instead of the misleading
# "Standalone — not registered". Env var still wins as an escape hatch
# (e.g. someone running a private fork of the registry).
def _normalize_url(u: str) -> str:
    return u.strip().rstrip("/").lower()

_env_is_reg = os.getenv("NOOSPHERE_IS_REGISTRY", "").lower()
if _env_is_reg in ("1", "true", "yes"):
    NOOSPHERE_IS_REGISTRY = True
elif _env_is_reg in ("0", "false", "no"):
    NOOSPHERE_IS_REGISTRY = False
else:
    NOOSPHERE_IS_REGISTRY = _normalize_url(APP_URL) == _normalize_url(DEFAULT_REGISTRY)

# Enrichment scheduler — interval in minutes (0 = disabled)
ENRICHMENT_INTERVAL_MINUTES = int(os.getenv("ENRICHMENT_INTERVAL_MINUTES", "60"))

# Living concept notes — compounding via compiled-truth + timeline.
# When a new source doc is ingested, it's auto-appended to the timeline of any
# concept note whose existing chunks score above the threshold. Concepts are
# marked "dirty" and recompiled in batch once pending_changes crosses the
# recompile threshold (or on explicit user/CLI trigger).
CONCEPT_TIMELINE_THRESHOLD = float(os.getenv("CONCEPT_TIMELINE_THRESHOLD", "0.60"))
CONCEPT_TIMELINE_MAX_MATCHES = int(os.getenv("CONCEPT_TIMELINE_MAX_MATCHES", "3"))
CONCEPT_RECOMPILE_THRESHOLD = int(os.getenv("CONCEPT_RECOMPILE_THRESHOLD", "3"))
# Markdown heading used as the boundary between compiled truth and timeline.
# Chosen over raw `---` (GBrain's marker) because compiled synthesis text may
# contain `---` as a section separator.
CONCEPT_TIMELINE_HEADING = "## Timeline"

# Database URL for PostgreSQL (empty = SQLite)
DATABASE_URL = os.getenv("DATABASE_URL", "")
