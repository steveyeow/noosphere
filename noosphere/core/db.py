"""Database initialisation and access — SQLite (default) or PostgreSQL.

PostgreSQL is used when DATABASE_URL or POSTGRES_URL is set (e.g. on Vercel).
Otherwise falls back to local SQLite with FTS5 for full-text search.
"""

import logging
import os
import threading

from noosphere.core.config import DATA_DIR, DB_PATH

logger = logging.getLogger(__name__)

# ── Database mode detection ────────────────────────────────────────

_RAW_DATABASE_URL = os.getenv("DATABASE_URL", "") or os.getenv("POSTGRES_URL", "")
_USE_PG = bool(_RAW_DATABASE_URL)


def is_pg() -> bool:
    """Check if we're using PostgreSQL."""
    return _USE_PG


def _clean_dsn(url: str) -> str:
    """Strip query params psycopg2 doesn't understand (e.g. pgbouncer=true)."""
    if "?" in url:
        base, qs = url.split("?", 1)
        from urllib.parse import parse_qs, urlencode
        params = parse_qs(qs)
        params.pop("pgbouncer", None)
        clean_qs = urlencode(params, doseq=True)
        return f"{base}?{clean_qs}" if clean_qs else base
    return url


def _pg():
    """Lazy-import psycopg2."""
    import psycopg2
    import psycopg2.extras
    return psycopg2


DATABASE_URL = _clean_dsn(_RAW_DATABASE_URL) if _USE_PG else ""


# ── PostgreSQL connection wrapper ──────────────────────────────────
# Makes psycopg2 behave like sqlite3 — same API for consumer code.

class _PgCursorResult:
    """Wraps a psycopg2 cursor to match sqlite3 cursor interface."""

    def __init__(self, cursor):
        self._cur = cursor

    def fetchone(self):
        try:
            return self._cur.fetchone()
        except Exception:
            return None

    def fetchall(self):
        try:
            return list(self._cur.fetchall())
        except Exception:
            return []

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return getattr(self._cur, "lastrowid", None)


class _PgConnWrapper:
    """Wraps psycopg2 connection to accept SQLite-style ? placeholders."""

    def __init__(self, dsn: str):
        pg = _pg()
        self._conn = pg.connect(dsn)
        self._conn.autocommit = False

    def execute(self, sql: str, params=()) -> _PgCursorResult:
        pg = _pg()
        sql = sql.replace("?", "%s")
        try:
            cur = self._conn.cursor(cursor_factory=pg.extras.RealDictCursor)
            cur.execute(sql, params)
            return _PgCursorResult(cur)
        except pg.errors.InFailedSqlTransaction:
            # Connection poisoned by a prior failed statement (singleton connection
            # shared across requests). Roll back and retry once so this caller isn't
            # punished for someone else's error. Do NOT add a blanket rollback on
            # other exceptions — callers using SAVEPOINT (migrations) rely on the
            # transaction staying open so they can ROLLBACK TO SAVEPOINT themselves.
            self._conn.rollback()
            cur = self._conn.cursor(cursor_factory=pg.extras.RealDictCursor)
            cur.execute(sql, params)
            return _PgCursorResult(cur)

    def executemany(self, sql: str, params_list) -> _PgCursorResult:
        pg = _pg()
        sql = sql.replace("?", "%s")
        try:
            cur = self._conn.cursor(cursor_factory=pg.extras.RealDictCursor)
            cur.executemany(sql, params_list)
            return _PgCursorResult(cur)
        except pg.errors.InFailedSqlTransaction:
            self._conn.rollback()
            cur = self._conn.cursor(cursor_factory=pg.extras.RealDictCursor)
            cur.executemany(sql, params_list)
            return _PgCursorResult(cur)

    def executescript(self, sql: str):
        """Execute multiple statements separated by semicolons."""
        cur = self._conn.cursor()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                try:
                    cur.execute(stmt)
                except Exception:
                    self._conn.rollback()
                    cur = self._conn.cursor()
                    continue
        self._conn.commit()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


# ── Schema ─────────────────────────────────────────────────────────

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
    owned_handles TEXT DEFAULT '[]',
    task_types TEXT DEFAULT '[]',
    samples TEXT DEFAULT '[]',
    autonomy_level INTEGER DEFAULT 0,
    calibration_policy TEXT,
    license_terms TEXT,
    kb_reputation REAL DEFAULT 0.0,
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
    source_kind TEXT DEFAULT 'user_original',
    author_entity_id TEXT,
    participant_entity_ids TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_corpus ON documents(corpus_id);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    kind TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases TEXT DEFAULT '[]',
    description TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(corpus_id, kind, canonical_name)
);
CREATE INDEX IF NOT EXISTS idx_entities_corpus ON entities(corpus_id);
CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(corpus_id, kind);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    document_id TEXT NOT NULL REFERENCES documents(id),
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_start INTEGER,
    char_end INTEGER,
    vector {BLOB_TYPE} NOT NULL,
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
    action TEXT DEFAULT 'ask',
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

CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    stripe_session_id TEXT UNIQUE,
    stripe_payment_intent TEXT,
    stripe_customer_id TEXT,
    payment_type TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency TEXT DEFAULT 'usd',
    status TEXT DEFAULT 'pending',
    payer_email TEXT,
    payer_agent_id TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_payments_corpus ON payments(corpus_id, status);
CREATE INDEX IF NOT EXISTS idx_payments_session ON payments(stripe_session_id);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    stripe_subscription_id TEXT UNIQUE,
    stripe_customer_id TEXT NOT NULL,
    payer_email TEXT,
    status TEXT DEFAULT 'active',
    current_period_end TEXT,
    created_at TEXT NOT NULL,
    cancelled_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_subs_corpus ON subscriptions(corpus_id, status);
CREATE INDEX IF NOT EXISTS idx_subs_customer ON subscriptions(stripe_customer_id);

CREATE TABLE IF NOT EXISTS registered_nodes (
    endpoint TEXT PRIMARY KEY,
    node_version TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_health_at TEXT,
    health_status TEXT DEFAULT 'unknown',
    consecutive_failures INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS concept_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    source_doc_ids TEXT NOT NULL DEFAULT '[]',
    compiled_at TEXT NOT NULL,
    UNIQUE(document_id, version)
);
CREATE INDEX IF NOT EXISTS idx_concept_versions_document ON concept_versions(document_id);

CREATE TABLE IF NOT EXISTS registered_corpora (
    id TEXT PRIMARY KEY,
    node_endpoint TEXT NOT NULL REFERENCES registered_nodes(endpoint) ON DELETE CASCADE,
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
    task_types TEXT DEFAULT '[]',
    autonomy_level INTEGER DEFAULT 0,
    source_composition TEXT DEFAULT '{}',
    kb_reputation REAL DEFAULT 0.0,
    registered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(node_endpoint, corpus_id)
);
CREATE INDEX IF NOT EXISTS idx_rc_node ON registered_corpora(node_endpoint);
CREATE INDEX IF NOT EXISTS idx_rc_access ON registered_corpora(access_level);

CREATE TABLE IF NOT EXISTS corpus_citations (
    id TEXT PRIMARY KEY,
    citing_corpus_id TEXT NOT NULL REFERENCES corpora(id),
    cited_corpus_id TEXT NOT NULL,
    cited_corpus_endpoint TEXT,
    citing_doc_id TEXT,
    cited_doc_id TEXT,
    cited_chunk_id TEXT,
    kind TEXT NOT NULL,
    context TEXT,
    weight REAL DEFAULT 1.0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citations_citing ON corpus_citations(citing_corpus_id);
CREATE INDEX IF NOT EXISTS idx_citations_cited ON corpus_citations(cited_corpus_id);
CREATE INDEX IF NOT EXISTS idx_citations_kind ON corpus_citations(kind);

CREATE TABLE IF NOT EXISTS peer_subscriptions (
    id TEXT PRIMARY KEY,
    subscriber_corpus_id TEXT NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
    target_corpus_id TEXT,
    target_endpoint TEXT,
    target_slug TEXT,
    mode TEXT NOT NULL,
    query TEXT,
    topic_filter TEXT,
    cadence_minutes INTEGER NOT NULL,
    max_docs_per_cycle INTEGER NOT NULL DEFAULT 5,
    bearer_token TEXT,
    auth_mode TEXT NOT NULL,
    budget_cents_per_month INTEGER,
    status TEXT NOT NULL,
    last_run_at TEXT,
    next_run_at TEXT NOT NULL,
    last_error TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    approved_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_peer_sub_subscriber ON peer_subscriptions(subscriber_corpus_id);
CREATE INDEX IF NOT EXISTS idx_peer_sub_next_run ON peer_subscriptions(status, next_run_at);

CREATE TABLE IF NOT EXISTS peer_subscription_runs (
    id TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL REFERENCES peer_subscriptions(id) ON DELETE CASCADE,
    ran_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    docs_ingested INTEGER DEFAULT 0,
    chunks_ingested INTEGER DEFAULT 0,
    cents_spent INTEGER DEFAULT 0,
    latency_ms INTEGER,
    error_detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_peer_run_sub_date ON peer_subscription_runs(subscription_id, ran_at DESC);
"""

# SQLite: FTS5 virtual table for full-text search
FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content=chunks, content_rowid=rowid
);

CREATE VIRTUAL TABLE IF NOT EXISTS registered_corpora_fts USING fts5(
    name, description, author, tags, registry_id
);
"""

# PostgreSQL: tsvector column + GIN index for full-text search
PG_FTS_SQL = """
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='chunks' AND column_name='tsv'
    ) THEN
        ALTER TABLE chunks ADD COLUMN tsv TSVECTOR;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN(tsv);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='registered_corpora' AND column_name='tsv'
    ) THEN
        ALTER TABLE registered_corpora ADD COLUMN tsv TSVECTOR;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_rc_tsv ON registered_corpora USING GIN(tsv);
"""

MIGRATION_SQL = [
    "ALTER TABLE documents ADD COLUMN content_hash TEXT",
    "ALTER TABLE documents ADD COLUMN indexed_at TEXT",
    "ALTER TABLE corpora ADD COLUMN chunk_strategy TEXT DEFAULT 'paragraph'",
    "ALTER TABLE corpora ADD COLUMN stale_threshold_days INTEGER DEFAULT 365",
    "ALTER TABLE documents ADD COLUMN source_kind TEXT DEFAULT 'user_original'",
    "ALTER TABLE documents ADD COLUMN author_entity_id TEXT",
    "ALTER TABLE documents ADD COLUMN participant_entity_ids TEXT DEFAULT '[]'",
    "ALTER TABLE corpora ADD COLUMN owned_handles TEXT DEFAULT '[]'",
    "ALTER TABLE corpora ADD COLUMN task_types TEXT DEFAULT '[]'",
    "ALTER TABLE corpora ADD COLUMN samples TEXT DEFAULT '[]'",
    "ALTER TABLE corpora ADD COLUMN autonomy_level INTEGER DEFAULT 0",
    "ALTER TABLE corpora ADD COLUMN calibration_policy TEXT",
    "ALTER TABLE corpora ADD COLUMN license_terms TEXT",
    "ALTER TABLE corpora ADD COLUMN kb_reputation REAL DEFAULT 0.0",
    "ALTER TABLE registered_corpora ADD COLUMN task_types TEXT DEFAULT '[]'",
    "ALTER TABLE registered_corpora ADD COLUMN autonomy_level INTEGER DEFAULT 0",
    "ALTER TABLE registered_corpora ADD COLUMN source_composition TEXT DEFAULT '{}'",
    "ALTER TABLE registered_corpora ADD COLUMN kb_reputation REAL DEFAULT 0.0",
    "ALTER TABLE query_logs ADD COLUMN action TEXT DEFAULT 'ask'",
]

# Indexes that reference columns added via MIGRATION_SQL — must run after migrations
POST_MIGRATION_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_documents_source_kind ON documents(corpus_id, source_kind)",
    "CREATE INDEX IF NOT EXISTS idx_queries_corpus_action ON query_logs(corpus_id, action, created_at)",
]


# ── Init helpers ───────────────────────────────────────────────────

def _run_migrations_sqlite(conn):
    """Apply additive migrations, silently skipping already-applied ones."""
    import sqlite3
    for stmt in MIGRATION_SQL:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    for stmt in POST_MIGRATION_INDEXES:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()


def _run_migrations_pg(conn):
    """Apply additive migrations for PostgreSQL using SAVEPOINT."""
    for stmt in MIGRATION_SQL:
        col_name = stmt.split("ADD COLUMN")[1].strip().split()[0] if "ADD COLUMN" in stmt else ""
        sp = f"sp_mig_{col_name}" if col_name else "sp_mig"
        try:
            conn.execute(f"SAVEPOINT {sp}")
            conn.execute(stmt)
            conn.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
    for idx, stmt in enumerate(POST_MIGRATION_INDEXES):
        sp = f"sp_pmidx_{idx}"
        try:
            conn.execute(f"SAVEPOINT {sp}")
            conn.execute(stmt)
            conn.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
    conn.commit()


def _init_fts_sqlite(conn):
    """Create FTS5 virtual tables and populate from existing data."""
    conn.executescript(FTS_SCHEMA_SQL)
    count = conn.execute("SELECT COUNT(*) as n FROM chunks_fts").fetchone()["n"]
    if count == 0:
        existing = conn.execute("SELECT rowid, text FROM chunks").fetchall()
        if existing:
            conn.executemany(
                "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                [(r["rowid"], r["text"]) for r in existing],
            )
            conn.commit()
    rc_count = conn.execute("SELECT COUNT(*) as n FROM registered_corpora_fts").fetchone()["n"]
    if rc_count == 0:
        existing = conn.execute(
            "SELECT id, name, description, author, tags FROM registered_corpora"
        ).fetchall()
        if existing:
            conn.executemany(
                "INSERT INTO registered_corpora_fts(name, description, author, tags, registry_id) VALUES (?, ?, ?, ?, ?)",
                [(r["name"], r["description"] or "", r["author"] or "", r["tags"] or "", r["id"]) for r in existing],
            )
            conn.commit()


def _init_fts_pg(conn):
    """Create tsvector column + GIN index; backfill from existing data."""
    raw_conn = conn._conn if isinstance(conn, _PgConnWrapper) else conn
    cur = raw_conn.cursor()
    # Add tsv column if not exists + create GIN index for chunks
    cur.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='chunks' AND column_name='tsv'
            ) THEN
                ALTER TABLE chunks ADD COLUMN tsv TSVECTOR;
            END IF;
        END $$
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN(tsv)")
    raw_conn.commit()
    cur.execute("UPDATE chunks SET tsv = to_tsvector('english', text) WHERE tsv IS NULL")
    raw_conn.commit()
    # Add tsv column for registered_corpora (network discovery)
    cur.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='registered_corpora' AND column_name='tsv'
            ) THEN
                ALTER TABLE registered_corpora ADD COLUMN tsv TSVECTOR;
            END IF;
        END $$
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rc_tsv ON registered_corpora USING GIN(tsv)")
    raw_conn.commit()
    cur.execute("""
        UPDATE registered_corpora
        SET tsv = to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,'') || ' ' || coalesce(author,''))
        WHERE tsv IS NULL
    """)
    raw_conn.commit()


# ── Connection management ──────────────────────────────────────────

_conn = None
_lock = threading.Lock()


def get_conn():
    """Get a database connection (singleton, thread-safe).

    Returns a sqlite3.Connection or _PgConnWrapper — both support
    the same interface: .execute(), .executemany(), .executescript(),
    .commit(), .close().
    """
    global _conn
    with _lock:
        if _conn is not None:
            return _conn

        if _USE_PG:
            logger.info("Connecting to PostgreSQL")
            _conn = _PgConnWrapper(DATABASE_URL)
            schema = SCHEMA_SQL.replace("{BLOB_TYPE}", "BYTEA")
            _conn.executescript(schema)
            _run_migrations_pg(_conn)
            _init_fts_pg(_conn)
        else:
            import sqlite3
            logger.info("Using SQLite at %s", DB_PATH)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            schema = SCHEMA_SQL.replace("{BLOB_TYPE}", "BLOB")
            conn.executescript(schema)
            _run_migrations_sqlite(conn)
            _init_fts_sqlite(conn)
            _conn = conn

        return _conn


def close():
    """Close the database connection."""
    global _conn
    with _lock:
        if _conn:
            _conn.close()
            _conn = None


# ── Helpers for PG binary data ─────────────────────────────────────

def pg_binary(data: bytes) -> bytes:
    """Wrap bytes for PostgreSQL BYTEA column. No-op for SQLite."""
    if _USE_PG:
        return _pg().Binary(data)
    return data
