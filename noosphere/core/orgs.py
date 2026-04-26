"""Team workspaces — organizations, members, invites, audit log, permissions.

A corpus belongs to exactly one scope: ``owner_id`` (personal) XOR ``org_id``
(team). For org-scoped corpora, access is gated by membership in the org and
role tier (owner > admin > editor > viewer).

Self-hosted simplification: a single org per instance, identified per request
via the ``X-Noosphere-User-Id`` header (browser-issued, persisted in
localStorage). The localhost operator gets the sentinel id ``"local"`` and
remains the implicit owner of any org they create.
"""

import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from noosphere.core.db import get_conn

# ── Roles ──────────────────────────────────────────────────────────

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"

ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER)

# Order matters — index = privilege level.
_ROLE_RANK = {ROLE_VIEWER: 0, ROLE_EDITOR: 1, ROLE_ADMIN: 2, ROLE_OWNER: 3}


def role_at_least(actual: Optional[str], required: str) -> bool:
    if not actual or actual not in _ROLE_RANK:
        return False
    return _ROLE_RANK[actual] >= _ROLE_RANK[required]


# ── Util ───────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    s = (text or "").lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    d = dict(row)
    if "settings_json" in d and isinstance(d["settings_json"], str):
        try:
            d["settings"] = json.loads(d["settings_json"]) if d["settings_json"] else {}
        except (json.JSONDecodeError, TypeError):
            d["settings"] = {}
    return d


# ── Organizations ──────────────────────────────────────────────────


class OrgError(Exception):
    """Domain error for org operations (slug taken, role conflict, etc.)."""


def create_org(
    name: str,
    *,
    owner_user_id: str,
    slug: str = "",
    tier: str = "team",
    settings: Optional[dict] = None,
) -> dict:
    if not owner_user_id:
        raise OrgError("create_org requires owner_user_id")
    conn = get_conn()
    org_id = uuid.uuid4().hex[:12]
    base_slug = _slugify(slug or name) or org_id
    final_slug = base_slug
    existing = conn.execute(
        "SELECT id FROM organizations WHERE slug=?", (final_slug,)
    ).fetchone()
    if existing:
        final_slug = f"{base_slug}-{org_id[:6]}"
    now = _now()
    conn.execute(
        """INSERT INTO organizations (id, slug, name, tier, settings_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?)""",
        (org_id, final_slug, name, tier, json.dumps(settings or {}), now, now),
    )
    conn.execute(
        """INSERT INTO organization_members (org_id, user_id, role, invited_by, joined_at)
           VALUES (?,?,?,?,?)""",
        (org_id, owner_user_id, ROLE_OWNER, owner_user_id, now),
    )
    conn.commit()
    return get_org(org_id)


def get_org(org_id: str) -> Optional[dict]:
    row = get_conn().execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()
    return _row_to_dict(row)


def get_org_by_slug(slug: str) -> Optional[dict]:
    row = get_conn().execute("SELECT * FROM organizations WHERE slug=?", (slug,)).fetchone()
    return _row_to_dict(row)


def update_org(org_id: str, **fields) -> Optional[dict]:
    allowed = {"name", "slug", "tier", "billing_customer_id",
               "stripe_connect_account_id", "settings_json"}
    if "settings" in fields and "settings_json" not in fields:
        fields["settings_json"] = json.dumps(fields.pop("settings") or {})
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_org(org_id)
    if "slug" in updates:
        updates["slug"] = _slugify(updates["slug"])
        clash = get_conn().execute(
            "SELECT id FROM organizations WHERE slug=? AND id<>?",
            (updates["slug"], org_id),
        ).fetchone()
        if clash:
            raise OrgError(f"slug already taken: {updates['slug']}")
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [org_id]
    get_conn().execute(f"UPDATE organizations SET {set_clause} WHERE id=?", values)
    get_conn().commit()
    return get_org(org_id)


def delete_org(org_id: str) -> bool:
    """Hard-delete an org. Org-scoped corpora are NOT touched (caller decides)."""
    conn = get_conn()
    conn.execute("DELETE FROM organization_invites WHERE org_id=?", (org_id,))
    conn.execute("DELETE FROM organization_members WHERE org_id=?", (org_id,))
    cur = conn.execute("DELETE FROM organizations WHERE id=?", (org_id,))
    conn.commit()
    return cur.rowcount > 0


def list_orgs_for_user(user_id: str) -> list[dict]:
    if not user_id:
        return []
    rows = get_conn().execute(
        """SELECT o.*, m.role
           FROM organizations o
           JOIN organization_members m ON m.org_id = o.id
           WHERE m.user_id = ?
           ORDER BY o.created_at ASC""",
        (user_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def first_org() -> Optional[dict]:
    """Self-hosted single-org helper."""
    row = get_conn().execute(
        "SELECT * FROM organizations ORDER BY created_at ASC LIMIT 1"
    ).fetchone()
    return _row_to_dict(row)


# ── Members ────────────────────────────────────────────────────────


def add_member(
    org_id: str,
    user_id: str,
    role: str = ROLE_EDITOR,
    invited_by: str = "",
    display_name: str = "",
) -> dict:
    if role not in ROLES:
        raise OrgError(f"invalid role: {role}")
    conn = get_conn()
    existing = get_member(org_id, user_id)
    if existing:
        return existing
    now = _now()
    conn.execute(
        """INSERT INTO organization_members
           (org_id, user_id, role, invited_by, display_name, joined_at)
           VALUES (?,?,?,?,?,?)""",
        (org_id, user_id, role, invited_by or None, (display_name or None), now),
    )
    conn.commit()
    return get_member(org_id, user_id)


def update_display_name(org_id: str, user_id: str, display_name: str) -> Optional[dict]:
    """Set/clear the member's display name. Empty string clears it."""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE organization_members SET display_name=? WHERE org_id=? AND user_id=?",
        ((display_name or None), org_id, user_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_member(org_id, user_id)


def get_member(org_id: str, user_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM organization_members WHERE org_id=? AND user_id=?",
        (org_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def list_members(org_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM organization_members WHERE org_id=? ORDER BY joined_at ASC",
        (org_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_role(org_id: str, user_id: str, role: str) -> Optional[dict]:
    if role not in ROLES:
        raise OrgError(f"invalid role: {role}")
    member = get_member(org_id, user_id)
    if not member:
        return None
    # Don't let the last owner be demoted.
    if member["role"] == ROLE_OWNER and role != ROLE_OWNER:
        owners = [m for m in list_members(org_id) if m["role"] == ROLE_OWNER]
        if len(owners) <= 1:
            raise OrgError("cannot demote the last owner")
    conn = get_conn()
    conn.execute(
        "UPDATE organization_members SET role=? WHERE org_id=? AND user_id=?",
        (role, org_id, user_id),
    )
    conn.commit()
    return get_member(org_id, user_id)


def remove_member(org_id: str, user_id: str) -> bool:
    member = get_member(org_id, user_id)
    if not member:
        return False
    if member["role"] == ROLE_OWNER:
        owners = [m for m in list_members(org_id) if m["role"] == ROLE_OWNER]
        if len(owners) <= 1:
            raise OrgError("cannot remove the last owner")
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM organization_members WHERE org_id=? AND user_id=?",
        (org_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def member_role(org_id: str, user_id: str) -> Optional[str]:
    m = get_member(org_id, user_id)
    return m["role"] if m else None


# ── Invites (shared link tokens) ───────────────────────────────────


def create_invite(
    org_id: str,
    *,
    role: str = ROLE_EDITOR,
    created_by: str = "",
    ttl_days: int = 14,
) -> dict:
    if role not in ROLES:
        raise OrgError(f"invalid role: {role}")
    if role == ROLE_OWNER:
        raise OrgError("cannot invite as owner; promote after join")
    conn = get_conn()
    invite_id = uuid.uuid4().hex[:12]
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=ttl_days)).isoformat()
    conn.execute(
        """INSERT INTO organization_invites
           (id, org_id, token, role, created_by, expires_at, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (invite_id, org_id, token, role, created_by or None, expires, now.isoformat()),
    )
    conn.commit()
    return get_invite(invite_id)


def get_invite(invite_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM organization_invites WHERE id=?", (invite_id,)
    ).fetchone()
    return dict(row) if row else None


def get_invite_by_token(token: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM organization_invites WHERE token=?", (token,)
    ).fetchone()
    return dict(row) if row else None


def list_invites(org_id: str, *, include_used: bool = False) -> list[dict]:
    if include_used:
        rows = get_conn().execute(
            "SELECT * FROM organization_invites WHERE org_id=? ORDER BY created_at DESC",
            (org_id,),
        ).fetchall()
    else:
        rows = get_conn().execute(
            """SELECT * FROM organization_invites
               WHERE org_id=? AND accepted_at IS NULL AND revoked_at IS NULL
               ORDER BY created_at DESC""",
            (org_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def revoke_invite(invite_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE organization_invites SET revoked_at=? WHERE id=? AND accepted_at IS NULL",
        (_now(), invite_id),
    )
    conn.commit()
    return cur.rowcount > 0


def accept_invite(
    token: str, accepting_user_id: str, display_name: str = ""
) -> dict:
    """Consume a single-use invite token, adding the accepting user as a member.

    Returns the new (or existing) member row.
    Raises OrgError on invalid / expired / already-used / revoked tokens.
    """
    if not accepting_user_id:
        raise OrgError("accept_invite requires accepting_user_id")
    invite = get_invite_by_token(token)
    if not invite:
        raise OrgError("invite token not found")
    if invite["accepted_at"]:
        raise OrgError("invite already used")
    if invite.get("revoked_at"):
        raise OrgError("invite revoked")
    expires_at = invite.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                raise OrgError("invite expired")
        except (TypeError, ValueError):
            pass

    conn = get_conn()
    member = add_member(
        invite["org_id"],
        accepting_user_id,
        role=invite["role"],
        invited_by=invite.get("created_by") or "",
        display_name=display_name,
    )
    conn.execute(
        "UPDATE organization_invites SET accepted_at=?, accepted_by=? WHERE id=?",
        (_now(), accepting_user_id, invite["id"]),
    )
    conn.commit()
    return member


# ── Audit log ──────────────────────────────────────────────────────


def log_audit(
    action: str,
    *,
    org_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    ip_addr: Optional[str] = None,
) -> str:
    """Insert an audit-log row. Best-effort: never raises.

    Returns the new log id, or empty string on failure (so callers stay
    write-path simple — audit failure must not break user-visible action).
    """
    try:
        conn = get_conn()
        log_id = uuid.uuid4().hex[:16]
        conn.execute(
            """INSERT INTO audit_logs
               (id, org_id, actor_user_id, action, resource_type, resource_id,
                metadata_json, ip_addr, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                log_id, org_id, actor_user_id, action, resource_type, resource_id,
                json.dumps(metadata or {}), ip_addr, _now(),
            ),
        )
        conn.commit()
        return log_id
    except Exception:  # noqa: BLE001 — best-effort
        return ""


def list_audit_logs(
    org_id: str,
    *,
    limit: int = 100,
    before: Optional[str] = None,
) -> list[dict]:
    if before:
        rows = get_conn().execute(
            """SELECT * FROM audit_logs
               WHERE org_id=? AND created_at < ?
               ORDER BY created_at DESC LIMIT ?""",
            (org_id, before, limit),
        ).fetchall()
    else:
        rows = get_conn().execute(
            """SELECT * FROM audit_logs
               WHERE org_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (org_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        meta = d.get("metadata_json")
        if isinstance(meta, str) and meta:
            try:
                d["metadata"] = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                d["metadata"] = {}
        out.append(d)
    return out


# ── Permissions ────────────────────────────────────────────────────


def corpus_role_for_user(corpus: dict, user_id: Optional[str]) -> Optional[str]:
    """Return the user's effective role on a corpus, or None if no access.

    Personal corpus (owner_id set): owner if user matches owner_id, else None.
    Team corpus (org_id set): the user's org role, or None if not a member.
    """
    if not corpus:
        return None
    org_id = corpus.get("org_id")
    if org_id:
        if not user_id:
            return None
        return member_role(org_id, user_id)
    owner_id = corpus.get("owner_id")
    if owner_id and user_id and owner_id == user_id:
        return ROLE_OWNER
    return None


def can_read_corpus(corpus: dict, user_id: Optional[str]) -> bool:
    role = corpus_role_for_user(corpus, user_id)
    return role_at_least(role, ROLE_VIEWER)


def can_write_corpus(corpus: dict, user_id: Optional[str]) -> bool:
    role = corpus_role_for_user(corpus, user_id)
    return role_at_least(role, ROLE_EDITOR)


def can_admin_corpus(corpus: dict, user_id: Optional[str]) -> bool:
    role = corpus_role_for_user(corpus, user_id)
    return role_at_least(role, ROLE_ADMIN)


def can_admin_org(org_id: str, user_id: Optional[str]) -> bool:
    return role_at_least(member_role(org_id, user_id) if user_id else None, ROLE_ADMIN)


def can_own_org(org_id: str, user_id: Optional[str]) -> bool:
    return role_at_least(member_role(org_id, user_id) if user_id else None, ROLE_OWNER)


__all__ = [
    "ROLE_OWNER", "ROLE_ADMIN", "ROLE_EDITOR", "ROLE_VIEWER", "ROLES",
    "OrgError", "role_at_least",
    "create_org", "get_org", "get_org_by_slug", "update_org", "delete_org",
    "list_orgs_for_user", "first_org",
    "add_member", "get_member", "list_members", "update_role",
    "remove_member", "member_role", "update_display_name",
    "create_invite", "get_invite", "get_invite_by_token", "list_invites",
    "revoke_invite", "accept_invite",
    "log_audit", "list_audit_logs",
    "corpus_role_for_user", "can_read_corpus", "can_write_corpus",
    "can_admin_corpus", "can_admin_org", "can_own_org",
]
