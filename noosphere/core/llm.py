"""Shared LLM calling utilities — Gemini and OpenAI providers.

Providers are tried in order (Gemini → OpenAI). If the first fails with a
hard error (geo-block, quota, bad key, 5xx), the next configured provider
is attempted. The final error surfaces the real underlying message(s) so
the user can tell a geo-block from a quota from a missing key.
"""

import logging

import httpx

from noosphere.core.config import (
    OPENAI_API_KEY, GEMINI_API_KEY, GEMINI_API_KEYS,
    GEMINI_BASE_URL, GEMINI_CHAT_MODEL, OPENAI_CHAT_MODEL,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL,
    KIMI_API_KEY, KIMI_BASE_URL, KIMI_CHAT_MODEL,
    ZHIPU_API_KEY, ZHIPU_BASE_URL, ZHIPU_CHAT_MODEL,
)

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when every configured provider fails. Message contains per-provider causes."""


def call_llm(messages: list[dict]) -> str:
    errors: list[str] = []

    def _try(name: str, fn):
        try:
            return fn()
        except Exception as e:
            errors.append(f"{name}: {_extract_err(e)}")
            logger.warning("%s failed, falling back: %s", name, errors[-1])
            return None

    # Chain order: Gemini primary; on failure jump straight to DeepSeek
    # (stable + cheap + China-friendly). OpenAI stays third — it tends to
    # 429 on exhausted quotas and trying it before DeepSeek would just add
    # latency for geo-blocked Gemini users. Kimi and Zhipu are last-resort.
    if GEMINI_API_KEY:
        r = _try("Gemini", lambda: _call_gemini(messages))
        if r is not None:
            return r
    if DEEPSEEK_API_KEY:
        r = _try("DeepSeek", lambda: _call_openai_compat(DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL, DEEPSEEK_API_KEY, messages))
        if r is not None:
            return r
    if OPENAI_API_KEY:
        r = _try("OpenAI", lambda: _call_openai(messages))
        if r is not None:
            return r
    if KIMI_API_KEY:
        r = _try("Kimi", lambda: _call_openai_compat(KIMI_BASE_URL, KIMI_CHAT_MODEL, KIMI_API_KEY, messages))
        if r is not None:
            return r
    if ZHIPU_API_KEY:
        r = _try("Zhipu", lambda: _call_openai_compat(ZHIPU_BASE_URL, ZHIPU_CHAT_MODEL, ZHIPU_API_KEY, messages))
        if r is not None:
            return r

    if not errors:
        raise LLMError("No LLM provider configured. Set one of GEMINI_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, KIMI_API_KEY, or ZHIPU_API_KEY in .env")
    raise LLMError(" / ".join(errors))


def _extract_err(e: Exception) -> str:
    """Pull the useful bit out of an httpx error (status + provider error message)."""
    if isinstance(e, httpx.HTTPStatusError):
        try:
            body = e.response.json()
            msg = body.get("error", {}).get("message") or body.get("error") or e.response.text[:200]
        except Exception:
            msg = e.response.text[:200]
        return f"{e.response.status_code} {msg}"
    return str(e)[:200]


def _call_gemini(messages: list[dict]) -> str:
    """Gemini chat with multi-key rotation.

    Iterates through GEMINI_API_KEYS in order. When a key returns 4xx/5xx
    (quota, geo-block, bad key), the next key is tried. Only the last-seen
    error is raised so the outer provider-fallback chain sees one Gemini
    failure rather than N.
    """
    contents = []
    system_text = ""
    for m in messages:
        if m["role"] == "system":
            system_text = m["content"]
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

    body = {"contents": contents}
    if system_text:
        body["systemInstruction"] = {"parts": [{"text": system_text}]}

    keys = GEMINI_API_KEYS or [GEMINI_API_KEY]
    last_err: Exception | None = None
    base = GEMINI_BASE_URL.rstrip("/")
    for i, key in enumerate(keys):
        url = f"{base}/models/{GEMINI_CHAT_MODEL}:generateContent?key={key}"
        try:
            resp = httpx.post(url, json=body, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return "Failed to generate response."
        except Exception as e:
            last_err = e
            if i < len(keys) - 1:
                logger.info("Gemini key #%d exhausted/unavailable, rotating: %s", i + 1, _extract_err(e))
    assert last_err is not None
    raise last_err


def _call_openai(messages: list[dict]) -> str:
    return _call_openai_compat(
        "https://api.openai.com/v1", OPENAI_CHAT_MODEL, OPENAI_API_KEY, messages
    )


def _call_openai_compat(base_url: str, model: str, api_key: str, messages: list[dict]) -> str:
    """OpenAI-compatible chat completions (OpenAI, DeepSeek, Kimi/Moonshot, etc.)."""
    url = base_url.rstrip("/") + "/chat/completions"
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "max_tokens": 1024},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
