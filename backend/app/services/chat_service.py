"""Conversations, message persistence, bookmarks and full-text history search."""
from __future__ import annotations

import re

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.database import fts_available
from app.models import ChatMessage, ChatSession, MessageSource, User
from app.services.search_service import RetrievedChunk, query_terms


def create_session(
    db: Session,
    user: User,
    *,
    title: str | None = None,
    subject_id: int | None = None,
    document_ids: list[int] | None = None,
    answer_mode: str = "exam",
) -> ChatSession:
    session = ChatSession(
        user_id=user.id,
        title=(title or "New chat")[:200],
        subject_id=subject_id,
        document_ids=document_ids or None,
        answer_mode=answer_mode,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_owned_session(db: Session, user: User, session_id: int, *, with_messages: bool = False) -> ChatSession | None:
    stmt = select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user.id)
    if with_messages:
        stmt = stmt.options(selectinload(ChatSession.messages).selectinload(ChatMessage.sources))
    return db.execute(stmt).scalar_one_or_none()


def list_sessions(db: Session, user: User, limit: int = 100) -> list[dict]:
    counts = (
        select(ChatMessage.session_id, func.count(ChatMessage.id).label("n"))
        .where(ChatMessage.user_id == user.id)
        .group_by(ChatMessage.session_id)
        .subquery()
    )
    rows = db.execute(
        select(ChatSession, counts.c.n)
        .outerjoin(counts, counts.c.session_id == ChatSession.id)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
        .limit(limit)
    ).all()
    out = []
    for session, n in rows:
        last = db.execute(
            select(ChatMessage.content).where(ChatMessage.session_id == session.id).order_by(ChatMessage.id.desc()).limit(1)
        ).scalar_one_or_none()
        out.append({"session": session, "message_count": int(n or 0), "preview": (last or "")[:140]})
    return out


def auto_title(question: str) -> str:
    cleaned = re.sub(r"\s+", " ", question).strip().strip("?.!")
    if not cleaned:
        return "New chat"
    words = cleaned.split(" ")
    title = " ".join(words[:9])
    if len(words) > 9:
        title += "..."
    return title[:120]


def add_user_message(db: Session, session: ChatSession, user: User, content: str) -> ChatMessage:
    msg = ChatMessage(session_id=session.id, user_id=user.id, role="user", content=content)
    db.add(msg)
    if session.title == "New chat":
        session.title = auto_title(content)
    db.commit()
    db.refresh(msg)
    return msg


def add_assistant_message(
    db: Session,
    session: ChatSession,
    user: User,
    content: str,
    *,
    sources: list[RetrievedChunk] | list[dict],
    provider: str | None,
    model: str | None,
    follow_ups: list[str] | None,
    grounded: bool,
    latency_ms: int | None,
) -> ChatMessage:
    msg = ChatMessage(
        session_id=session.id,
        user_id=user.id,
        role="assistant",
        content=content,
        provider=provider,
        model=model,
        follow_ups=follow_ups or None,
        grounded=grounded,
        latency_ms=latency_ms,
    )
    db.add(msg)
    db.flush()
    for rank, src in enumerate(sources, start=1):
        if isinstance(src, RetrievedChunk):
            data = {
                "chunk_id": src.chunk_id,
                "document_id": src.document_id,
                "document_title": src.document_title,
                "page_no": src.page_no,
                "score": src.score,
                "snippet": src.snippet,
            }
        else:
            data = src
        db.add(
            MessageSource(
                message_id=msg.id,
                chunk_id=data.get("chunk_id"),
                document_id=data.get("document_id"),
                document_title=data.get("document_title"),
                page_no=data.get("page_no"),
                rank=rank,
                score=float(data.get("score") or 0.0),
                snippet=(data.get("snippet") or "")[:600],
            )
        )
    session.updated_at = func.now()
    db.commit()
    db.refresh(msg)
    return msg


def recent_history(db: Session, session: ChatSession, limit: int = 8) -> list[ChatMessage]:
    rows = db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.id.desc()).limit(limit)
    ).scalars().all()
    return list(reversed(rows))


def search_history(db: Session, user: User, query: str, limit: int = 20) -> list[dict]:
    terms = query_terms(query)
    if not terms:
        return []
    if fts_available():
        sql = text(
            "SELECT m.id AS id, bm25(chat_messages_fts) AS rank, "
            "snippet(chat_messages_fts, 0, '[[', ']]', ' ... ', 20) AS snip "
            "FROM chat_messages_fts JOIN chat_messages m ON m.id = chat_messages_fts.rowid "
            "WHERE chat_messages_fts MATCH :q AND m.user_id = :uid ORDER BY rank LIMIT :k"
        )
        rows = db.execute(sql, {"q": " OR ".join(f'"{t}"' for t in terms), "uid": user.id, "k": limit}).all()
        hits = [(int(r.id), r.snip or "") for r in rows]
    else:
        stmt = select(ChatMessage).where(ChatMessage.user_id == user.id)
        hits = [(m.id, m.content[:200]) for m in db.execute(stmt).scalars() if any(t in m.content.lower() for t in terms)][:limit]
    if not hits:
        return []
    ids = [h[0] for h in hits]
    msgs = {m.id: m for m in db.execute(select(ChatMessage).where(ChatMessage.id.in_(ids))).scalars()}
    sessions = {s.id: s for s in db.execute(select(ChatSession).where(ChatSession.id.in_({m.session_id for m in msgs.values()}))).scalars()}
    out = []
    for mid, snip in hits:
        m = msgs.get(mid)
        if not m:
            continue
        s = sessions.get(m.session_id)
        out.append(
            {
                "message_id": m.id,
                "session_id": m.session_id,
                "session_title": s.title if s else "",
                "role": m.role,
                "snippet": snip,
                "content": m.content,
                "created_at": m.created_at,
                "bookmarked": m.bookmarked,
            }
        )
    return out


def list_bookmarks(db: Session, user: User, limit: int = 50) -> list[ChatMessage]:
    return list(
        db.execute(
            select(ChatMessage)
            .options(selectinload(ChatMessage.sources))
            .where(ChatMessage.user_id == user.id, ChatMessage.bookmarked.is_(True))
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        ).scalars()
    )


def chat_stats(db: Session, user: User) -> dict:
    sessions = db.scalar(select(func.count(ChatSession.id)).where(ChatSession.user_id == user.id)) or 0
    messages = db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.user_id == user.id, ChatMessage.role == "user")) or 0
    bookmarks = db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.user_id == user.id, ChatMessage.bookmarked.is_(True))) or 0
    return {"sessions": int(sessions), "questions": int(messages), "bookmarks": int(bookmarks)}
