"""Tests for citation graph + kb_reputation (M3)."""

import pytest

from noosphere.core.citations import (
    CITATION_SATURATION_K,
    KIND_MANIFEST,
    KIND_ROUTE,
    citation_count_in,
    citations_in,
    citations_out,
    compute_kb_reputation,
    delete_citation,
    record_citation,
    refresh_all_kb_reputations,
    refresh_kb_reputation,
    upsert_manifest_citation,
    weighted_citation_score_in,
)
from noosphere.core.corpus import create_corpus, get_corpus


# ── record / list ──────────────────────────────────────────────────


def test_record_citation_inserts_row():
    a = create_corpus("A")
    b = create_corpus("B")
    edge = record_citation(a["id"], b["id"], KIND_MANIFEST, context="tested")
    assert edge["kind"] == KIND_MANIFEST
    assert edge["weight"] == 1.0
    assert citation_count_in(b["id"]) == 1
    assert citation_count_in(a["id"]) == 0


def test_record_citation_rejects_self_citation():
    a = create_corpus("A")
    with pytest.raises(ValueError, match="cannot cite itself"):
        record_citation(a["id"], a["id"], KIND_MANIFEST)


def test_record_citation_rejects_unknown_kind():
    a = create_corpus("A")
    b = create_corpus("B")
    with pytest.raises(ValueError, match="unknown kind"):
        record_citation(a["id"], b["id"], "garbage")


def test_upsert_manifest_citation_is_idempotent():
    a = create_corpus("A")
    b = create_corpus("B")
    upsert_manifest_citation(a["id"], b["id"])
    upsert_manifest_citation(a["id"], b["id"])
    upsert_manifest_citation(a["id"], b["id"])
    assert citation_count_in(b["id"], kind=KIND_MANIFEST) == 1


def test_citations_out_and_in_lists():
    a = create_corpus("A")
    b = create_corpus("B")
    c = create_corpus("C")
    record_citation(a["id"], b["id"], KIND_MANIFEST)
    record_citation(a["id"], c["id"], KIND_MANIFEST)
    record_citation(c["id"], b["id"], KIND_MANIFEST)

    out_a = citations_out(a["id"])
    in_b = citations_in(b["id"])
    assert {e["cited_corpus_id"] for e in out_a} == {b["id"], c["id"]}
    assert {e["citing_corpus_id"] for e in in_b} == {a["id"], c["id"]}


def test_delete_citation_removes_it():
    a = create_corpus("A")
    b = create_corpus("B")
    edge = record_citation(a["id"], b["id"], KIND_MANIFEST)
    assert citation_count_in(b["id"]) == 1
    assert delete_citation(edge["id"]) is True
    assert citation_count_in(b["id"]) == 0


# ── weighting / kb_reputation ─────────────────────────────────────


def test_weighted_score_uses_citing_reputation():
    a = create_corpus("High Rep")
    b = create_corpus("Low Rep")
    target = create_corpus("Target")

    # Set reputations directly
    from noosphere.core.db import get_conn
    get_conn().execute("UPDATE corpora SET kb_reputation=? WHERE id=?", (0.8, a["id"]))
    get_conn().execute("UPDATE corpora SET kb_reputation=? WHERE id=?", (0.1, b["id"]))
    get_conn().commit()

    record_citation(a["id"], target["id"], KIND_MANIFEST)
    score_with_high = weighted_citation_score_in(target["id"])
    # Add a low-rep citation; score should grow by less per edge
    record_citation(b["id"], target["id"], KIND_MANIFEST)
    score_with_both = weighted_citation_score_in(target["id"])
    # The delta from adding a low-rep citing KB is smaller than adding a high-rep one.
    delta_low = score_with_both - score_with_high
    assert delta_low > 0
    assert delta_low < score_with_high  # high-rep edge contributed more


def test_kb_reputation_cold_start_baseline():
    """v2a baseline: calibration stub 0.5 * 0.2 = 0.1, plus satisfaction
    default 1.0 * 0.1 = 0.1 when no paid traffic → KBR floor ≈ 0.2."""
    target = create_corpus("cold start")
    kbr = compute_kb_reputation(target["id"])
    # 0.4 * 0 + 0.3 * 0 + 0.2 * 0.5 + 0.1 * 1.0 = 0.2
    assert 0.19 < kbr < 0.21


def test_kb_reputation_citation_lifts_above_baseline():
    a = create_corpus("citer")
    target = create_corpus("target")
    from noosphere.core.db import get_conn
    get_conn().execute("UPDATE corpora SET kb_reputation=? WHERE id=?", (1.0, a["id"]))
    get_conn().commit()

    base = compute_kb_reputation(target["id"])
    record_citation(a["id"], target["id"], KIND_MANIFEST)
    after = compute_kb_reputation(target["id"])
    # Adding a strong citation lifts KBR: weighted_score = 1, citation_term = 1/6,
    # delta = 0.4 * 1/6 ≈ 0.067
    assert after > base
    assert 0.06 < (after - base) < 0.08


def test_refresh_kb_reputation_persists_to_row():
    a = create_corpus("A")
    target = create_corpus("target")
    from noosphere.core.db import get_conn
    get_conn().execute("UPDATE corpora SET kb_reputation=? WHERE id=?", (1.0, a["id"]))
    get_conn().commit()
    record_citation(a["id"], target["id"], KIND_MANIFEST)

    kbr = refresh_kb_reputation(target["id"])
    assert kbr > 0
    fetched = get_corpus(target["id"])
    assert abs(fetched["kb_reputation"] - kbr) < 1e-6


def test_refresh_all_kb_reputations_runs_through_all():
    a = create_corpus("A")
    b = create_corpus("B")
    c = create_corpus("C")
    record_citation(a["id"], b["id"], KIND_MANIFEST)
    record_citation(b["id"], c["id"], KIND_MANIFEST)

    n = refresh_all_kb_reputations()
    assert n == 3
    # After two-pass refresh, C's reputation should be boosted above baseline
    # via a → b → c chain.
    base = compute_kb_reputation(create_corpus("baseline")["id"])
    assert get_corpus(c["id"])["kb_reputation"] > base


# ── KBR v2 terms: retention / satisfaction ─────────────────────────


def test_query_retention_cold_start_returns_zero():
    from noosphere.core.citations import query_retention_score
    c = create_corpus("Retention Cold")
    assert query_retention_score(c["id"]) == 0.0


def test_query_retention_high_when_agents_come_back():
    from datetime import datetime, timezone
    from noosphere.core.citations import query_retention_score
    from noosphere.core.db import get_conn
    c = create_corpus("Retention Hot")
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    # 10 queries from 3 repeat agents (all repeat) + 1 query from a one-off agent
    for i in range(10):
        agent = f"repeat_{i % 3}"
        conn.execute(
            "INSERT INTO query_logs (id, corpus_id, agent_id, created_at) VALUES (?,?,?,?)",
            (f"q{i}", c["id"], agent, now),
        )
    conn.execute(
        "INSERT INTO query_logs (id, corpus_id, agent_id, created_at) VALUES (?,?,?,?)",
        ("q-oneoff", c["id"], "oneoff", now),
    )
    conn.commit()
    score = query_retention_score(c["id"])
    # repeat rate = 10/11 ≈ 0.91, doubled and clipped → 1.0
    assert score == 1.0


def test_satisfaction_score_cold_start_is_trusting():
    from noosphere.core.citations import satisfaction_score
    c = create_corpus("Sat Cold")
    assert satisfaction_score(c["id"]) == 1.0


def test_satisfaction_score_penalizes_refunds():
    from datetime import datetime, timezone
    from noosphere.core.citations import satisfaction_score
    from noosphere.core.db import get_conn
    c = create_corpus("Sat Hot")
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    # 10 completed + 2 refunded = 12 paid, refund rate 2/12 ≈ 0.167
    for i in range(10):
        conn.execute(
            """INSERT INTO payments (id, corpus_id, payment_type, amount_cents,
                                      status, created_at)
               VALUES (?,?,?,?,?,?)""",
            (f"pc{i}", c["id"], "per_query", 100, "completed", now),
        )
    for i in range(2):
        conn.execute(
            """INSERT INTO payments (id, corpus_id, payment_type, amount_cents,
                                      status, created_at)
               VALUES (?,?,?,?,?,?)""",
            (f"pr{i}", c["id"], "per_query", 100, "refunded", now),
        )
    conn.commit()
    score = satisfaction_score(c["id"])
    assert 0.82 < score < 0.84


def test_calibration_score_is_stubbed():
    from noosphere.core.citations import CALIBRATION_STUB, calibration_score
    c = create_corpus("Calib")
    assert calibration_score(c["id"]) == CALIBRATION_STUB == 0.5


def test_kb_reputation_combines_all_four_terms():
    """Fully-active KB (cited, repeat traffic, paid without refunds) scores well
    above the cold-start baseline."""
    from datetime import datetime, timezone
    from noosphere.core.db import get_conn
    citer = create_corpus("Citer")
    target = create_corpus("Active Target")
    get_conn().execute("UPDATE corpora SET kb_reputation=? WHERE id=?", (1.0, citer["id"]))
    get_conn().commit()
    record_citation(citer["id"], target["id"], KIND_MANIFEST)

    # Repeat agent traffic
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    for i in range(12):
        conn.execute(
            "INSERT INTO query_logs (id, corpus_id, agent_id, created_at) VALUES (?,?,?,?)",
            (f"q{i}", target["id"], f"a{i % 3}", now),
        )
    # Paid with no refunds
    for i in range(10):
        conn.execute(
            """INSERT INTO payments (id, corpus_id, payment_type, amount_cents, status, created_at)
               VALUES (?,?,?,?,?,?)""",
            (f"p{i}", target["id"], "per_query", 100, "completed", now),
        )
    conn.commit()

    kbr = compute_kb_reputation(target["id"])
    # citation ~0.067 + retention 0.3*1.0 + calibration 0.2*0.5 + satisfaction 0.1*1.0
    # ≈ 0.067 + 0.3 + 0.1 + 0.1 = 0.567
    assert 0.55 < kbr < 0.58


# ── REST citations endpoints ───────────────────────────────────────


def test_api_record_and_list_citations(client):
    r_a = client.post("/api/v1/corpora", json={"name": "RA"})
    r_b = client.post("/api/v1/corpora", json={"name": "RB"})
    a_id = r_a.json()["id"]
    b_id = r_b.json()["id"]

    r = client.post(
        f"/api/v1/corpora/{a_id}/citations",
        json={"cited_corpus_id": b_id, "context": "recommended"},
    )
    assert r.status_code == 200

    out = client.get(f"/api/v1/corpora/{a_id}/citations?direction=out").json()
    assert len(out["citations"]) == 1
    assert out["citations"][0]["cited_corpus_id"] == b_id

    in_ = client.get(f"/api/v1/corpora/{b_id}/citations?direction=in").json()
    assert len(in_["citations"]) == 1


def test_api_record_citation_rejects_self(client):
    r = client.post("/api/v1/corpora", json={"name": "RSelf"})
    cid = r.json()["id"]
    r = client.post(f"/api/v1/corpora/{cid}/citations", json={"cited_corpus_id": cid})
    assert r.status_code == 400


# ── route ──────────────────────────────────────────────────────────


def test_route_excludes_source_and_private(client):
    r_source = client.post("/api/v1/corpora", json={
        "name": "Source KB", "description": "general",
    })
    r_target = client.post("/api/v1/corpora", json={
        "name": "Python Advice", "description": "python programming guidance",
        "tags": ["python", "programming"],
    })
    r_priv = client.post("/api/v1/corpora", json={
        "name": "Private Python", "description": "python secrets",
        "access_level": "private",
    })
    source_id = r_source.json()["id"]
    target_id = r_target.json()["id"]
    priv_id = r_priv.json()["id"]

    r = client.post(
        f"/api/v1/corpora/{source_id}/route",
        json={"question": "python tips"},
    )
    assert r.status_code == 200
    body = r.json()
    ids = {c["corpus_id"] for c in body["candidates"]}
    assert target_id in ids
    assert source_id not in ids
    assert priv_id not in ids


def test_route_boosts_endorsed_corpora(client):
    r_source = client.post("/api/v1/corpora", json={"name": "Source"})
    r_plain = client.post("/api/v1/corpora", json={
        "name": "Python Plain", "description": "relevant to python", "tags": ["python"],
    })
    r_endorsed = client.post("/api/v1/corpora", json={
        "name": "Unrelated Name", "description": "totally different topic",
    })
    source_id = r_source.json()["id"]
    plain_id = r_plain.json()["id"]
    endorsed_id = r_endorsed.json()["id"]

    # Endorse the unrelated one explicitly
    client.post(
        f"/api/v1/corpora/{source_id}/citations",
        json={"cited_corpus_id": endorsed_id},
    )

    r = client.post(
        f"/api/v1/corpora/{source_id}/route",
        json={"question": "python"},
    )
    body = r.json()
    ids = {c["corpus_id"] for c in body["candidates"]}
    # Endorsed corpus should appear even without text match
    assert endorsed_id in ids
    # And a text-relevant one should too
    assert plain_id in ids


def test_route_404_for_unknown(client):
    r = client.post(
        "/api/v1/corpora/nonexistent000/route",
        json={"question": "x"},
    )
    assert r.status_code == 404


# ── MCP route tool ─────────────────────────────────────────────────


def test_mcp_route_tool_returns_candidates():
    from noosphere.mcp.server import handle_tool_call
    source = create_corpus("MCP Source")
    create_corpus("Python One", description="python docs", tags=["python"])
    result = handle_tool_call("route", {
        "corpus_id": source["id"],
        "question": "python",
    })
    assert "candidates" in result
    assert result["source_corpus_id"] == source["id"]


def test_mcp_route_blocked_on_private():
    from noosphere.mcp.server import handle_tool_call
    priv = create_corpus("Priv Source", access_level="private")
    result = handle_tool_call("route", {
        "corpus_id": priv["id"],
        "question": "x",
    })
    assert "error" in result


# ── describe exposes kb_reputation ─────────────────────────────────


def test_describe_includes_kb_reputation():
    from noosphere.core.kb_agent import describe
    c = create_corpus("With Rep")
    from noosphere.core.db import get_conn
    get_conn().execute("UPDATE corpora SET kb_reputation=? WHERE id=?", (0.42, c["id"]))
    get_conn().commit()
    card = describe(c["id"])
    assert card["kb_reputation"] == 0.42
