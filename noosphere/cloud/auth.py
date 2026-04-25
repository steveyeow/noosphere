"""Supabase JWT authentication middleware for Noosphere Cloud.

Validates Bearer tokens from Supabase Auth. Supports both HS256 (legacy)
and ES256 (JWKS) algorithms. On success, sets request.state.user_id,
request.state.email, and request.state.tier.

Unauthenticated requests are allowed for public/read paths. Write operations
and user-specific data require authentication.
"""

from __future__ import annotations

import os
import logging
import time

import jwt
import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

from noosphere.cloud.db import get_or_create_user

log = logging.getLogger(__name__)

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()

_JWKS_CACHE: list | None = None
_JWKS_CACHE_TIME: float = 0
_JWKS_TTL = 600

# Paths that never require authentication
PUBLIC_PATHS = {
    "/",
    "/api/v1/health",
    "/api/v1/search",
    "/.well-known/noosphere.json",
    "/api/v1/stripe/webhook",
    "/api/v1/cloud/webhook",
    "/favicon.ico",
    # Node-to-node registration is anonymous by design — any self-hosted
    # node can publish its metadata and retract it. Spam is deterred at
    # a different layer: fake endpoints fail real queries (reputation
    # stays at zero), and the registry's reconcile step drops nodes that
    # stop heartbeating.
    "/api/v1/register",
    "/api/v1/deregister",
}
PUBLIC_PREFIXES = (
    "/static/",
    "/mcp",
)

# GET requests to these paths require authentication (user-specific data)
PRIVATE_GET_PREFIXES = (
    "/api/v1/cloud/subscription",
    "/api/v1/cloud/usage",
)


def _get_jwks_keys() -> list:
    """Fetch and cache JWKS keys from Supabase."""
    global _JWKS_CACHE, _JWKS_CACHE_TIME
    now = time.monotonic()
    if _JWKS_CACHE is not None and (now - _JWKS_CACHE_TIME) < _JWKS_TTL:
        return _JWKS_CACHE
    if not SUPABASE_URL:
        return _JWKS_CACHE or []
    jwks_url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
    try:
        resp = httpx.get(jwks_url, timeout=5)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
        _JWKS_CACHE = [jwt.PyJWK(k) for k in keys]
        _JWKS_CACHE_TIME = now
        log.info("Fetched %d JWKS keys from %s", len(_JWKS_CACHE), jwks_url)
    except Exception as e:
        log.warning("JWKS fetch failed: %s", e)
    return _JWKS_CACHE or []


def _verify_token_via_supabase(token: str) -> dict:
    """Fallback: verify token by calling Supabase's /auth/v1/user endpoint."""
    if not SUPABASE_URL:
        raise jwt.InvalidTokenError("SUPABASE_URL not configured for fallback")
    url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/user"
    anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    headers = {"Authorization": f"Bearer {token}", "apikey": anon_key}
    try:
        resp = httpx.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "sub": data.get("id", ""),
                "email": data.get("email", ""),
                "aud": "authenticated",
            }
        raise jwt.InvalidTokenError(f"Supabase returned {resp.status_code}")
    except httpx.HTTPError as e:
        raise jwt.InvalidTokenError(f"Supabase verification failed: {e}")


def _decode_token(token: str) -> dict:
    """Decode a Supabase JWT. Supports HS256 (legacy) and ES256 (JWKS).

    Falls back to Supabase /auth/v1/user API when local validation fails.
    """
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")

    # Try local validation first
    try:
        if alg == "HS256" and SUPABASE_JWT_SECRET:
            return jwt.decode(
                token, SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )

        if alg == "ES256":
            kid = header.get("kid", "")
            for jwk in _get_jwks_keys():
                if jwk.key_id == kid:
                    return jwt.decode(
                        token, jwk.key,
                        algorithms=["ES256"],
                        audience="authenticated",
                    )
    except Exception as e:
        log.warning("Local JWT validation failed (%s), trying Supabase API: %s", alg, e)

    # Fallback: verify via Supabase API directly
    return _verify_token_via_supabase(token)


async def auth_middleware(request: Request, call_next):
    """Authenticate requests via Supabase JWT.

    Public paths and GET requests to non-private API endpoints pass through
    without authentication. Write operations require a valid token.
    """
    path = request.url.path
    is_public = path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES)
    is_get_api = request.method == "GET" and path.startswith("/api/")

    # Public paths always pass through
    if is_public:
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    has_token = auth_header.startswith("Bearer ")

    is_private_get = is_get_api and any(
        path.startswith(p) for p in PRIVATE_GET_PREFIXES
    )

    # No token
    if not has_token:
        # Allow public GET API requests (corpus listing, search, etc.)
        if is_get_api and not is_private_get:
            return await call_next(request)
        return JSONResponse(
            {"detail": "Authentication required", "code": "auth_required"},
            status_code=401,
        )

    # Validate token
    token = auth_header[7:]
    try:
        payload = _decode_token(token)
    except jwt.ExpiredSignatureError:
        if is_get_api and not is_private_get:
            return await call_next(request)
        return JSONResponse(
            {"detail": "Token expired", "code": "token_expired"},
            status_code=401,
        )
    except jwt.InvalidTokenError as e:
        log.warning("JWT validation failed: %s", e)
        if is_get_api and not is_private_get:
            return await call_next(request)
        return JSONResponse(
            {"detail": "Invalid token", "code": "invalid_token"},
            status_code=401,
        )

    user_id = payload.get("sub", "")
    email = payload.get("email", "")

    if not user_id:
        if is_get_api and not is_private_get:
            return await call_next(request)
        return JSONResponse({"detail": "Invalid token claims"}, status_code=401)

    # Get or create user record
    try:
        user = get_or_create_user(user_id, email)
    except Exception as e:
        log.error("get_or_create_user failed for %s: %s", user_id, e)
        user = None

    # Set user context on request
    request.state.user_id = user_id
    request.state.email = email
    request.state.tier = user.get("tier", "free") if user else "free"

    return await call_next(request)
