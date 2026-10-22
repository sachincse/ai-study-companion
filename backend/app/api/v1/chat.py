from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, get_session_factory
from app.core.deps import ai_rate_limit, get_current_user
from app.models import ChatMessage, Document, User
from app.schemas.chat import (
    BookmarkRequest,
    FeedbackRequest,
    MessageOut,
    SendMessageRequest,
    SessionCreate,
    SessionDetail,
    SessionOut,
    SessionSummary,
    SessionUpdate,
    SyncChatResponse,
)
from app.schemas.common import Message
from app.services import chat_service
from app.services.activity import log_activity
from app.services.generation import subject_hint
from app.services.llm import LLMError, get_llm
from app.services.rag_service import answer_once, stream_answer

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _owned_document_ids(db: Session, user: User, ids: list[int] | None) -> list[int] | None:
    """Keep only documents that still exist and belong to the user (deleted ids would silently empty retrieval)."""
    if not ids:
        return None
    owned = {d for (d,) in db.execute(select(Document.id).where(Document.user_id == user.id, Document.id.in_(ids))).all()}
    kept = [i for i in ids if i in owned]
    return kept or None


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SessionOut:
    session = chat_service.create_session(db, user, title=payload.title, subject_id=payload.subject_id, document_ids=payload.document_ids, answer_mode=payload.answer_mode)
    return SessionOut.model_validate(session)


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SessionSummary]:
    out = []
    for item in chat_service.list_sessions(db, user):
        base = SessionOut.model_validate(item["session"]).model_dump()
        out.append(SessionSummary(**base, message_count=item["message_count"], preview=item["preview"]))
    return out


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SessionDetail:
    session = chat_service.get_owned_session(db, user, session_id, with_messages=True)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return SessionDetail.model_validate(session)


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def update_session(session_id: int, payload: SessionUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SessionOut:
    session = chat_service.get_owned_session(db, user, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(session, key, value)
    db.commit()
    db.refresh(session)
    return SessionOut.model_validate(session)


@router.delete("/sessions/{session_id}", response_model=Message)
def delete_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Message:
    session = chat_service.get_owned_session(db, user, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    db.delete(session)
    db.commit()
    return Message(detail="Chat deleted")


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: int, payload: SendMessageRequest, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> StreamingResponse:
    """Ask the tutor. Streams Server-Sent Events: sources, token*, done | error."""
    session = chat_service.get_owned_session(db, user, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    try:
        llm = get_llm(db, user)
    except LLMError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.user_message) from exc

    answer_mode = payload.answer_mode or session.answer_mode
    document_ids = _owned_document_ids(db, user, payload.document_ids if payload.document_ids is not None else session.document_ids)
    hint = subject_hint(db, session.subject_id)
    history = chat_service.recent_history(db, session, limit=8)
    user_msg = chat_service.add_user_message(db, session, user, payload.content)
    session_pk = session.id
    user_pk = user.id

    async def event_stream() -> AsyncIterator[str]:
        factory = get_session_factory()
        with factory() as sdb:
            s = chat_service.get_owned_session(sdb, user, session_pk)
            u = sdb.get(User, user_pk)
            yield _sse({"type": "user_message", "message": MessageOut.model_validate(user_msg).model_dump(mode="json")})
            captured_sources: list[dict] = []
            try:
                async for event in stream_answer(
                    llm, sdb, user_pk, payload.content, document_ids=document_ids, answer_mode=answer_mode, history=history, subject_hint=hint
                ):
                    if event["type"] == "sources":
                        captured_sources = event["sources"]
                        yield _sse({"type": "sources", "sources": [{k: v for k, v in src.items() if k != "content"} for src in captured_sources], "grounded": event["grounded"]})
                    elif event["type"] == "done":
                        msg = chat_service.add_assistant_message(
                            sdb, s, u, event["answer"], sources=captured_sources, provider=event["provider"], model=event["model"],
                            follow_ups=event["follow_ups"], grounded=event["grounded"], latency_ms=event["latency_ms"],
                        )
                        log_activity(sdb, user_pk, "chat", ref_id=msg.id, subject_id=s.subject_id, detail=payload.content[:120])
                        yield _sse({"type": "done", "message": MessageOut.model_validate(msg).model_dump(mode="json")})
                    else:
                        yield _sse(event)
            except Exception:  # noqa: BLE001
                log.exception("chat stream failed")
                yield _sse({"type": "error", "message": "Something went wrong while answering. Please try again."})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/sessions/{session_id}/messages/sync", response_model=SyncChatResponse)
async def send_message_sync(session_id: int, payload: SendMessageRequest, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> SyncChatResponse:
    """Non-streaming variant (used by tests and simple clients)."""
    session = chat_service.get_owned_session(db, user, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    llm = get_llm(db, user)
    history = chat_service.recent_history(db, session, limit=8)
    user_msg = chat_service.add_user_message(db, session, user, payload.content)
    answer, ctx = await answer_once(
        llm, db, user.id, payload.content,
        document_ids=_owned_document_ids(db, user, payload.document_ids if payload.document_ids is not None else session.document_ids),
        answer_mode=payload.answer_mode or session.answer_mode, history=history,
    )
    msg = chat_service.add_assistant_message(db, session, user, answer, sources=ctx.sources, provider=llm.id, model=llm.model, follow_ups=None, grounded=ctx.grounded, latency_ms=None)
    log_activity(db, user.id, "chat", ref_id=msg.id, subject_id=session.subject_id, detail=payload.content[:120])
    return SyncChatResponse(user_message=MessageOut.model_validate(user_msg), assistant_message=MessageOut.model_validate(msg))


@router.post("/messages/{message_id}/bookmark", response_model=MessageOut)
def bookmark(message_id: int, payload: BookmarkRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageOut:
    msg = db.get(ChatMessage, message_id)
    if msg is None or msg.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    msg.bookmarked = payload.bookmarked
    db.commit()
    db.refresh(msg)
    return MessageOut.model_validate(msg)


@router.post("/messages/{message_id}/feedback", response_model=MessageOut)
def feedback(message_id: int, payload: FeedbackRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageOut:
    msg = db.get(ChatMessage, message_id)
    if msg is None or msg.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    msg.feedback = payload.value
    db.commit()
    db.refresh(msg)
    return MessageOut.model_validate(msg)


@router.get("/bookmarks", response_model=list[MessageOut])
def bookmarks(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[MessageOut]:
    return [MessageOut.model_validate(m) for m in chat_service.list_bookmarks(db, user)]
