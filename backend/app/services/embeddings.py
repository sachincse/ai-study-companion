"""Pluggable embedding models.

* ``local``  - fastembed (BAAI/bge-small-en-v1.5, 384 dims). No API key, runs on CPU.
* ``openai`` - text-embedding-3-small via the OpenAI API.
* ``gemini`` - gemini-embedding-001 via Google's OpenAI-compatible endpoint.
* ``ollama`` - nomic-embed-text (or any embedding model you pulled) via Ollama.
* ``hash``   - deterministic bag-of-words embedding used by the test-suite.

The embedding provider is deployment-wide (changing it requires re-indexing
because vector dimensions differ), unlike the chat LLM which is per-user.
"""
from __future__ import annotations

import hashlib
import math
import re
import threading
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Cheap, deterministic embedding (feature hashing). Only for tests/offline demos."""

    name = "hash-256"
    dim = 256

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0 if (h >> 8) % 2 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class LocalEmbedder:
    """fastembed ONNX model, downloaded once into storage/models."""

    name = "BAAI/bge-small-en-v1.5"
    dim = 384

    def __init__(self, model_name: str | None = None, cache_dir: str | None = None) -> None:
        from fastembed import TextEmbedding

        self.name = model_name or self.name
        self._model = TextEmbedding(model_name=self.name, cache_dir=cache_dir)
        probe = next(iter(self._model.embed(["dimension probe"])))
        self.dim = len(probe)
        self._lock = threading.Lock()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            return [v.tolist() for v in self._model.embed(texts, batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        with self._lock:
            return next(iter(self._model.query_embed(text))).tolist()


class OpenAICompatibleEmbedder:
    """Any ``/v1/embeddings`` endpoint (OpenAI, Gemini OpenAI-compat, Ollama, LM Studio...)."""

    def __init__(self, *, name: str, base_url: str | None, api_key: str | None, model: str, dim: int | None = None) -> None:
        from openai import OpenAI

        self.name = name
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key or "not-needed")
        self.dim = dim or len(self.embed_query("dimension probe"))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            batch = [t[:8000] for t in texts[i : i + 64]]
            resp = self._client.embeddings.create(model=self.model, input=batch)
            out.extend([d.embedding for d in sorted(resp.data, key=lambda d: d.index)])
        return out

    def embed_query(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self.model, input=text[:8000])
        return resp.data[0].embedding


def build_embedder(provider: str | None = None) -> Embedder:
    settings = get_settings()
    provider = (provider or settings.embedding_provider).lower()
    model = settings.embedding_model
    if provider == "hash":
        return HashEmbedder()
    if provider == "local":
        settings.ensure_dirs()
        return LocalEmbedder(model_name=model, cache_dir=str(settings.models_cache_dir))
    if provider == "openai":
        return OpenAICompatibleEmbedder(
            name=f"openai/{model or 'text-embedding-3-small'}",
            base_url=None,
            api_key=settings.openai_api_key,
            model=model or "text-embedding-3-small",
        )
    if provider == "gemini":
        return OpenAICompatibleEmbedder(
            name=f"gemini/{model or 'gemini-embedding-001'}",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=settings.gemini_api_key,
            model=model or "gemini-embedding-001",
        )
    if provider == "ollama":
        return OpenAICompatibleEmbedder(
            name=f"ollama/{model or 'nomic-embed-text'}",
            base_url=settings.ollama_base_url.rstrip("/") + "/v1",
            api_key="ollama",
            model=model or "nomic-embed-text",
        )
    raise ValueError(f"Unknown EMBEDDING_PROVIDER '{provider}'. Use local, openai, gemini, ollama or hash.")


_embedder: Embedder | None = None
_embedder_lock = threading.Lock()
_embedder_error: str | None = None


def get_embedder() -> Embedder:
    """Process-wide embedder (lazy, thread-safe). Raises if the model cannot load."""
    global _embedder, _embedder_error
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        if _embedder is None:
            try:
                _embedder = build_embedder()
                _embedder_error = None
            except Exception as exc:  # pragma: no cover - depends on environment
                _embedder_error = str(exc)
                raise
    return _embedder


def embedder_status() -> dict:
    return {
        "provider": get_settings().embedding_provider,
        "ready": _embedder is not None,
        "model": getattr(_embedder, "name", None),
        "dim": getattr(_embedder, "dim", None),
        "error": _embedder_error,
    }


def reset_embedder(embedder: Embedder | None = None) -> None:
    """Swap the process-wide embedder (tests inject :class:`HashEmbedder`)."""
    global _embedder, _embedder_error
    _embedder = embedder
    _embedder_error = None


@lru_cache(maxsize=1)
def warm_up_in_background() -> threading.Thread:
    thread = threading.Thread(target=lambda: _safe_warm_up(), name="embedder-warmup", daemon=True)
    thread.start()
    return thread


def _safe_warm_up() -> None:
    try:
        get_embedder()
    except Exception:
        pass
