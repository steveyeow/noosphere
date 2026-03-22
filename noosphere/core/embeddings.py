"""Pluggable embedding providers — OpenAI and Gemini."""

import json
import struct
from abc import ABC, abstractmethod

import httpx
import numpy as np

from noosphere.core.config import OPENAI_API_KEY, GEMINI_API_KEY, DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_DIM


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
            resp = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers=headers,
                json={"model": self._model, "input": batch},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data.sort(key=lambda x: x["index"])
            all_embeddings.extend([d["embedding"] for d in data])

        return np.array(all_embeddings, dtype=np.float32)

    def dim(self) -> int:
        return 1536

    def model_name(self) -> str:
        return self._model


class GeminiEmbedder(EmbeddingProvider):
    MODEL_DIMS = {"gemini-embedding-001": 3072, "text-embedding-004": 768}

    def __init__(self, api_key: str = "", model: str = "gemini-embedding-001"):
        self._key = api_key or GEMINI_API_KEY
        self._model = model
        if not self._key:
            raise ValueError("GEMINI_API_KEY is required for Gemini embeddings")

    def embed(self, texts: list[str]) -> np.ndarray:
        all_embeddings = []
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:batchEmbedContents?key={self._key}"

        for i in range(0, len(texts), 100):
            batch = texts[i : i + 100]
            requests_body = [{"model": f"models/{self._model}", "content": {"parts": [{"text": t}]}} for t in batch]
            resp = httpx.post(url, json={"requests": requests_body}, timeout=60)
            resp.raise_for_status()
            embeddings = resp.json()["embeddings"]
            all_embeddings.extend([e["values"] for e in embeddings])

        return np.array(all_embeddings, dtype=np.float32)

    def dim(self) -> int:
        return self.MODEL_DIMS.get(self._model, 3072)

    def model_name(self) -> str:
        return self._model


def get_embedder(provider: str = "") -> EmbeddingProvider:
    """Auto-detect available provider or use the specified one.

    When both keys are configured and no provider is specified,
    Gemini is preferred (higher free-tier rate limits).
    """
    if provider == "openai":
        return OpenAIEmbedder()
    if provider == "gemini":
        return GeminiEmbedder()
    if GEMINI_API_KEY:
        return GeminiEmbedder()
    if OPENAI_API_KEY:
        return OpenAIEmbedder()
    raise ValueError("No embedding provider configured. Set OPENAI_API_KEY or GEMINI_API_KEY in .env")


def vector_to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def blob_to_vector(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32).reshape(dim)
