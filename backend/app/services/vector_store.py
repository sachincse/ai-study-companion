"""Vector store abstraction: ChromaDB (persistent) or an in-memory numpy index."""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import get_settings


@dataclass
class VectorHit:
    id: str
    score: float  # cosine similarity in [0, 1]
    metadata: dict[str, Any]


class VectorStore(Protocol):
    name: str

    def add(self, ids: list[str], embeddings: list[list[float]], metadatas: list[dict], documents: list[str]) -> None: ...

    def query(self, embedding: list[float], top_k: int, user_id: int, document_ids: list[int] | None = None) -> list[VectorHit]: ...

    def delete_document(self, user_id: int, document_id: int) -> None: ...

    def count(self, user_id: int | None = None) -> int: ...


def _where(user_id: int, document_ids: list[int] | None) -> dict:
    if document_ids:
        return {"$and": [{"user_id": user_id}, {"document_id": {"$in": list(document_ids)}}]}
    return {"user_id": user_id}


class MemoryVectorStore:
    """Dependency-free store used in tests and for ``VECTOR_STORE=memory``."""

    name = "memory"

    def __init__(self) -> None:
        self._rows: dict[str, tuple[list[float], dict, str]] = {}
        self._lock = threading.Lock()

    def add(self, ids, embeddings, metadatas, documents) -> None:  # noqa: ANN001
        with self._lock:
            for i, e, m, d in zip(ids, embeddings, metadatas, documents):
                norm = math.sqrt(sum(x * x for x in e)) or 1.0
                self._rows[i] = ([x / norm for x in e], dict(m), d)

    def query(self, embedding, top_k, user_id, document_ids=None) -> list[VectorHit]:  # noqa: ANN001
        norm = math.sqrt(sum(x * x for x in embedding)) or 1.0
        q = [x / norm for x in embedding]
        hits: list[VectorHit] = []
        with self._lock:
            for id_, (vec, meta, _doc) in self._rows.items():
                if meta.get("user_id") != user_id:
                    continue
                if document_ids and meta.get("document_id") not in document_ids:
                    continue
                sim = sum(a * b for a, b in zip(q, vec))
                hits.append(VectorHit(id=id_, score=max(0.0, min(1.0, (sim + 1) / 2)), metadata=meta))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def delete_document(self, user_id: int, document_id: int) -> None:
        with self._lock:
            for id_ in [i for i, (_, m, _) in self._rows.items() if m.get("user_id") == user_id and m.get("document_id") == document_id]:
                del self._rows[id_]

    def count(self, user_id: int | None = None) -> int:
        with self._lock:
            if user_id is None:
                return len(self._rows)
            return sum(1 for _, (_, m, _) in self._rows.items() if m.get("user_id") == user_id)


class ChromaVectorStore:
    name = "chroma"

    def __init__(self, path: str, collection: str = "note_chunks") -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
        self._collection = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def add(self, ids, embeddings, metadatas, documents) -> None:  # noqa: ANN001
        if not ids:
            return
        clean_meta = [{k: (v if v is not None else 0) for k, v in m.items()} for m in metadatas]
        for i in range(0, len(ids), 256):
            self._collection.upsert(
                ids=ids[i : i + 256],
                embeddings=embeddings[i : i + 256],
                metadatas=clean_meta[i : i + 256],
                documents=documents[i : i + 256],
            )

    def query(self, embedding, top_k, user_id, document_ids=None) -> list[VectorHit]:  # noqa: ANN001
        if self._collection.count() == 0:
            return []
        res = self._collection.query(
            query_embeddings=[embedding],
            n_results=max(1, top_k),
            where=_where(user_id, document_ids),
            include=["metadatas", "distances"],
        )
        hits: list[VectorHit] = []
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        for id_, dist, meta in zip(ids, dists, metas):
            sim = 1.0 - float(dist)  # cosine distance -> similarity
            hits.append(VectorHit(id=id_, score=max(0.0, min(1.0, sim)), metadata=dict(meta or {})))
        return hits

    def delete_document(self, user_id: int, document_id: int) -> None:
        self._collection.delete(where={"$and": [{"user_id": user_id}, {"document_id": document_id}]})

    def count(self, user_id: int | None = None) -> int:
        if user_id is None:
            return self._collection.count()
        res = self._collection.get(where={"user_id": user_id}, include=[])
        return len(res.get("ids", []))


_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_vector_store() -> VectorStore:
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            settings = get_settings()
            if settings.vector_store.lower() == "memory":
                _store = MemoryVectorStore()
            else:
                settings.ensure_dirs()
                _store = ChromaVectorStore(path=str(settings.chroma_dir))
    return _store


def reset_vector_store(store: VectorStore | None = None) -> None:
    global _store
    _store = store
