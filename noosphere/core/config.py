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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

CHUNK_MIN_TOKENS = int(os.getenv("CHUNK_MIN_TOKENS", "100"))
CHUNK_MAX_TOKENS = int(os.getenv("CHUNK_MAX_TOKENS", "800"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "50"))

ENABLE_CLOUD = os.getenv("ENABLE_CLOUD", "").lower() in ("1", "true", "yes")

import getpass as _getpass
_raw = os.getenv("OWNER_EMAIL", "") or os.getenv("OWNER_NAME", "")
if _raw and "@" in _raw:
    _raw = _raw.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ")
OWNER_NAME = _raw.strip().title() if _raw.strip() else _getpass.getuser().title()

GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

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
DEFAULT_REGISTRY = "https://noosphere-production.up.railway.app"
NOOSPHERE_REGISTRY = os.getenv("NOOSPHERE_REGISTRY", DEFAULT_REGISTRY)
if NOOSPHERE_REGISTRY.lower() == "none":
    NOOSPHERE_REGISTRY = ""

# Enrichment scheduler — interval in minutes (0 = disabled)
ENRICHMENT_INTERVAL_MINUTES = int(os.getenv("ENRICHMENT_INTERVAL_MINUTES", "60"))

# Database URL for PostgreSQL (empty = SQLite)
DATABASE_URL = os.getenv("DATABASE_URL", "")
