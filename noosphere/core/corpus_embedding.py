"""Corpus-level embeddings for the discovery graph.

This module owns the "one summary vector per corpus" pipeline that the
Noosphere graph view (renderNet / Explore) uses to draw "this KB looks
semantically related to that KB" edges. It is deliberately decoupled
from the per-chunk embeddings used for retrieval — those vectors are
high-fidelity passage vectors stored in `chunks`, while these vectors
are coarse-grained "what is this corpus about" summaries stored on the
`corpora` row itself.

Why a separate vector at all? Because edges-from-tag-overlap are
hopelessly sparse: a fresh user with five distinct topic KBs and no
manually-set tags sees five disconnected dots. A profile vector lets us
compute pair-wise cosine similarity instead, which produces meaningful
edges even when nothing else is filled in.

Profile text composition (in priority order, all optional, capped):
  1. Corpus name + description + tags  — always available, even at create.
  2. Top-N entities by mention count   — surfaces what the corpus is
     actually about once enrichment has run.
  3. Snippet from the manifest doc     — auto-generated wiki-style overview
     that tends to summarise the corpus better than any single doc.
  4. First-line / title from a few representative docs — last-resort
     filler so a freshly-ingested corpus with no manifest yet still has
     enough text for a reasonable embedding.

Truncation is intentional: an embedding of a 50-document KB shouldn't
cost an embed call over the entire corpus. We aim for ~500-1500 chars
of profile text per corpus — enough for the embedder to anchor topic,
not so much that it drowns the signal in irrelevant token noise.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from noosphere.core.db import get_conn
from noosphere.core.embeddings import (
    EmbeddingProvider,
    blob_to_vector,
    get_embedder,
    vector_to_blob,
)

log = logging.getLogger(__name__)

# Caps that keep profile text bounded. Tuned for the cheap-and-fast
# embedders we route to (Zhipu/Gemini/OpenAI small models all handle
# ~2k chars comfortably). Bigger doesn't help — the cosine signal
# saturates well before that.
_MAX_PROFILE_CHARS = 1500
_TOP_ENTITIES = 8
_SAMPLE_DOCS = 3
_SAMPLE_DOC_CHARS = 200


def _safe_str(v) -> str:
    return v if isinstance(v, str) else ""


def _clip(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def build_corpus_profile_text(corpus: dict) -> str:
    """Synthesise a single ~1.5KB descriptor capturing what this corpus
    is about. Pure string assembly — no DB writes, no embedding calls.
    Returns "" if the corpus has nothing useful (empty name and no docs);
    callers should treat that as "skip embedding for now".
    """
    cid = corpus.get("id")
    parts: list[str] = []

    name = _safe_str(corpus.get("name")).strip()
    if name:
        parts.append(name)

    desc = _safe_str(corpus.get("description")).strip()
    if desc:
        parts.append(desc)

    tags = corpus.get("tags") or []
    if isinstance(tags, str):
        # Stored as JSON in some paths (raw row reads); be permissive.
        import json as _json
        try:
            tags = _json.loads(tags) if tags else []
        except Exception:
            tags = []
    if tags:
        parts.append("Tags: " + ", ".join(str(t) for t in tags if t))

    # Top entities — only available once enrichment has run. Best signal
    # for "what this KB is actually about" once it has content.
    if cid:
        try:
            from noosphere.core.entities import list_entities
            ents = list_entities(cid)
            ents_sorted = sorted(
                ents,
                key=lambda e: e.get("mention_count", 0),
                reverse=True,
            )[:_TOP_ENTITIES]
            ent_names = [
                _safe_str(e.get("canonical_name")).strip()
                for e in ents_sorted
                if _safe_str(e.get("canonical_name")).strip()
            ]
            if ent_names:
                parts.append("Key entities: " + ", ".join(ent_names))
        except Exception as e:
            log.debug("list_entities failed for %s: %s", cid, e)

    # Manifest doc — auto-generated overview. Prefer it over arbitrary
    # docs because it's curated to summarise the corpus.
    if cid:
        try:
            conn = get_conn()
            row = conn.execute(
                "SELECT title, content FROM documents "
                "WHERE corpus_id=? AND COALESCE(source_kind,'') = 'system' "
                "ORDER BY created_at DESC LIMIT 1",
                (cid,),
            ).fetchone()
            if row:
                manifest = _safe_str(row["content"]) if row["content"] else ""
                if manifest:
                    parts.append("Overview: " + _clip(manifest, 600))
        except Exception as e:
            log.debug("manifest fetch failed for %s: %s", cid, e)

    # Sample doc titles + first-line snippets — fallback signal when we
    # have nothing else. Skips the system manifest (already used above)
    # to avoid double-counting.
    if cid:
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT title, content FROM documents "
                "WHERE corpus_id=? AND COALESCE(source_kind,'user_original') != 'system' "
                "ORDER BY created_at DESC LIMIT ?",
                (cid, _SAMPLE_DOCS),
            ).fetchall()
            samples = []
            for r in rows:
                title = _safe_str(r["title"]).strip()
                first = _safe_str(r["content"]).strip().split("\n", 1)[0]
                if title and first:
                    samples.append(f"{title}: {_clip(first, _SAMPLE_DOC_CHARS)}")
                elif title:
                    samples.append(title)
            if samples:
                parts.append("Recent: " + " | ".join(samples))
        except Exception as e:
            log.debug("sample docs fetch failed for %s: %s", cid, e)

    text = "\n".join(parts).strip()
    return _clip(text, _MAX_PROFILE_CHARS)


def compute_corpus_embedding(
    corpus: dict,
    *,
    embedder: Optional[EmbeddingProvider] = None,
) -> Optional[tuple[bytes, float, int, str]]:
    """Embed a corpus's profile text. Returns (vec_bytes, l2_norm, dim, model)
    or None if the corpus has no useful profile text or no embedder is
    configured. Best-effort — never raises into the caller."""
    text = build_corpus_profile_text(corpus)
    if not text:
        return None
    try:
        if embedder is None:
            # probe=False: skip the per-provider ping that get_embedder()
            # does by default. On tight free-tier RPM caps the probe
            # alone burns the rate budget before we reach the real
            # embed call. If the chosen provider is misconfigured we
            # find out from the real call below — same error class,
            # one fewer API hit.
            embedder = get_embedder(probe=False)
        arr = embedder.embed([text])
        if arr is None or len(arr) == 0:
            return None
        vec = np.asarray(arr[0], dtype=np.float32)
        norm = float(np.linalg.norm(vec))
        if not np.isfinite(norm) or norm == 0:
            return None
        return vector_to_blob(vec), norm, int(vec.shape[0]), embedder.model_name()
    except Exception as e:
        log.warning("compute_corpus_embedding failed for %s: %s", corpus.get("id"), e)
        return None


def update_corpus_embedding(corpus_id: str, *, embedder: Optional[EmbeddingProvider] = None) -> bool:
    """Recompute and persist the corpus's profile embedding. Returns True
    on success, False if skipped (empty profile, no embedder, etc.).
    Safe to call repeatedly — overwrites the previous vector."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM corpora WHERE id=?", (corpus_id,)).fetchone()
    if not row:
        return False
    result = compute_corpus_embedding(dict(row), embedder=embedder)
    if not result:
        return False
    vec_bytes, norm, _dim, _model = result
    # Wrap bytes for psycopg in cloud mode; passthrough for sqlite.
    from noosphere.core.db import pg_binary  # local import to avoid cycle at module load
    payload = pg_binary(vec_bytes)
    # Only touch the corpus-vector columns. `embedding_model` and
    # `embedding_dim` are owned by the chunks indexer (they describe the
    # per-passage model used for retrieval), and overwriting them here
    # would conflate two distinct embedding pipelines. The corpus vector
    # gets its dim inferred at load time from blob length / 4 (float32).
    # Also clear the dirty flag — re-embed is what dirty was waiting for.
    conn.execute(
        "UPDATE corpora "
        "SET corpus_vector=?, corpus_vector_norm=?, corpus_vector_dirty_since=NULL "
        "WHERE id=?",
        (payload, norm, corpus_id),
    )
    conn.commit()
    return True


def update_corpus_embeddings_batch(corpus_ids: list[str]) -> dict:
    """Embed and store profile vectors for several corpora in a single
    embedder API call. Strictly faster + cheaper than calling
    update_corpus_embedding() in a loop:

      - One embed() invocation regardless of N (Gemini's
        batchEmbedContents accepts up to 100 inputs per request, so a
        backfill of 8 corpora = 1 RPM hit, not 8).
      - Single get_embedder() probe — auth/geo-block check once.
      - Multi-key rotation in GeminiEmbedder operates on the whole
        batch, so one exhausted key still serves the rest.

    Returns {"succeeded": [...ids], "failed": [{"id":..., "error":...}],
            "embedder": "<model_name>" | None}.
    Best-effort: empty list of ids → empty result; embedder unavailable
    → all ids reported as failed with the same error message; partial
    DB write failures are bucketed per-corpus.
    """
    out = {"succeeded": [], "failed": [], "embedder": None}
    if not corpus_ids:
        return out

    conn = get_conn()
    placeholders = ",".join(["?"] * len(corpus_ids))
    rows = conn.execute(
        f"SELECT * FROM corpora WHERE id IN ({placeholders})",
        tuple(corpus_ids),
    ).fetchall()

    # Pre-compute profile texts. Skip corpora whose profiles are empty
    # (no name + no description + nothing) — they'd produce a useless
    # embedding and waste a slot in the API batch.
    pending: list[tuple[str, str]] = []  # (corpus_id, profile_text)
    for r in rows:
        cd = dict(r)
        text = build_corpus_profile_text(cd)
        if not text:
            out["failed"].append({"id": cd["id"], "error": "empty profile text"})
            continue
        pending.append((cd["id"], text))

    if not pending:
        return out

    # Resolve embedder WITHOUT the auth probe. The probe in get_embedder()
    # makes a ping API call per configured provider (gemini, openai,
    # zhipu) before doing useful work — fast-fails on bad keys / geo-
    # blocks, but on tight free-tier RPM caps the probe alone burns the
    # rate budget before we ever reach the real batch. probe=False
    # returns the first configured provider blindly; if its keys are
    # exhausted we'll find out from the real batch call below, which
    # surfaces the actual error rather than the probe's stale ping
    # error. Same trade Feynman makes for its 50-mind embed runs.
    try:
        embedder = get_embedder(probe=False)
        out["embedder"] = embedder.model_name()
    except Exception as e:
        msg = f"no embedder available: {str(e)[:200]}"
        for cid, _ in pending:
            out["failed"].append({"id": cid, "error": msg})
        return out

    # Single batched API call. With Gemini's batchEmbedContents this
    # carries up to 100 texts in one HTTP request → one RPM hit total.
    # If this provider's keys are exhausted, fall through to the next
    # provider in the chain (OpenAI → Zhipu), batching against each.
    # Mirrors the probe's chain semantics but on real work, not pings.
    texts = [t for _, t in pending]
    arr = None
    last_err = None
    chain_attempts: list[str] = []
    try:
        arr = embedder.embed(texts)
    except Exception as e:
        last_err = e
        chain_attempts.append(f"{embedder.model_name()}: {str(e)[:160]}")
        # Try the rest of the chain.
        from noosphere.core.embeddings import (
            GEMINI_API_KEY, OPENAI_API_KEY, ZHIPU_API_KEY,
            GeminiEmbedder, OpenAIEmbedder, ZhipuEmbedder,
        )
        candidates = []
        if GEMINI_API_KEY: candidates.append(("gemini", GeminiEmbedder))
        if OPENAI_API_KEY: candidates.append(("openai", OpenAIEmbedder))
        if ZHIPU_API_KEY: candidates.append(("zhipu", ZhipuEmbedder))
        # Skip the one we already tried.
        for name, cls in candidates:
            if cls is type(embedder):
                continue
            try:
                alt = cls()
                arr = alt.embed(texts)
                embedder = alt
                out["embedder"] = alt.model_name()
                last_err = None
                break
            except Exception as e2:
                last_err = e2
                chain_attempts.append(f"{name}: {str(e2)[:160]}")
                continue
    if arr is None:
        msg = "embed batch failed across providers: " + " / ".join(chain_attempts)
        for cid, _ in pending:
            out["failed"].append({"id": cid, "error": msg[:300]})
        return out

    if arr is None or len(arr) != len(pending):
        for cid, _ in pending:
            out["failed"].append({
                "id": cid,
                "error": f"embedder returned wrong shape: got {0 if arr is None else len(arr)}, expected {len(pending)}",
            })
        return out

    # Persist each vector. Per-row try/except so a single bad write
    # doesn't lose the rest.
    from noosphere.core.db import pg_binary
    for (cid, _), vec in zip(pending, arr):
        try:
            v = np.asarray(vec, dtype=np.float32)
            norm = float(np.linalg.norm(v))
            if not np.isfinite(norm) or norm == 0:
                out["failed"].append({"id": cid, "error": "zero/non-finite norm"})
                continue
            payload = pg_binary(vector_to_blob(v))
            conn.execute(
                "UPDATE corpora "
                "SET corpus_vector=?, corpus_vector_norm=?, "
                "    corpus_vector_dirty_since=NULL "
                "WHERE id=?",
                (payload, norm, cid),
            )
            out["succeeded"].append(cid)
        except Exception as e:
            out["failed"].append({"id": cid, "error": f"db write failed: {str(e)[:200]}"})
    conn.commit()
    return out


def mark_corpus_embedding_dirty(corpus_id: str) -> None:
    """Flag a corpus as needing a profile-vector refresh. Cheap UPDATE
    — does NOT call the embedder. The next /corpora/network view
    triggers the actual recompute via the lazy-backfill path. Idempotent:
    re-marking an already-dirty corpus is a no-op (we keep the earliest
    dirty timestamp so debugging can answer "how long has this been
    stale?").

    Best-effort: any DB failure (column missing on a half-migrated
    deployment, etc.) is swallowed so the caller's primary work isn't
    affected. Worst case the graph just shows the older vector for a
    while longer.
    """
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        get_conn().execute(
            "UPDATE corpora SET corpus_vector_dirty_since=? "
            "WHERE id=? AND corpus_vector_dirty_since IS NULL",
            (now, corpus_id),
        )
        get_conn().commit()
    except Exception as e:
        log.debug("mark_corpus_embedding_dirty failed for %s: %s", corpus_id, e)


def load_corpus_vectors(corpus_ids: Optional[list[str]] = None) -> list[dict]:
    """Load (id, vec, norm, dim) for corpora that have a profile embedding.
    Skips rows missing either column — those didn't run through the
    pipeline yet (pre-existing corpora before backfill, or corpora
    created without an embedder configured). Used by the network endpoint
    to compute pair-wise cosine similarity without requiring every corpus
    to be embedded.
    """
    conn = get_conn()
    if corpus_ids:
        placeholders = ",".join(["?"] * len(corpus_ids))
        rows = conn.execute(
            f"SELECT id, corpus_vector, corpus_vector_norm "
            f"FROM corpora "
            f"WHERE id IN ({placeholders}) "
            f"AND corpus_vector IS NOT NULL "
            f"AND corpus_vector_norm IS NOT NULL",
            tuple(corpus_ids),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, corpus_vector, corpus_vector_norm "
            "FROM corpora "
            "WHERE corpus_vector IS NOT NULL "
            "AND corpus_vector_norm IS NOT NULL"
        ).fetchall()
    out = []
    for r in rows:
        try:
            blob = bytes(r["corpus_vector"])  # works for sqlite + psycopg memoryview
            # Dim inferred from blob length / 4 (float32 = 4 bytes). We
            # intentionally don't reuse the corpora.embedding_dim column,
            # which describes the chunk-indexing model — corpus profile
            # vectors are a separate pipeline that may use a different
            # embedder (e.g. operator changes EMBEDDING_PROVIDER between
            # runs). Inferring locally keeps the two decoupled.
            dim = len(blob) // 4
            if dim == 0:
                continue
            vec = blob_to_vector(blob, dim)
            out.append({
                "id": r["id"],
                "vec": vec,
                "norm": float(r["corpus_vector_norm"]),
                "dim": dim,
            })
        except Exception as e:
            log.debug("skip corpus %s: %s", r["id"], e)
    return out
