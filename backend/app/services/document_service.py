"""Upload handling and the ingestion pipeline (parse -> chunk -> embed -> index)."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models import Chunk, Document, User
from app.services.activity import log_activity
from app.services.chunking import ChunkingConfig, chunk_pages
from app.services.embeddings import get_embedder
from app.services.parsing import MIME_BY_EXT, SUPPORTED_EXTENSIONS, EmptyDocumentError, UnsupportedFileError, parse_bytes
from app.services.vector_store import get_vector_store

log = logging.getLogger(__name__)


class UploadError(ValueError):
    pass


def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._\- ]+", "_", name).strip() or "upload"
    return name[:120]


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def save_upload(
    db: Session,
    user: User,
    *,
    filename: str,
    data: bytes,
    title: str | None = None,
    subject_id: int | None = None,
    unit: int | None = None,
) -> Document:
    settings = get_settings()
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UploadError(f"Unsupported file type '{ext or 'unknown'}'. Upload PDF, DOCX, TXT or Markdown.")
    if not data:
        raise UploadError("The uploaded file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise UploadError(f"File is larger than the {settings.max_upload_mb} MB limit.")

    safe = _safe_filename(filename)
    doc = Document(
        user_id=user.id,
        subject_id=subject_id,
        unit=unit,
        title=(title or Path(safe).stem.replace("_", " ")).strip()[:255],
        filename=safe,
        file_path="",
        mime_type=MIME_BY_EXT.get(ext, "application/octet-stream"),
        size_bytes=len(data),
        status="uploaded",
    )
    db.add(doc)
    db.flush()
    user_dir = settings.uploads_dir / f"user_{user.id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{doc.id}_{safe}"
    path.write_bytes(data)
    doc.file_path = str(path)
    db.commit()
    db.refresh(doc)
    return doc


def process_document(document_id: int) -> None:
    """Background job: parse, chunk, embed and index one document. Own DB session."""
    factory = get_session_factory()
    with factory() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status = "processing"
        doc.error = None
        db.commit()
        try:
            _ingest(db, doc)
            doc.status = "ready"
            doc.processed_at = _utcnow()
            db.commit()
            log_activity(db, doc.user_id, "upload", ref_id=doc.id, subject_id=doc.subject_id, detail=doc.title)
            log.info("indexed document %s (%s chunks)", doc.id, doc.chunk_count)
        except (UnsupportedFileError, EmptyDocumentError) as exc:
            doc.status = "failed"
            doc.error = str(exc)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            log.exception("ingestion failed for document %s", document_id)
            doc.status = "failed"
            doc.error = f"Indexing failed: {str(exc)[:300]}"
            db.commit()


def _ingest(db: Session, doc: Document) -> None:
    settings = get_settings()
    data = Path(doc.file_path).read_bytes()
    parsed = parse_bytes(doc.filename, data)
    cfg = ChunkingConfig(chunk_size=settings.chunk_size_chars, chunk_overlap=settings.chunk_overlap_chars)
    chunks = chunk_pages(parsed.pages, cfg)
    if not chunks:
        raise EmptyDocumentError("No usable text could be extracted from this file.")

    # replace any previous index for this document
    db.execute(Chunk.__table__.delete().where(Chunk.document_id == doc.id))
    store = get_vector_store()
    store.delete_document(doc.user_id, doc.id)

    rows = [
        Chunk(
            document_id=doc.id,
            user_id=doc.user_id,
            chunk_index=c.index,
            page_no=c.page_no,
            heading=c.heading,
            content=c.content,
            token_estimate=c.token_estimate,
        )
        for c in chunks
    ]
    db.add_all(rows)
    db.flush()

    embedder = get_embedder()
    texts = [r.content for r in rows]
    embeddings = embedder.embed_documents(texts)
    store.add(
        ids=[f"chunk-{r.id}" for r in rows],
        embeddings=embeddings,
        metadatas=[
            {"user_id": doc.user_id, "document_id": doc.id, "chunk_id": r.id, "page_no": r.page_no or 0, "chunk_index": r.chunk_index}
            for r in rows
        ],
        documents=texts,
    )
    doc.pages = parsed.page_count
    doc.char_count = parsed.char_count
    doc.chunk_count = len(rows)


def delete_document(db: Session, user: User, doc: Document) -> None:
    try:
        get_vector_store().delete_document(user.id, doc.id)
    except Exception as exc:  # noqa: BLE001
        log.warning("vector cleanup failed for document %s: %s", doc.id, exc)
    try:
        if doc.file_path and Path(doc.file_path).exists():
            Path(doc.file_path).unlink()
    except OSError as exc:  # pragma: no cover
        log.warning("file cleanup failed: %s", exc)
    db.delete(doc)
    db.commit()


def list_documents(db: Session, user: User) -> list[Document]:
    return list(db.execute(select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())).scalars())


def get_owned_document(db: Session, user: User, document_id: int) -> Document | None:
    doc = db.get(Document, document_id)
    if doc is None or doc.user_id != user.id:
        return None
    return doc


def document_stats(db: Session, user: User) -> dict:
    total = db.scalar(select(func.count(Document.id)).where(Document.user_id == user.id)) or 0
    ready = db.scalar(select(func.count(Document.id)).where(Document.user_id == user.id, Document.status == "ready")) or 0
    chunks = db.scalar(select(func.count(Chunk.id)).where(Chunk.user_id == user.id)) or 0
    return {"total": int(total), "ready": int(ready), "chunks": int(chunks)}


def chunks_for_document(db: Session, user: User, doc: Document, page: int | None = None) -> list[Chunk]:
    stmt = select(Chunk).where(Chunk.document_id == doc.id, Chunk.user_id == user.id).order_by(Chunk.chunk_index)
    if page is not None:
        stmt = stmt.where(Chunk.page_no == page)
    return list(db.execute(stmt).scalars())
