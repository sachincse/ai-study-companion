"""SQLAlchemy engine/session plus the SQLite full-text indexes.

FTS5 virtual tables cannot be expressed with the ORM, so they are created with
raw DDL in :func:`init_db`. Triggers keep them in sync with the base tables.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        settings.ensure_dirs()
        url = settings.sqlalchemy_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, future=True)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, _):  # noqa: ANN001
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Dispose the engine (used by the test-suite to point at a fresh database)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


FTS_DDL = [
    # chunk keyword index (BM25 ranking comes with FTS5)
    """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        content, content='chunks', content_rowid='id', tokenize='porter unicode61'
    )""",
    """CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
        INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
        INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
    END""",
    # chat history search
    """CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts USING fts5(
        content, content='chat_messages', content_rowid='id', tokenize='porter unicode61'
    )""",
    """CREATE TRIGGER IF NOT EXISTS chat_messages_ai AFTER INSERT ON chat_messages BEGIN
        INSERT INTO chat_messages_fts(rowid, content) VALUES (new.id, new.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS chat_messages_ad AFTER DELETE ON chat_messages BEGIN
        INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content) VALUES ('delete', old.id, old.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS chat_messages_au AFTER UPDATE ON chat_messages BEGIN
        INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content) VALUES ('delete', old.id, old.content);
        INSERT INTO chat_messages_fts(rowid, content) VALUES (new.id, new.content);
    END""",
]


def init_db() -> None:
    """Create all tables and the FTS5 indexes (idempotent)."""
    from app import models  # noqa: F401  (register mappings)

    engine = get_engine()
    Base.metadata.create_all(engine)
    if engine.url.get_backend_name() == "sqlite":
        with engine.begin() as conn:
            for ddl in FTS_DDL:
                conn.execute(text(ddl))


def fts_available() -> bool:
    return get_engine().url.get_backend_name() == "sqlite"
