from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import OptUtcDatetime, ORMModel, UtcDatetime


class DocumentOut(ORMModel):
    id: int
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    pages: int
    status: str
    error: str | None = None
    chunk_count: int
    char_count: int
    subject_id: int | None = None
    unit: int | None = None
    created_at: UtcDatetime
    processed_at: OptUtcDatetime = None


class ChunkOut(ORMModel):
    id: int
    document_id: int
    chunk_index: int
    page_no: int | None = None
    heading: str | None = None
    content: str
    token_estimate: int


class DocumentStats(BaseModel):
    total: int
    ready: int
    chunks: int


class SearchHit(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    page_no: int | None = None
    heading: str | None = None
    snippet: str
    content: str
    score: float
    keyword_score: float = 0.0
    vector_score: float = 0.0
    methods: list[str] = []


class SearchResponse(BaseModel):
    query: str
    mode: str
    hits: list[SearchHit]


class HistoryHit(BaseModel):
    message_id: int
    session_id: int
    session_title: str
    role: str
    snippet: str
    content: str
    created_at: UtcDatetime
    bookmarked: bool
