"""External-agent access logging + Discovery Reach + Revenue Health.

This module captures the *anonymous* external traffic that ``query_logs``
deliberately ignores. ``query_logs`` only records hits that carry an
``x-agent-id`` header or a corpus access token (see
``noosphere.core.retrieval._log_query``) — the goal there is to keep the
authenticated-agent funnel clean. But during cold start the dominant
signal is the *un*authenticated traffic: Perplexity / ChatGPT browse /
Claude search / generic crawlers fetching ``llms.txt`` / ``sitemap.xml``
/ public corpus pages.

Discovery Reach is the compound parameter built from this data, surfaced
alongside (not inside) KB Reputation. The two are deliberately separate:

- KBR is a *Noosphere-network-internal trust* signal — KB-to-KB citations,
  repeat agent retention, calibration, satisfaction. Inputs are
  authenticated and resistant to drive-by inflation.
- Discovery Reach is *external AI surface visibility* — does the wider
  AI ecosystem actually read this corpus? Inputs are anonymous and
  high-volume. Folding it into KBR would pollute a clean trust metric
  with crawl-volume noise and create incentive to game llms.txt fetches.

Revenue Health is the third axis — subscriber count, recent revenue,
retention. Lagging artifact, not a quality signal.

All three surface to the corpus owner on the Insights dashboard and to
query-time agents via ``describe``. Each agent / consumer weights per
task; the platform exposes axes, not a single ranking number.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from noosphere.core.db import get_conn

logger = logging.getLogger(__name__)


# ── User-Agent classification ─────────────────────────────────────

# Ordered list of (substring_lower, agent_class). First match wins, so
# more specific matches must come before generic ones (e.g. ``ClaudeBot``
# before ``bot``). All comparisons are case-insensitive — the substring
# is stored lowercased and the input is lowercased before matching.
#
# Update this table as new agent identifiers emerge — Anthropic, OpenAI,
# Perplexity, and others periodically rename their crawlers, and new
# coding-agent IDEs (Cursor, Cline, Aider, Continue) ship their own.
_UA_PATTERNS: list[tuple[str, str]] = [
    # Anthropic / Claude family
    ("claude-web", "claude"),
    ("claudebot", "claude"),
    ("claude-user", "claude"),
    ("claude-code", "claude_code"),
    ("anthropic-ai", "claude"),
    ("anthropic", "claude"),

    # OpenAI / ChatGPT family
    ("gptbot", "gpt"),
    ("oai-searchbot", "gpt"),
    ("chatgpt-user", "gpt"),
    ("openai", "gpt"),

    # Perplexity
    ("perplexitybot", "perplexity"),
    ("perplexity-user", "perplexity"),
    ("perplexity", "perplexity"),

    # Coding agents / IDEs (shipping their own UAs)
    ("cursor", "cursor"),
    ("cline", "cursor"),
    ("aider", "cursor"),
    ("continue", "cursor"),
    ("windsurf", "cursor"),

    # Other AI search / aggregator
    ("you.com", "ai_search"),
    ("youbot", "ai_search"),
    ("google-extended", "ai_search"),
    ("google-cloudvertexbot", "ai_search"),
    ("bytespider", "ai_search"),
    ("amazonbot", "ai_search"),
    ("applebot-extended", "ai_search"),
    ("ccbot", "ai_search"),
    ("meta-externalagent", "ai_search"),
    ("facebookbot", "ai_search"),

    # Generic crawler / bot patterns. Order matters: place after all
    # named agents so we don't misclassify e.g. ``GPTBot`` as generic.
    ("googlebot", "search_bot"),
    ("bingbot", "search_bot"),
    ("duckduckbot", "search_bot"),
    ("yandexbot", "search_bot"),
    ("baiduspider", "search_bot"),
    ("slurp", "search_bot"),
    ("bot", "generic_bot"),
    ("crawler", "generic_bot"),
    ("spider", "generic_bot"),
    ("scraper", "generic_bot"),
    ("http", "generic_bot"),
    ("python-requests", "generic_bot"),
    ("curl", "generic_bot"),
    ("wget", "generic_bot"),

    # Browsers (humans). Last because some bots spoof Mozilla — we only
    # land here when nothing more specific matched.
    ("mozilla", "human"),
    ("safari", "human"),
    ("chrome", "human"),
    ("firefox", "human"),
    ("edg/", "human"),
    ("opera", "human"),
]


# Reach weights per agent_class. AI-surface traffic is the cold-start
# signal we actually care about; humans and search engines get partial
# credit because they still indicate the corpus is being found.
_REACH_WEIGHTS: dict[str, float] = {
    "claude": 1.0,
    "gpt": 1.0,
    "perplexity": 1.0,
    "ai_search": 1.0,
    "claude_code": 0.8,
    "cursor": 0.8,
    "search_bot": 0.4,
    "generic_bot": 0.2,
    "human": 0.3,
    "unknown": 0.2,
}


def classify_user_agent(ua: str | None) -> str:
    """Map a User-Agent string to one of the canonical agent classes.

    Returns ``"unknown"`` for empty/missing UAs. Matching is by
    substring, first-hit-wins, against the ordered ``_UA_PATTERNS`` list.
    """
    if not ua:
        return "unknown"
    s = ua.lower()
    for needle, klass in _UA_PATTERNS:
        if needle in s:
            return klass
    return "unknown"


# ── Logging ────────────────────────────────────────────────────────


def _hash_ip(ip: str | None) -> str:
    """One-way hash of the remote IP for de-duplication without retention.

    We need to count *distinct* callers per agent_class per window, but
    we never want to store raw IPs — the hash is enough for dedup and
    privacy-respecting at the same time. Truncated to 16 hex chars
    (64 bits) so the table stays compact.
    """
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


def _client_ip(request: Any) -> str:
    """Pull the most-likely client IP out of a Starlette/FastAPI Request.

    Prefers ``X-Forwarded-For`` (first hop) when behind a proxy/CDN,
    falling back to the socket peer. Best-effort — IPs are only used
    for the dedup hash, never returned to callers.
    """
    try:
        fwd = (request.headers.get("x-forwarded-for") or "").strip()
        if fwd:
            return fwd.split(",")[0].strip()
        client = getattr(request, "client", None)
        return getattr(client, "host", "") or ""
    except Exception:
        return ""


def log_access(
    request: Any,
    *,
    corpus_id: str | None,
    surface: str,
) -> None:
    """Persist an external-access row. Best-effort — never raises.

    ``surface`` should be one of the conventional surface names (see
    module docstring): ``site_llms``, ``site_sitemap``, ``site_robots``,
    ``corpus_llms``, ``corpus_llms_full``, ``corpus_describe``,
    ``corpus_preview``, ``corpus_preview_ask``, ``corpus_meta``.

    Note: this writes for *all* hits, including authenticated agents.
    The User-Agent dimension is what query_logs is missing — overlap
    with query_logs is fine; downstream queries pick the right table
    for the question being asked. KBR keeps using query_logs;
    Discovery Reach uses access_logs.
    """
    try:
        ua = (request.headers.get("user-agent") or "").strip()
        agent_class = classify_user_agent(ua)
        ip = _client_ip(request)
        path = ""
        try:
            path = str(getattr(request, "url", "")) or request.scope.get("path", "")
        except Exception:
            pass
        referer = (request.headers.get("referer") or "").strip()
        conn = get_conn()
        conn.execute(
            """INSERT INTO access_logs
               (id, corpus_id, surface, user_agent, agent_class, ip_hash, path, referer, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uuid.uuid4().hex[:12],
                corpus_id,
                surface,
                ua[:512],
                agent_class,
                _hash_ip(ip),
                path[:512],
                referer[:512],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    except Exception:
        logger.warning("Failed to log access for corpus %s surface %s", corpus_id, surface, exc_info=True)


# ── Discovery Reach ────────────────────────────────────────────────


def _window_cutoff(window: str) -> str:
    """Map a window string to an ISO8601 cutoff. Same convention as the
    insights endpoint — ``7d`` (default), ``30d``, ``all``.
    """
    now = datetime.now(timezone.utc)
    if window == "30d":
        return (now - timedelta(days=30)).isoformat()
    if window == "all":
        return "1970-01-01T00:00:00+00:00"
    return (now - timedelta(days=7)).isoformat()


def _by_class(corpus_id: str, since: str) -> dict[str, dict[str, int]]:
    """Aggregate access_logs by agent_class within a window.

    Returns ``{class: {hits, distinct_ips}}``. Empty dict for corpora
    with no rows yet.
    """
    conn = get_conn()
    rows = conn.execute(
        """SELECT agent_class,
                  COUNT(*) AS hits,
                  COUNT(DISTINCT ip_hash) AS distinct_ips
           FROM access_logs
           WHERE corpus_id=? AND created_at >= ?
           GROUP BY agent_class""",
        (corpus_id, since),
    ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        out[r["agent_class"]] = {
            "hits": int(r["hits"] or 0),
            "distinct_ips": int(r["distinct_ips"] or 0),
        }
    return out


def discovery_reach(corpus_id: str, *, window: str = "7d") -> dict:
    """Compound parameter: how visible is this corpus to the AI ecosystem?

    Returned shape::

        {
            "window": "7d",
            "score": 12.4,                # weighted reach number (0+, soft-capped)
            "by_class": {
                "claude": {"hits": 8, "distinct_ips": 3, "weight": 1.0},
                "perplexity": {"hits": 14, "distinct_ips": 5, "weight": 1.0},
                ...
            },
            "ai_surfaces_total": 22,      # sum of distinct_ips for AI classes
            "human_total": 4,             # distinct human IPs
            "bot_total": 2,               # distinct generic_bot IPs
        }

    The score uses log-saturated distinct_ips per class: ``weight × ln(1 + distinct_ips)``.
    Saturation prevents one frequent-fetcher class from dominating; weights
    give AI classes priority over generic crawlers.
    """
    import math

    since = _window_cutoff(window)
    raw = _by_class(corpus_id, since)

    score = 0.0
    by_class: dict[str, dict[str, Any]] = {}
    ai_total = 0
    human_total = 0
    bot_total = 0
    for klass, vals in raw.items():
        weight = _REACH_WEIGHTS.get(klass, _REACH_WEIGHTS["unknown"])
        distinct = vals["distinct_ips"]
        contribution = weight * math.log1p(distinct)
        score += contribution
        by_class[klass] = {
            "hits": vals["hits"],
            "distinct_ips": distinct,
            "weight": weight,
        }
        if klass in ("claude", "gpt", "perplexity", "ai_search", "claude_code", "cursor"):
            ai_total += distinct
        elif klass == "human":
            human_total += distinct
        elif klass in ("search_bot", "generic_bot", "unknown"):
            bot_total += distinct

    return {
        "window": window if window in ("7d", "30d", "all") else "7d",
        "score": round(score, 3),
        "by_class": by_class,
        "ai_surfaces_total": ai_total,
        "human_total": human_total,
        "bot_total": bot_total,
    }


def discovery_reach_summary(corpus_id: str) -> dict:
    """Compact form for ``describe`` — 7d + 30d windows side by side.

    ``describe`` is the agent-facing capability card; we want a small
    payload that lets a consumer judge "is anyone reading this" without
    pulling the full per-class breakdown.
    """
    seven = discovery_reach(corpus_id, window="7d")
    thirty = discovery_reach(corpus_id, window="30d")
    return {
        "7d": {
            "score": seven["score"],
            "ai_surfaces": seven["ai_surfaces_total"],
        },
        "30d": {
            "score": thirty["score"],
            "ai_surfaces": thirty["ai_surfaces_total"],
        },
    }


# ── Revenue Health ─────────────────────────────────────────────────


def _per_month_cents(corpus: dict | None) -> int:
    """Look up the monthly subscription price from corpus.pricing_json."""
    if not corpus:
        return 0
    raw = corpus.get("pricing_json")
    if not raw:
        return 0
    try:
        import json
        pricing = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return 0
    if pricing.get("type") not in ("subscription", "monthly"):
        return 0
    try:
        return int(pricing.get("amount_cents") or 0)
    except (TypeError, ValueError):
        return 0


def revenue_health(corpus_id: str, *, window: str = "30d") -> dict:
    """Lightweight commercial health snapshot for a corpus.

    Returned shape::

        {
            "subscriber_count": 4,
            "mrr_cents": 8000,
            "window_revenue_cents": 12500,   # payments + agent_settlements
            "retention_rate": 0.85,          # active / (active + cancelled_in_window)
            "active_paid": True,             # corpus has a paid access_level configured
        }

    Kept deliberately separate from Discovery Reach and KBR. Revenue is
    a lagging artifact, not a quality signal — a brand-new paid corpus
    has $0 MRR but may have high reach, and folding revenue into
    quality scoring would punish new entrants.
    """
    conn = get_conn()
    since = _window_cutoff(window)

    # Corpus row for pricing + access_level
    try:
        corp = conn.execute(
            "SELECT access_level, pricing_json FROM corpora WHERE id=?",
            (corpus_id,),
        ).fetchone()
    except Exception:
        corp = None
    corp_dict = dict(corp) if corp else None

    # Active subscribers
    sub_row = conn.execute(
        "SELECT COUNT(*) AS n FROM subscriptions WHERE corpus_id=? AND status='active'",
        (corpus_id,),
    ).fetchone()
    subscriber_count = int(sub_row["n"] or 0) if sub_row else 0

    # Revenue inside the window — payments + settlements.
    pay_row = conn.execute(
        """SELECT COALESCE(SUM(amount_cents), 0) AS cents
           FROM payments
           WHERE corpus_id=? AND status='completed' AND created_at >= ?""",
        (corpus_id, since),
    ).fetchone()
    payments_cents = int(pay_row["cents"] or 0) if pay_row else 0

    settle_cents = 0
    try:
        settle_row = conn.execute(
            """SELECT COALESCE(SUM(amount_cents), 0) AS cents
               FROM agent_settlements
               WHERE corpus_id=? AND created_at >= ?""",
            (corpus_id, since),
        ).fetchone()
        settle_cents = int(settle_row["cents"] or 0) if settle_row else 0
    except Exception:
        pass

    # Retention: active / (active + cancelled in window). Only meaningful
    # when there's at least one cancellation to compare against.
    cancelled_row = conn.execute(
        """SELECT COUNT(*) AS n FROM subscriptions
           WHERE corpus_id=? AND status='cancelled' AND cancelled_at >= ?""",
        (corpus_id, since),
    ).fetchone()
    cancelled_in_window = int(cancelled_row["n"] or 0) if cancelled_row else 0
    if subscriber_count + cancelled_in_window > 0:
        retention_rate: float | None = round(
            subscriber_count / (subscriber_count + cancelled_in_window), 3
        )
    else:
        retention_rate = None

    return {
        "subscriber_count": subscriber_count,
        "mrr_cents": subscriber_count * _per_month_cents(corp_dict),
        "window_revenue_cents": payments_cents + settle_cents,
        "window": window if window in ("7d", "30d", "all") else "30d",
        "retention_rate": retention_rate,
        "active_paid": bool(corp_dict and (corp_dict.get("access_level") in ("paid", "subscription"))),
    }
