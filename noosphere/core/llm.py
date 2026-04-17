"""Shared LLM calling utilities — Gemini and OpenAI providers."""

import httpx

from noosphere.core.config import (
    OPENAI_API_KEY, GEMINI_API_KEY,
    GEMINI_CHAT_MODEL, OPENAI_CHAT_MODEL,
)


def call_llm(messages: list[dict]) -> str:
    """Call the best available LLM provider."""
    if GEMINI_API_KEY:
        return _call_gemini(messages)
    if OPENAI_API_KEY:
        return _call_openai(messages)
    return "No LLM provider configured. Set GEMINI_API_KEY or OPENAI_API_KEY in .env"


def _call_gemini(messages: list[dict]) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_CHAT_MODEL}:generateContent?key={GEMINI_API_KEY}"

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

    resp = httpx.post(url, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return "Failed to generate response."


def _call_openai(messages: list[dict]) -> str:
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json={"model": OPENAI_CHAT_MODEL, "messages": messages, "max_tokens": 1024},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
