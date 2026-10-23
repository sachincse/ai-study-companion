from __future__ import annotations

import re

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import ai_rate_limit, get_current_user
from app.models import User
from app.schemas.common import Message
from app.schemas.documents import ChunkOut, DocumentOut, DocumentStats, HistoryHit, SearchHit, SearchResponse
from app.services import chat_service, document_service
from app.services.document_service import UploadError
from app.services.search_service import hybrid_search
from app.workers.ingest import schedule_ingestion

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    subject_id: int | None = Form(default=None),
    unit: int | None = Form(default=None),
    user: User = Depends(ai_rate_limit),
    db: Session = Depends(get_db),
) -> DocumentOut:
    limit = get_settings().max_upload_mb * 1024 * 1024
    buf = bytearray()
    while chunk := await file.read(1024 * 1024):
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File is larger than the {get_settings().max_upload_mb} MB limit.")
    data = bytes(buf)
    try:
        doc = document_service.save_upload(db, user, filename=file.filename or "upload.txt", data=data, title=title, subject_id=subject_id, unit=unit)
    except UploadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    schedule_ingestion(background, doc.id)
    db.refresh(doc)
    return DocumentOut.model_validate(doc)


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[DocumentOut]:
    return [DocumentOut.model_validate(d) for d in document_service.list_documents(db, user)]


@router.get("/documents/stats", response_model=DocumentStats)
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DocumentStats:
    return DocumentStats(**document_service.document_stats(db, user))


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DocumentOut:
    doc = document_service.get_owned_document(db, user, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentOut.model_validate(doc)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkOut])
def get_chunks(document_id: int, page: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ChunkOut]:
    doc = document_service.get_owned_document(db, user, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return [ChunkOut.model_validate(c) for c in document_service.chunks_for_document(db, user, doc, page)]


@router.post("/documents/{document_id}/reindex", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def reindex(document_id: int, background: BackgroundTasks, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> DocumentOut:
    doc = document_service.get_owned_document(db, user, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if doc.status in ("uploaded", "processing"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This document is already being indexed")
    doc.status = "uploaded"
    doc.error = None
    db.commit()
    schedule_ingestion(background, doc.id)
    db.refresh(doc)
    return DocumentOut.model_validate(doc)


@router.delete("/documents/{document_id}", response_model=Message)
def delete_document(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Message:
    doc = document_service.get_owned_document(db, user, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    document_service.delete_document(db, user, doc)
    return Message(detail="Document deleted")


@router.get("/search", response_model=SearchResponse)
def search_notes(
    q: str,
    document_ids: str | None = None,
    mode: str = "hybrid",
    top_k: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchResponse:
    if mode not in ("hybrid", "keyword", "semantic"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mode must be hybrid, keyword or semantic")
    ids: list[int] | None = None
    if document_ids:
        parts = [x.strip() for x in document_ids.split(",") if x.strip()]
        if not all(re.fullmatch(r"[0-9]+", x) for x in parts):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "document_ids must be a comma-separated list of ids")
        ids = [int(x) for x in parts]
    k = min(max(top_k or get_settings().retrieval_top_k, 1), 30)
    hits = hybrid_search(db, user.id, q, top_k=k, document_ids=ids, mode=mode)
    return SearchResponse(query=q, mode=mode, hits=[SearchHit(**{k2: getattr(h, k2) for k2 in SearchHit.model_fields}) for h in hits])


@router.get("/search/history", response_model=list[HistoryHit])
def search_history(q: str, limit: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[HistoryHit]:
    return [HistoryHit(**h) for h in chat_service.search_history(db, user, q, limit=min(limit, 100))]
