"""Pluggable embedding providers — OpenAI and Gemini."""

import logging
import time
from abc import ABC, abstractmethod

import httpx
import numpy as np

from noosphere.core.config import (
    OPENAI_API_KEY, GEMINI_API_KEY, GEMINI_API_KEYS,
    GEMINI_BASE_URL, GEMINI_EMBED_MODEL,
    ZHIPU_API_KEY, ZHIPU_BASE_URL, ZHIPU_EMBED_MODEL, ZHIPU_EMBED_DIM,
    EMBEDDING_PROVIDER,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = (1, 3, 10)  # seconds


RATE_LIMIT_BACKOFF = (15, 30, 60, 60, 60)  # seconds; must outlast a per-minute quota window


def _request_with_retry(method, url, **kwargs):
    """HTTP request with exponential backoff retry on transient failures."""
    attempt = 0        # transient failures (timeout / connect / 5xx)
    rate_limited = 0   # 429s get their own, more patient budget
    while True:
        try:
            resp = method(url, **kwargs)
            resp.raise_for_status()
            return resp
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            is_429 = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
            # 429 is the one retryable 4xx: rate limits are transient by
            # definition and Gemini free-tier quotas hit them routinely
            # mid-index. Other 4xx (bad key, bad payload) stay fatal.
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500 and not is_429:
                raise
            if is_429:
                # Separate budget from transient errors: a quota window needs
                # to be waited out, not raced. Honor Retry-After when sent.
                if rate_limited >= len(RATE_LIMIT_BACKOFF):
                    raise
                wait = RATE_LIMIT_BACKOFF[rate_limited]
                retry_after = e.response.headers.get("retry-after", "")
                if retry_after.isdigit():
                    wait = max(wait, min(int(retry_after), 120))
                rate_limited += 1
                logger.warning("Embedding API rate-limited (429), waiting %ds (retry %d/%d)",
                               wait, rate_limited, len(RATE_LIMIT_BACKOFF))
                time.sleep(wait)
                continue
            if attempt >= MAX_RETRIES - 1:
                raise
            wait = RETRY_BACKOFF[attempt]
            attempt += 1
            logger.warning("Embedding API attempt %d failed (%s), retrying in %ds", attempt, e, wait)
            time.sleep(wait)


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return (N, dim) float32 array of embeddings."""
        ...

    @abstractmethod
    def dim(self) -> int:
        ...

    @abstractmethod
    def model_name(self) -> str:
        ...


class OpenAIEmbedder(EmbeddingProvider):
    def __init__(self, api_key: str = "", model: str = "text-embedding-3-small"):
        self._key = api_key or OPENAI_API_KEY
        self._model = model
        if not self._key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")

    def embed(self, texts: list[str]) -> np.ndarray:
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        all_embeddings = []

        for i in range(0, len(texts), 100):
            batch = texts[i : i + 100]
            resp = _request_with_retry(
                httpx.post,
                "https://api.openai.com/v1/embeddings",
                headers=headers,
                json={"model": self._model, "input": batch},
                timeout=60,
            )
            data = resp.json()["data"]
            data.sort(key=lambda x: x["index"])
            all_embeddings.extend([d["embedding"] for d in data])

        return np.array(all_embeddings, dtype=np.float32)

    def dim(self) -> int:
        return 1536

    def model_name(self) -> str:
        return self._model


class ZhipuEmbedder(EmbeddingProvider):
    """Zhipu AI embedding-3 via their OpenAI-compatible /v4/embeddings endpoint.

    Supports flexible output dims via the `dimensions` param (256/512/1024/2048).
    Chinese-aware; works in-country without geo-blocking.
    """

    def __init__(self, api_key: str = "", model: str = "", base_url: str = "", dim: int = 0):
        self._key = api_key or ZHIPU_API_KEY
        self._model = model or ZHIPU_EMBED_MODEL
        self._base = (base_url or ZHIPU_BASE_URL).rstrip("/")
        self._dim = dim or ZHIPU_EMBED_DIM
        if not self._key:
            raise ValueError("ZHIPU_API_KEY is required for Zhipu embeddings")

    def embed(self, texts: list[str]) -> np.ndarray:
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        all_embeddings = []
        url = f"{self._base}/embeddings"

        # Zhipu accepts a batch of up to 64 inputs per call.
        for i in range(0, len(texts), 64):
            batch = texts[i : i + 64]
            body = {"model": self._model, "input": batch, "dimensions": self._dim}
            resp = _request_with_retry(httpx.post, url, headers=headers, json=body, timeout=60)
            data = resp.json()["data"]
            data.sort(key=lambda x: x["index"])
            all_embeddings.extend([d["embedding"] for d in data])

        return np.array(all_embeddings, dtype=np.float32)

    def dim(self) -> int:
        return self._dim

    def model_name(self) -> str:
        return self._model


class GeminiEmbedder(EmbeddingProvider):
    """Gemini embeddings with multi-key rotation.

    Supports comma-separated GEMINI_API_KEY. When one key hits its quota or
    geo-block, the next key is attempted for the same batch. Keys from the
    SAME Google Cloud project share quota; use keys from different accounts
    for real capacity stacking.
    """

    MODEL_DIMS = {"gemini-embedding-001": 3072, "text-embedding-004": 768}

    def __init__(self, api_key: str = "", model: str = "", api_keys: list[str] | None = None, base_url: str = ""):
        if api_keys:
            self._keys = [k for k in api_keys if k]
        elif api_key:
            self._keys = [api_key]
        else:
            self._keys = list(GEMINI_API_KEYS) if GEMINI_API_KEYS else ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
        self._model = model or GEMINI_EMBED_MODEL
        self._base = (base_url or GEMINI_BASE_URL).rstrip("/")
        if not self._keys:
            raise ValueError("GEMINI_API_KEY is required for Gemini embeddings")

    def _post_with_key_rotation(self, requests_body: list[dict]) -> httpx.Response:
        last_err: Exception | None = None
        for i, key in enumerate(self._keys):
            url = f"{self._base}/models/{self._model}:batchEmbedContents?key={key}"
            try:
                return _request_with_retry(httpx.post, url, json={"requests": requests_body}, timeout=60)
            except Exception as e:
                last_err = e
                if i < len(self._keys) - 1:
                    logger.info("Gemini embed key #%d exhausted, rotating: %s", i + 1, str(e)[:160])
        assert last_err is not None
        raise last_err

    # Per-request word budget. batchEmbedContents accepts up to 100 contents,
    # but a full 100-chunk batch of dense text (~90k words / ~150k+ tokens)
    # gets hard-429'd regardless of retries, which used to kill indexing of
    # any code-heavy corpus. 8k words (~16-20k tokens) is an order of
    # magnitude under the observed failure point and probed safe.
    MAX_BATCH_ITEMS = 100
    MAX_BATCH_WORDS = 8000

    def embed(self, texts: list[str]) -> np.ndarray:
        all_embeddings = []

        batch: list[str] = []
        batch_words = 0
        def flush():
            nonlocal batch, batch_words
            if not batch:
                return
            requests_body = [{"model": f"models/{self._model}", "content": {"parts": [{"text": t}]}} for t in batch]
            resp = self._post_with_key_rotation(requests_body)
            embeddings = resp.json()["embeddings"]
            all_embeddings.extend([e["values"] for e in embeddings])
            batch, batch_words = [], 0

        for t in texts:
            words = len(t.split())
            if batch and (len(batch) >= self.MAX_BATCH_ITEMS or batch_words + words > self.MAX_BATCH_WORDS):
                flush()
            batch.append(t)
            batch_words += words
        flush()

        return np.array(all_embeddings, dtype=np.float32)

    def dim(self) -> int:
        return self.MODEL_DIMS.get(self._model, 3072)

    def model_name(self) -> str:
        return self._model


def get_embedder(provider: str = "", *, probe: bool = True) -> EmbeddingProvider:
    """Resolve an embedder by provider name, with optional probe-based fallback.

    Behavior:
      * Explicit provider (e.g. "gemini") — honored verbatim, no probe.
        Callers that must match a corpus's stored embedding model should
        pass the provider explicitly (retrieval does this via
        `embedding_model`) to guarantee dim compatibility.
      * Empty provider — resolves to the first working provider in the
        chain below. If probe=True (default), each candidate is
        test-called ("ping") so geo-block / quota / bad-key errors
        short-circuit to the next. If probe=False, the first configured
        provider is returned without a network call (fast path for tests).

    Fallback chain when no provider is specified (or EMBEDDING_PROVIDER env):
      1. Gemini — primary (rich quality, high free-tier limits)
      2. OpenAI
      3. Zhipu — last resort (cheap, China-friendly)
    """
    known: dict[str, type[EmbeddingProvider]] = {
        "zhipu": ZhipuEmbedder, "openai": OpenAIEmbedder, "gemini": GeminiEmbedder,
    }
    requested = (provider or EMBEDDING_PROVIDER or "").lower()
    if requested in known:
        return known[requested]()

    chain: list[tuple[str, type[EmbeddingProvider]]] = []
    if GEMINI_API_KEY:
        chain.append(("gemini", GeminiEmbedder))
    if OPENAI_API_KEY:
        chain.append(("openai", OpenAIEmbedder))
    if ZHIPU_API_KEY:
        chain.append(("zhipu", ZhipuEmbedder))
    if not chain:
        raise ValueError("No embedding provider configured. Set GEMINI_API_KEY, OPENAI_API_KEY, or ZHIPU_API_KEY in .env")

    if not probe:
        return chain[0][1]()

    errors: list[str] = []
    for name, cls in chain:
        try:
            emb = cls()
            emb.embed(["ping"])  # surfaces geo-block / quota / bad-key fast
            logger.info("Embedder resolved: %s (%s)", name, emb.model_name())
            return emb
        except Exception as e:
            errors.append(f"{name}: {str(e)[:160]}")
            logger.warning("%s unavailable, trying next: %s", name, errors[-1])
    raise ValueError("All embedding providers failed: " + " / ".join(errors))


def vector_to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def blob_to_vector(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32).reshape(dim)
