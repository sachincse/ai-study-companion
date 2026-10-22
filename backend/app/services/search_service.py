"""Hybrid retrieval: SQLite FTS5 keyword search (BM25) + dense vector search,
fused with Reciprocal Rank Fusion. Every hit is scoped to the requesting user.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from app.core.database import fts_available
from app.models import Chunk, Document
from app.services.embeddings import get_embedder
from app.services.vector_store import get_vector_store

log = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were", "be", "with",
    "what", "which", "who", "how", "why", "when", "where", "does", "do", "did", "explain", "define", "describe",
    "me", "my", "i", "you", "it", "its", "this", "that", "these", "those", "about", "from", "by", "as", "at",
    "can", "could", "would", "should", "give", "tell", "please", "notes", "note", "unit", "topic", "question",
}
RRF_K = 60
RELEVANCE_CUTOFF = 0.5  # drop candidates whose fused score is below half of the best one


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    document_title: str
    page_no: int | None
    heading: str | None
    content: str
    score: float
    keyword_score: float = 0.0
    vector_score: float = 0.0
    snippet: str = ""
    methods: list[str] = field(default_factory=list)

    def citation_label(self) -> str:
        page = f", p. {self.page_no}" if self.page_no else ""
        return f"{self.document_title}{page}"


def query_terms(query: str, limit: int = 12) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_\-]*", query.lower())
    seen: list[str] = []
    for t in tokens:
        t = t.strip("-_")
        if len(t) < 2 or t in STOPWORDS or t in seen:
            continue
        seen.append(t)
    return seen[:limit]


def _fts_match_expression(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"' for t in terms)


def make_snippet(content: str, terms: list[str], width: int = 240) -> str:
    """A window of ``content`` around the first query term, with matches marked as [[term]]."""
    lowered = content.lower()
    hit = min((lowered.find(t) for t in terms if t in lowered), default=-1)
    if hit < 0:
        return content[:width] + (" ..." if len(content) > width else "")
    start = max(0, hit - width // 3)
    end = min(len(content), start + width)
    window = content[start:end]
    pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r")\w*", re.IGNORECASE)
    marked = pattern.sub(lambda m: f"[[{m.group(0)}]]", window)
    return ("... " if start > 0 else "") + marked + (" ..." if end < len(content) else "")


def keyword_search(
    db: Session, user_id: int, query: str, top_k: int = 12, document_ids: list[int] | None = None
) -> list[tuple[int, float, str]]:
    """Return ``(chunk_id, score, snippet)`` ranked by BM25 (higher is better)."""
    terms = query_terms(query)
    if not terms:
        return []
    if not fts_available():
        return _like_search(db, user_id, terms, top_k, document_ids)
    sql = (
        "SELECT c.id AS id, bm25(chunks_fts) AS rank, "
        "snippet(chunks_fts, 0, '[[', ']]', ' ... ', 18) AS snip "
        "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid "
        "WHERE chunks_fts MATCH :q AND c.user_id = :uid "
    )
    params: dict = {"q": _fts_match_expression(terms), "uid": user_id, "k": top_k}
    stmt = text(sql + ("AND c.document_id IN :doc_ids " if document_ids else "") + "ORDER BY rank LIMIT :k")
    if document_ids:
        stmt = stmt.bindparams(bindparam("doc_ids", expanding=True))
        params["doc_ids"] = list(document_ids)
    rows = db.execute(stmt, params).all()
    return [(int(r.id), float(-r.rank), r.snip or "") for r in rows]


def _like_search(db: Session, user_id: int, terms: list[str], top_k: int, document_ids: list[int] | None):
    stmt = select(Chunk).where(Chunk.user_id == user_id)
    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))
    scored: list[tuple[int, float, str]] = []
    for chunk in db.execute(stmt).scalars():
        lowered = chunk.content.lower()
        hits = sum(lowered.count(t) for t in terms)
        if hits:
            scored.append((chunk.id, float(hits), chunk.content[:240]))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def vector_search(user_id: int, query: str, top_k: int = 12, document_ids: list[int] | None = None) -> list[tuple[int, float]]:
    embedder = get_embedder()
    store = get_vector_store()
    hits = store.query(embedder.embed_query(query), top_k, user_id, document_ids)
    out: list[tuple[int, float]] = []
    for h in hits:
        try:
            out.append((int(str(h.id).split("-")[-1]), float(h.score)))
        except ValueError:
            continue
    return out


def hybrid_search(
    db: Session,
    user_id: int,
    query: str,
    *,
    top_k: int = 6,
    document_ids: list[int] | None = None,
    mode: str = "hybrid",
) -> list[RetrievedChunk]:
    """Fuse keyword and vector rankings (RRF) and hydrate the winning chunks."""
    query = (query or "").strip()
    if not query:
        return []
    candidate_k = max(top_k * 3, 10)
    keyword_hits: list[tuple[int, float, str]] = []
    vector_hits: list[tuple[int, float]] = []
    if mode in ("hybrid", "keyword"):
        try:
            keyword_hits = keyword_search(db, user_id, query, candidate_k, document_ids)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("keyword search failed: %s", exc)
    if mode in ("hybrid", "semantic"):
        try:
            vector_hits = vector_search(user_id, query, candidate_k, document_ids)
        except Exception as exc:
            log.warning("vector search unavailable, falling back to keywords: %s", exc)

    fused: dict[int, float] = {}
    kw_scores: dict[int, float] = {}
    vec_scores: dict[int, float] = {}
    snippets: dict[int, str] = {}
    methods: dict[int, list[str]] = {}
    for rank, (cid, score, snip) in enumerate(keyword_hits):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        kw_scores[cid] = score
        snippets[cid] = snip
        methods.setdefault(cid, []).append("keyword")
    for rank, (cid, score) in enumerate(vector_hits):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        vec_scores[cid] = score
        methods.setdefault(cid, []).append("semantic")
    if not fused:
        return []

    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    best = ordered[0][1]
    ordered = [kv for kv in ordered if kv[1] >= best * RELEVANCE_CUTOFF][:top_k]
    terms = query_terms(query)
    ids = [cid for cid, _ in ordered]
    rows = db.execute(
        select(Chunk, Document.title).join(Document, Document.id == Chunk.document_id).where(Chunk.id.in_(ids), Chunk.user_id == user_id)
    ).all()
    by_id = {chunk.id: (chunk, title) for chunk, title in rows}
    results: list[RetrievedChunk] = []
    max_fused = ordered[0][1] if ordered else 1.0
    for cid, score in ordered:
        if cid not in by_id:
            continue
        chunk, title = by_id[cid]
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=title,
                page_no=chunk.page_no,
                heading=chunk.heading,
                content=chunk.content,
                score=round(score / max_fused, 4),
                keyword_score=round(kw_scores.get(cid, 0.0), 4),
                vector_score=round(vec_scores.get(cid, 0.0), 4),
                snippet=snippets.get(cid) or make_snippet(chunk.content, terms),
                methods=methods.get(cid, []),
            )
        )
    return results


def sample_document_chunks(db: Session, user_id: int, document_ids: list[int], limit: int = 10) -> list[RetrievedChunk]:
    """Evenly spaced chunks across the given documents (for summaries/quizzes without a topic)."""
    rows = db.execute(
        select(Chunk, Document.title)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.user_id == user_id, Chunk.document_id.in_(document_ids))
        .order_by(Chunk.document_id, Chunk.chunk_index)
    ).all()
    if not rows:
        return []
    if len(rows) > limit:
        step = len(rows) / limit
        rows = [rows[int(i * step)] for i in range(limit)]
    return [
        RetrievedChunk(
            chunk_id=c.id,
            document_id=c.document_id,
            document_title=t,
            page_no=c.page_no,
            heading=c.heading,
            content=c.content,
            score=1.0,
            snippet=c.content[:240],
            methods=["sampled"],
        )
        for c, t in rows
    ]
