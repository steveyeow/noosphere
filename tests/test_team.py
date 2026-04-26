"""T-1 team-workspace tests: orgs, members, invites, permissions, attribution, audit log.

Covers the T-1 milestone definition of done end-to-end:
    A self-hosted user can create an org, invite a teammate via shared link,
    both ingest into the same corpus, both see contributor names on
    documents, and a third non-member is correctly rejected — all with audit
    log entries recorded.
"""

import pytest

from fastapi.testclient import TestClient

from noosphere.api.main import app
from noosphere.core import orgs as orgs_mod
from noosphere.core.corpus import LOCAL_OWNER_ID, create_corpus, get_corpus
from noosphere.core.db import get_conn


# ── Helpers ─────────────────────────────────────────────────────────


def _client(user_id: str | None = None, workspace: str = "personal"):
    """A TestClient pre-wired with team-workspace headers.

    Self-hosted mode is detected via X-Noosphere-User-Id header (cloud is off
    in tests). Pass ``user_id=None`` to imitate the localhost operator —
    `_get_user_id` will fall back to ``"local"`` in that case.
    """
    c = TestClient(app)
    headers = {"X-Noosphere-Workspace": workspace}
    if user_id is not None:
        headers["X-Noosphere-User-Id"] = user_id
    c.headers.update(headers)
    return c


def _create_org(c: TestClient, name="Acme") -> dict:
    r = c.post("/api/v1/orgs", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


# ── Schema / model layer ────────────────────────────────────────────


def test_xor_constraint_blocks_owner_and_org_both_set(isolated_db):
    org = orgs_mod.create_org("Acme", owner_user_id="alice")
    with pytest.raises(Exception):
        get_conn().execute(
            "INSERT INTO corpora(id,name,slug,owner_id,org_id,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            ("c1", "x", "xor-both", "alice", org["id"], "2026-01-01", "2026-01-01"),
        )
        get_conn().commit()


def test_create_corpus_defaults_owner_to_local_sentinel(isolated_db):
    c = create_corpus("Solo")
    assert c["owner_id"] == LOCAL_OWNER_ID
    assert c.get("org_id") in (None, "")


def test_create_corpus_with_org_id_clears_owner(isolated_db):
    org = orgs_mod.create_org("Acme", owner_user_id="alice")
    c = create_corpus("Team KB", org_id=org["id"])
    assert c.get("org_id") == org["id"]
    assert c.get("owner_id") in (None, "")


def test_create_corpus_rejects_both_owner_and_org(isolated_db):
    org = orgs_mod.create_org("Acme", owner_user_id="alice")
    with pytest.raises(ValueError):
        create_corpus("Mixed", owner_id="alice", org_id=org["id"])


# ── Org CRUD via API ────────────────────────────────────────────────


def test_create_org_makes_caller_the_owner(isolated_db):
    c = _client(user_id="alice")
    org = _create_org(c)
    assert org["slug"]
    members = c.get(f"/api/v1/orgs/{org['id']}/members").json()
    assert any(m["user_id"] == "alice" and m["role"] == orgs_mod.ROLE_OWNER for m in members)


def test_get_org_requires_membership(isolated_db):
    a = _client(user_id="alice")
    org = _create_org(a)
    bob = _client(user_id="bob")
    assert bob.get(f"/api/v1/orgs/{org['id']}").status_code == 403


def test_patch_org_requires_admin(isolated_db):
    a = _client(user_id="alice")
    org = _create_org(a)
    a.post(f"/api/v1/orgs/{org['id']}/invites", json={"role": "editor"})
    invite = a.get(f"/api/v1/orgs/{org['id']}/invites").json()[0]
    bob = _client(user_id="bob")
    bob.post(f"/api/v1/orgs/invites/{invite['token']}/accept")
    # Editor Bob can't rename the org.
    r = bob.patch(f"/api/v1/orgs/{org['id']}", json={"name": "Hijacked"})
    assert r.status_code == 403


def test_delete_org_owner_only(isolated_db):
    a = _client(user_id="alice")
    org = _create_org(a)
    a.post(f"/api/v1/orgs/{org['id']}/invites", json={"role": "admin"})
    invite = a.get(f"/api/v1/orgs/{org['id']}/invites").json()[0]
    bob = _client(user_id="bob")
    bob.post(f"/api/v1/orgs/invites/{invite['token']}/accept")
    # Admin can't delete.
    assert bob.delete(f"/api/v1/orgs/{org['id']}").status_code == 403
    # Owner can.
    assert a.delete(f"/api/v1/orgs/{org['id']}").status_code == 200


# ── Members + invites ──────────────────────────────────────────────


def test_invite_create_accept_flow(isolated_db):
    a = _client(user_id="alice")
    org = _create_org(a)
    a.post(f"/api/v1/orgs/{org['id']}/invites", json={"role": "editor"})
    invite = a.get(f"/api/v1/orgs/{org['id']}/invites").json()[0]
    bob = _client(user_id="bob")
    r = bob.post(f"/api/v1/orgs/invites/{invite['token']}/accept")
    assert r.status_code == 200
    member = r.json()
    assert member["user_id"] == "bob" and member["role"] == "editor"
    members = a.get(f"/api/v1/orgs/{org['id']}/members").json()
    assert {m["user_id"] for m in members} == {"alice", "bob"}


def test_invite_single_use(isolated_db):
    a = _client(user_id="alice")
    org = _create_org(a)
    a.post(f"/api/v1/orgs/{org['id']}/invites", json={"role": "editor"})
    invite = a.get(f"/api/v1/orgs/{org['id']}/invites").json()[0]
    bob = _client(user_id="bob")
    bob.post(f"/api/v1/orgs/invites/{invite['token']}/accept")
    carol = _client(user_id="carol")
    r = carol.post(f"/api/v1/orgs/invites/{invite['token']}/accept")
    assert r.status_code == 400


def test_invite_revoke_blocks_accept(isolated_db):
    a = _client(user_id="alice")
    org = _create_org(a)
    a.post(f"/api/v1/orgs/{org['id']}/invites", json={"role": "editor"})
    invite = a.get(f"/api/v1/orgs/{org['id']}/invites").json()[0]
    a.delete(f"/api/v1/orgs/{org['id']}/invites/{invite['id']}")
    bob = _client(user_id="bob")
    r = bob.post(f"/api/v1/orgs/invites/{invite['token']}/accept")
    assert r.status_code == 400


def test_role_change_and_last_owner_protection(isolated_db):
    a = _client(user_id="alice")
    org = _create_org(a)
    # Adding a second member as editor.
    a.post(f"/api/v1/orgs/{org['id']}/invites", json={"role": "editor"})
    invite = a.get(f"/api/v1/orgs/{org['id']}/invites").json()[0]
    bob = _client(user_id="bob")
    bob.post(f"/api/v1/orgs/invites/{invite['token']}/accept")
    # Promote Bob to owner — succeeds.
    r = a.patch(f"/api/v1/orgs/{org['id']}/members/bob", json={"role": "owner"})
    assert r.status_code == 200
    # Now demote Alice (still owner) — should also succeed since Bob is owner.
    r = a.patch(f"/api/v1/orgs/{org['id']}/members/alice", json={"role": "admin"})
    assert r.status_code == 200
    # Demote Bob — would leave zero owners, should fail.
    r = bob.patch(f"/api/v1/orgs/{org['id']}/members/bob", json={"role": "admin"})
    assert r.status_code == 400


def test_remove_member_admin_only(isolated_db):
    a = _client(user_id="alice")
    org = _create_org(a)
    a.post(f"/api/v1/orgs/{org['id']}/invites", json={"role": "editor"})
    inv = a.get(f"/api/v1/orgs/{org['id']}/invites").json()[0]
    bob = _client(user_id="bob")
    bob.post(f"/api/v1/orgs/invites/{inv['token']}/accept")
    # Editor can't remove anyone.
    r = bob.delete(f"/api/v1/orgs/{org['id']}/members/bob")
    assert r.status_code == 403
    # Owner can.
    r = a.delete(f"/api/v1/orgs/{org['id']}/members/bob")
    assert r.status_code == 200


# ── Workspace-scoped corpus permissions ────────────────────────────


def _new_org_with_member(role="editor"):
    a = _client(user_id="alice")
    org = _create_org(a)
    a.post(f"/api/v1/orgs/{org['id']}/invites", json={"role": role})
    invite = a.get(f"/api/v1/orgs/{org['id']}/invites").json()[0]
    bob = _client(user_id="bob")
    bob.post(f"/api/v1/orgs/invites/{invite['token']}/accept")
    return org, a, bob


def _scoped(c: TestClient, org_id: str) -> TestClient:
    """Clone a client with the same identity but switched to an org workspace."""
    out = TestClient(app)
    uid = c.headers.get("x-noosphere-user-id")
    if uid:
        out.headers["x-noosphere-user-id"] = uid
    out.headers["x-noosphere-workspace"] = f"org:{org_id}"
    return out


def _create_org_corpus(c: TestClient, org_id: str, name: str = "Team KB") -> dict:
    c2 = _scoped(c, org_id)
    r = c2.post("/api/v1/corpora", json={"name": name, "access_level": "private"})
    assert r.status_code == 200, r.text
    return r.json()


def test_org_corpus_blocked_for_non_member(isolated_db):
    org, alice, _ = _new_org_with_member()
    corpus = _create_org_corpus(alice, org["id"])
    # Carol is not a member.
    carol = _client(user_id="carol")
    # Read attempt — corpus is private, so even non-member gets the
    # standard 403 from access gating.
    r = carol.get(f"/api/v1/corpora/{corpus['id']}")
    assert r.status_code in (401, 403)
    # Write attempt — definitely 403.
    r = carol.post(
        f"/api/v1/corpora/{corpus['id']}/capture",
        json={"content": "sneaky"},
    )
    assert r.status_code in (401, 403)


def test_org_corpus_member_can_read_and_write(isolated_db):
    org, alice, bob = _new_org_with_member()
    corpus = _create_org_corpus(alice, org["id"])
    # Bob switches to the org workspace and ingests.
    bob_org = _scoped(bob, org["id"])
    r = bob_org.post(
        f"/api/v1/corpora/{corpus['id']}/capture",
        json={"content": "Bob's contribution", "title": "From Bob"},
    )
    assert r.status_code == 200, r.text
    bob_doc = r.json()
    assert bob_doc.get("contributor_user_id") == "bob"
    # Alice ingests too.
    alice_org = _scoped(alice, org["id"])
    r = alice_org.post(
        f"/api/v1/corpora/{corpus['id']}/capture",
        json={"content": "Alice's contribution", "title": "From Alice"},
    )
    assert r.status_code == 200
    # Both see contributor attribution on the document list.
    r = bob_org.get(f"/api/v1/corpora/{corpus['id']}/documents")
    assert r.status_code == 200
    contributors = {d.get("contributor_user_id") for d in r.json()}
    assert {"alice", "bob"}.issubset(contributors)


def test_viewer_cannot_write(isolated_db):
    org, alice, _ = _new_org_with_member(role="viewer")
    corpus = _create_org_corpus(alice, org["id"])
    bob = _client(user_id="bob", workspace=f"org:{org['id']}")
    r = bob.post(
        f"/api/v1/corpora/{corpus['id']}/capture",
        json={"content": "denied"},
    )
    assert r.status_code == 403


def test_workspace_list_corpora_scope(isolated_db):
    org, alice, _ = _new_org_with_member()
    _create_org_corpus(alice, org["id"], name="Org Brain")
    # Personal-workspace listing for Alice should NOT contain the org corpus.
    r = alice.get("/api/v1/corpora")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "Org Brain" not in names
    # Org-workspace listing must contain it.
    alice_org = _scoped(alice, org["id"])
    r = alice_org.get("/api/v1/corpora")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "Org Brain" in names


# ── Audit log ──────────────────────────────────────────────────────


def test_audit_log_records_org_lifecycle(isolated_db):
    org, alice, bob = _new_org_with_member()
    corpus = _create_org_corpus(alice, org["id"])
    bob_org = _scoped(bob, org["id"])
    bob_org.post(
        f"/api/v1/corpora/{corpus['id']}/capture",
        json={"content": "Bob's contribution"},
    )
    r = alice.get(f"/api/v1/orgs/{org['id']}/audit-logs?limit=200")
    assert r.status_code == 200
    actions = [row["action"] for row in r.json()]
    # We expect at minimum: org.create, member.invite, invite.accept,
    # corpus.create, doc.ingest.
    for required in ("org.create", "member.invite", "invite.accept",
                     "corpus.create", "doc.ingest"):
        assert required in actions, f"missing audit action: {required}"


def test_audit_log_admin_only(isolated_db):
    org, _alice, bob = _new_org_with_member(role="editor")
    r = bob.get(f"/api/v1/orgs/{org['id']}/audit-logs")
    assert r.status_code == 403


# ── /me reflects active workspace + org list ──────────────────────


def test_me_endpoint_lists_orgs_and_workspace(isolated_db):
    org, alice, _ = _new_org_with_member()
    r = alice.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "alice"
    assert body["active_workspace"]["kind"] == "personal"
    assert any(o["id"] == org["id"] for o in body.get("orgs", []))
    alice_org = _scoped(alice, org["id"])
    r = alice_org.get("/api/v1/me")
    assert r.json()["active_workspace"]["org_id"] == org["id"]


# ── Definition of Done end-to-end ─────────────────────────────────


def test_t1_definition_of_done_full_flow(isolated_db):
    """End-to-end T-1 milestone DoD:
    - Self-hosted user creates an org.
    - Invites a teammate via shared link.
    - Both ingest into the same corpus.
    - Both see contributor names on documents.
    - A third non-member is correctly rejected.
    - Audit log entries recorded for each step.
    """
    alice = _client(user_id="alice")
    org = _create_org(alice, name="Studio")
    # Invite Bob.
    r = alice.post(f"/api/v1/orgs/{org['id']}/invites", json={"role": "editor"})
    assert r.status_code == 200
    invite = r.json()
    # Bob (fresh browser identity) accepts.
    bob = _client(user_id="bob")
    r = bob.post(f"/api/v1/orgs/invites/{invite['token']}/accept")
    assert r.status_code == 200
    # Alice creates a private team corpus.
    corpus = _create_org_corpus(alice, org["id"], name="Studio Brain")
    # Both ingest.
    alice_org = _scoped(alice, org["id"])
    bob_org = _scoped(bob, org["id"])
    r1 = alice_org.post(f"/api/v1/corpora/{corpus['id']}/capture",
                        json={"content": "Alice writes a launch retro.",
                              "title": "Launch retro"})
    r2 = bob_org.post(f"/api/v1/corpora/{corpus['id']}/capture",
                      json={"content": "Bob captures customer feedback.",
                            "title": "Customer feedback"})
    assert r1.status_code == 200 and r2.status_code == 200
    # Both see contributor attribution.
    docs_alice = alice_org.get(f"/api/v1/corpora/{corpus['id']}/documents").json()
    docs_bob = bob_org.get(f"/api/v1/corpora/{corpus['id']}/documents").json()
    for docs in (docs_alice, docs_bob):
        contribs = {d.get("contributor_user_id") for d in docs}
        assert "alice" in contribs and "bob" in contribs
    # Carol — non-member — is rejected on the same corpus.
    carol = _client(user_id="carol", workspace=f"org:{org['id']}")
    r = carol.get(f"/api/v1/corpora/{corpus['id']}")
    assert r.status_code in (401, 403)
    r = carol.post(f"/api/v1/corpora/{corpus['id']}/capture",
                   json={"content": "intruder"})
    assert r.status_code in (401, 403)
    # Audit log captures the lifecycle.
    logs = alice.get(f"/api/v1/orgs/{org['id']}/audit-logs?limit=200").json()
    actions = [row["action"] for row in logs]
    for required in ("org.create", "member.invite", "invite.accept",
                     "corpus.create", "doc.ingest"):
        assert required in actions, f"missing audit action: {required}"
