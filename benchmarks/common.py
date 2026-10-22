"""Shared helpers for the benchmark scripts.

The benchmark uses its own storage directory (``storage/benchmark``) so it never
touches a real user's data, and talks to the application services directly
(no HTTP), which keeps it honest: it exercises exactly the retrieval and
generation code the API uses.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
os.environ.setdefault("STORAGE_DIR", str(ROOT / "storage" / "benchmark"))
os.environ.setdefault("APP_ENV", "benchmark")
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import get_session_factory, init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Chunk, Document, User  # noqa: E402
from app.services.document_service import process_document, save_upload  # noqa: E402
from app.services.llm import LLMProvider, build_provider, resolve_llm  # noqa: E402

BENCH_EMAIL = "benchmark@local"
NOTES_DIR = ROOT / "data" / "sample_notes"
RESULTS_DIR = ROOT / "benchmarks" / "results"
EVAL_SET = ROOT / "benchmarks" / "eval_set.json"


def bench_session() -> Session:
    init_db()
    return get_session_factory()()


def bench_user(db: Session) -> User:
    user = db.execute(select(User).where(User.email == BENCH_EMAIL)).scalar_one_or_none()
    if user is None:
        user = User(email=BENCH_EMAIL, name="Benchmark", password_hash=hash_password("benchmark-password"))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def ensure_corpus(db: Session, user: User, *, verbose: bool = True) -> list[Document]:
    """Ingest every PDF in data/sample_notes (idempotent)."""
    pdfs = sorted(NOTES_DIR.glob("*.pdf"))
    if not pdfs:
        raise SystemExit("No PDFs in data/sample_notes - run `python scripts/fetch_open_notes.py` first.")
    existing = {d.filename: d for d in db.execute(select(Document).where(Document.user_id == user.id)).scalars()}
    docs: list[Document] = []
    for pdf in pdfs:
        safe = pdf.name.replace("(", "_").replace(")", "_")
        doc = next((d for d in existing.values() if d.title == pdf.stem.replace("_", " ") or d.filename in (pdf.name, safe)), None)
        if doc is None or doc.status != "ready":
            if verbose:
                print(f"  ingesting {pdf.name} ...", flush=True)
            if doc is None:
                doc = save_upload(db, user, filename=pdf.name, data=pdf.read_bytes(), title=pdf.stem.replace("_", " "))
            process_document(doc.id)
            db.expire_all()
            doc = db.get(Document, doc.id)
            if verbose:
                print(f"    -> {doc.status}, {doc.pages} pages, {doc.chunk_count} chunks")
        docs.append(doc)
    return docs


def get_llm(db: Session, provider: str | None, model: str | None) -> LLMProvider:
    override = {}
    if provider:
        override["provider"] = provider
    if model:
        override["model"] = model
    return build_provider(resolve_llm(db, None, override=override))


def chunk_by_id(db: Session, chunk_id: int) -> Chunk | None:
    return db.get(Chunk, chunk_id)
