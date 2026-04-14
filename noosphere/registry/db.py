"""Registry database — SQLite storage for node and corpus metadata."""

import sqlite3
import threading
from pathlib import Path

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    endpoint TEXT PRIMARY KEY,
    node_version TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_health_at TEXT,
    health_status TEXT DEFAULT 'unknown',
    consecutive_failures INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS registry_corpora (
    id TEXT PRIMARY KEY,
    node_endpoint TEXT NOT NULL REFERENCES nodes(endpoint) ON DELETE CASCADE,
    corpus_id TEXT NOT NULL,
    name TEXT NOT NULL,
    slug TEXT,
    description TEXT,
    author TEXT,
    tags TEXT DEFAULT '[]',
    document_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    access_level TEXT DEFAULT 'public',
    status TEXT DEFAULT 'draft',
    registered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(node_endpoint, corpus_id)
);
CREATE INDEX IF NOT EXISTS idx_rc_node ON registry_corpora(node_endpoint);
CREATE INDEX IF NOT EXISTS idx_rc_access ON registry_corpora(access_level);

CREATE VIRTUAL TABLE IF NOT EXISTS registry_corpora_fts USING fts5(
    name, description, author, tags, registry_id
);
"""


def get_registry_conn(db_path: str | Path = "registry.db") -> sqlite3.Connection:
    """Get or create the registry database connection."""
    global _conn
    with _lock:
        if _conn is None:
            path = Path(db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(path), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _conn.execute("PRAGMA busy_timeout=5000")
            _conn.executescript(REGISTRY_SCHEMA)
        return _conn


def close_registry():
    global _conn
    with _lock:
        if _conn:
            _conn.close()
            _conn = None
