from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, UtcDatetime


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    subject_id: int | None = None
    document_ids: list[int] | None = None
    answer_mode: str = "exam"


class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    pinned: bool | None = None
    subject_id: int | None = None
    document_ids: list[int] | None = None
    answer_mode: str | None = None


class SourceOut(ORMModel):
    id: int | None = None
    chunk_id: int | None = None
    document_id: int | None = None
    document_title: str | None = None
    page_no: int | None = None
    rank: int = 0
    score: float = 0.0
    snippet: str = ""


class MessageOut(ORMModel):
    id: int
    session_id: int
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    follow_ups: list[str] | None = None
    grounded: bool = False
    bookmarked: bool = False
    feedback: int | None = None
    latency_ms: int | None = None
    created_at: UtcDatetime
    sources: list[SourceOut] = []


class SessionOut(ORMModel):
    id: int
    title: str
    subject_id: int | None = None
    document_ids: list[int] | None = None
    answer_mode: str
    pinned: bool
    created_at: UtcDatetime
    updated_at: UtcDatetime


class SessionSummary(SessionOut):
    message_count: int = 0
    preview: str = ""


class SessionDetail(SessionOut):
    messages: list[MessageOut] = []


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    answer_mode: str | None = None
    document_ids: list[int] | None = None


class SyncChatResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut


class BookmarkRequest(BaseModel):
    bookmarked: bool = True


class FeedbackRequest(BaseModel):
    value: int | None = Field(default=None, ge=-1, le=1)
