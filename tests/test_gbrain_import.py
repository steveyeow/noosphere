"""Tests for the GBrain repo importer — importers.import_gbrain_repo."""

import json

import pytest

from noosphere.core.corpus import create_corpus
from noosphere.core.db import get_conn
from noosphere.core.entities import get_entity, list_entities
from noosphere.core.importers import import_gbrain_repo

JANE_TRUTH = "Jane Doe is a founder building developer tooling."
JANE_TIMELINE_ONLY = "Met at the 2026 kickoff and discussed pricing."


@pytest.fixture(autouse=True)
def _no_index(monkeypatch):
    """Skip embedding/index in import tests — no network, fast."""
    monkeypatch.setattr(
        "noosphere.core.importers.index_corpus", lambda *a, **k: {"chunk_count": 0}
    )


@pytest.fixture
def corpus():
    return create_corpus("GBrain Test")


@pytest.fixture
def brain(tmp_path):
    root = tmp_path / "brain"
    (root / "people").mkdir(parents=True)
    (root / "companies").mkdir(parents=True)
    (root / "concepts").mkdir(parents=True)
    (root / "meetings").mkdir(parents=True)
    (root / ".raw").mkdir(parents=True)
    (root / "archive").mkdir(parents=True)

    (root / "people" / "jane-doe.md").write_text(
        "---\n"
        "type: person\n"
        "aliases: [Jane D, JD]\n"
        "tags: [founder]\n"
        "---\n"
        "# Jane Doe\n\n"
        f"{JANE_TRUTH}\n\n"
        "## State\n- Role: Founder\n"
        "Works with [Acme](../companies/acme.md) and knows [[john-smith]].\n\n"
        "---\n\n"
        "## Timeline\n"
        f"- 2026-01-10 | meeting — {JANE_TIMELINE_ONLY}\n"
    )
    (root / "people" / "john-smith.md").write_text(
        "# John Smith\n\nEngineer. No frontmatter on this page.\n"
    )
    (root / "companies" / "acme.md").write_text(
        "---\ntype: company\n---\n"
        "# Acme\n\nAcme builds widgets.\n\n"
        "## State\n- Founders: [Jane Doe](../people/jane-doe.md)\n\n"
        "---\n\n## Timeline\n- 2025-09-01 | Series A\n"
    )
    (root / "concepts" / "product-market-fit.md").write_text(
        "---\ntype: concept\n---\n"
        "# Product-Market Fit\n\nWhen the product satisfies a strong market.\n"
    )
    (root / "meetings" / "2026-01-kickoff.md").write_text(
        "# 2026 Kickoff\n\nNotes from the kickoff with [Jane Doe](../people/jane-doe.md).\n"
    )
    # Must all be skipped:
    (root / "index.md").write_text("# Index\n- catalog\n")
    (root / "log.md").write_text("# Log\n- 2026 ingest\n")
    (root / "RESOLVER.md").write_text("# Resolver\n")
    (root / "schema.md").write_text("# Schema\n")
    (root / ".raw" / "jane-doe.md").write_text("raw sidecar, skip me\n")
    (root / "archive" / "dead.md").write_text("# Dead page\n")
    return root


def _docs(corpus_id):
    rows = get_conn().execute(
        "SELECT id, title, doc_type, tags, metadata_json FROM documents "
        "WHERE corpus_id=?",
        (corpus_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def test_counts_and_skips(corpus, brain):
    r = import_gbrain_repo(corpus["id"], str(brain))
    assert r["entities"] == 3          # jane, john, acme
    assert r["concepts"] == 1          # product-market-fit
    assert r["sources"] == 1           # the meeting
    # meta files index/log/RESOLVER/schema (4) + archive/dead (1) counted as
    # skipped; .raw/ is a dot-dir, excluded from consideration entirely.
    assert r["skipped"] >= 5
    assert r["errors"] == 0

    titles = {d["title"] for d in _docs(corpus["id"])}
    assert "Index" not in titles and "Log" not in titles
    assert "Dead Page" not in titles and "Resolver" not in titles
    assert "Schema" not in titles
    # .raw sidecar content never imported
    assert all("raw sidecar" not in (d["title"] or "") for d in _docs(corpus["id"]))


def test_entity_kinds_and_compiled_truth(corpus, brain):
    import_gbrain_repo(corpus["id"], str(brain))
    ents = {e["canonical_name"]: e for e in list_entities(corpus["id"])}

    assert ents["Jane Doe"]["kind"] == "person"
    assert ents["Acme"]["kind"] == "organization"
    assert ents["John Smith"]["kind"] == "person"

    jane = get_entity(ents["Jane Doe"]["id"])
    # description == compiled truth (above the ---), timeline excluded
    assert JANE_TRUTH in jane["description"]
    assert JANE_TIMELINE_ONLY not in jane["description"]
    assert "Jane D" in jane["aliases"] and "JD" in jane["aliases"]
    # gbrain on-disk link syntax is stripped to clean prose in the description
    assert "](" not in jane["description"] and "[[" not in jane["description"]
    assert "Acme" in jane["description"]  # link text preserved, syntax gone


def test_concept_doc_type(corpus, brain):
    import_gbrain_repo(corpus["id"], str(brain))
    concept = [d for d in _docs(corpus["id"]) if d["title"] == "Product-Market Fit"]
    assert concept and concept[0]["doc_type"] == "concept"


def test_cross_links_resolve_to_entities(corpus, brain):
    import_gbrain_repo(corpus["id"], str(brain))
    ents = {e["canonical_name"]: e for e in list_entities(corpus["id"])}
    acme_id = ents["Acme"]["id"]
    john_id = ents["John Smith"]["id"]
    jane_id = ents["Jane Doe"]["id"]

    jane_doc = [d for d in _docs(corpus["id"]) if d["title"] == "Jane Doe"][0]
    meta = json.loads(jane_doc["metadata_json"])
    mentioned = meta.get("mentioned_entity_ids") or []

    # markdown link → Acme, wikilink → John Smith, both resolved
    assert acme_id in mentioned
    assert john_id in mentioned
    # the page is attached to its own entity (so it renders on Jane's
    # entity page) exactly once — pass 2 must not duplicate it
    assert mentioned.count(jane_id) == 1


def test_classify_edge_type():
    from noosphere.core.entities import classify_edge_type
    assert classify_edge_type("Founders") == "founded"
    assert classify_edge_type("Role") == "works_at"
    assert classify_edge_type("Close to") == "close_to"
    assert classify_edge_type("State") == "related"
    assert classify_edge_type("") == "related"


def test_typed_edges_and_backlinks(corpus, brain):
    from noosphere.core.entities import get_entity_edges
    import_gbrain_repo(corpus["id"], str(brain))
    ents = {e["canonical_name"]: e for e in list_entities(corpus["id"])}
    jane, acme = ents["Jane Doe"]["id"], ents["Acme"]["id"]

    je = get_entity_edges(jane)
    out = {(o["name"], o["type"]) for o in je["outbound"]}
    # Jane's page links Acme + John under "## State" → untyped 'related'
    assert ("Acme", "related") in out
    assert ("John Smith", "related") in out
    # Acme lists Jane under "Founders:" → typed 'founded', appears as a
    # backlink on Jane (inbound)
    assert any(i["name"] == "Acme" and i["type"] == "founded" for i in je["inbound"])

    ae = get_entity_edges(acme)
    assert any(o["name"] == "Jane Doe" and o["type"] == "founded" for o in ae["outbound"])
    assert any(i["name"] == "Jane Doe" and i["type"] == "related" for i in ae["inbound"])
    # never a self-edge
    assert all(o["entity_id"] != jane for o in je["outbound"])


def test_idempotent_reimport(corpus, brain):
    import_gbrain_repo(corpus["id"], str(brain))
    r2 = import_gbrain_repo(corpus["id"], str(brain))
    # entities dedupe by (kind, name) — still exactly 3
    assert len(list_entities(corpus["id"])) == 3
    assert r2["entities"] == 3
