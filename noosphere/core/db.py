"""SQLite database initialisation and access."""

import sqlite3
import threading
from noosphere.core.config import DATA_DIR, DB_PATH

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS corpora (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    author_name TEXT,
    author_url TEXT,
    document_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    embedding_model TEXT,
    embedding_dim INTEGER,
    language TEXT DEFAULT 'en',
    license TEXT DEFAULT 'personal-use',
    tags TEXT DEFAULT '[]',
    access_level TEXT DEFAULT 'public',
    pricing_json TEXT,
    status TEXT DEFAULT 'draft',
    owner_id TEXT,
    source_type TEXT,
    source_url TEXT,
    chunk_strategy TEXT DEFAULT 'paragraph',
    stale_threshold_days INTEGER DEFAULT 365,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    doc_type TEXT,
    date TEXT,
    word_count INTEGER,
    content_hash TEXT,
    indexed_at TEXT,
    tags TEXT DEFAULT '[]',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_corpus ON documents(corpus_id);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    document_id TEXT NOT NULL REFERENCES documents(id),
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_start INTEGER,
    char_end INTEGER,
    vector BLOB NOT NULL,
    dim INTEGER NOT NULL,
    norm REAL NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_corpus ON chunks(corpus_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

CREATE TABLE IF NOT EXISTS access_tokens (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    token_hash TEXT NOT NULL,
    label TEXT,
    permissions TEXT DEFAULT 'read',
    usage_count INTEGER DEFAULT 0,
    last_used_at TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tokens_corpus ON access_tokens(corpus_id);

CREATE TABLE IF NOT EXISTS query_logs (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    query_text TEXT,
    result_count INTEGER,
    token_id TEXT,
    agent_id TEXT,
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queries_corpus ON query_logs(corpus_id, created_at);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    corpus_id TEXT REFERENCES corpora(id),
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_corpus ON chat_sessions(corpus_id, updated_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
"""

FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content=chunks, content_rowid=rowid
);
"""

MIGRATION_SQL = [
    "ALTER TABLE documents ADD COLUMN content_hash TEXT",
    "ALTER TABLE documents ADD COLUMN indexed_at TEXT",
    "ALTER TABLE corpora ADD COLUMN chunk_strategy TEXT DEFAULT 'paragraph'",
    "ALTER TABLE corpora ADD COLUMN stale_threshold_days INTEGER DEFAULT 365",
]


def _run_migrations(conn: sqlite3.Connection):
    """Apply additive migrations, silently skipping already-applied ones."""
    for stmt in MIGRATION_SQL:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()


def _init_fts(conn: sqlite3.Connection):
    """Create FTS5 virtual tables and populate from existing data."""
    conn.executescript(FTS_SCHEMA_SQL)

    count = conn.execute(
        "SELECT COUNT(*) as n FROM chunks_fts"
    ).fetchone()["n"]
    if count == 0:
        existing = conn.execute("SELECT rowid, text FROM chunks").fetchall()
        if existing:
            conn.executemany(
                "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                [(r["rowid"], r["text"]) for r in existing],
            )
            conn.commit()


def get_conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _conn.execute("PRAGMA busy_timeout=5000")
            _conn.executescript(SCHEMA_SQL)
            _run_migrations(_conn)
            _init_fts(_conn)
        return _conn


def close():
    global _conn
    with _lock:
        if _conn:
            _conn.close()
            _conn = None
