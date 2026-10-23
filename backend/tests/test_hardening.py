"""Regression tests for the issues found in the pre-release audit."""
from pathlib import Path

import pytest

from app.core.config import ROOT_DIR, Settings
from app.core.security import PasswordTooLongError, hash_password
from app.schemas.learning import QuestionPublic, QuestionRevealed
from app.services.chunking import ChunkingConfig, PageText, chunk_pages, detect_heading
from app.services.llm import LLMError, validate_base_url
from app.services.quiz_service import _normalise_question, grade_objective
from app.services.search_service import make_snippet


def test_env_example_loads(monkeypatch):
    """The shipped .env.example must produce a valid Settings object (CORS list, comments, blanks)."""
    for key in ("CORS_ORIGINS", "SECRET_KEY", "APP_ENV", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=ROOT_DIR / ".env.example")
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"]
    assert settings.groq_api_key in (None, "")
    assert settings.app_env == "development"


def test_cors_accepts_comma_and_json_forms(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings(_env_file=None).cors_origins == ["http://a.test", "http://b.test"]
    monkeypatch.setenv("CORS_ORIGINS", '["http://c.test"]')
    assert Settings(_env_file=None).cors_origins == ["http://c.test"]


def test_production_refuses_placeholder_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "change-me-in-production")
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None)
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    assert Settings(_env_file=None).is_production


def test_password_byte_limit(client):
    with pytest.raises(PasswordTooLongError):
        hash_password("p" * 73)
    resp = client.post("/api/v1/auth/register", json={"name": "Long Pass", "email": "longpass@example.com", "password": "p" * 100})
    assert resp.status_code == 422
    resp = client.post("/api/v1/auth/register", json={"name": "Hindi", "email": "hindi@example.com", "password": "क" * 30})
    assert resp.status_code == 422  # 90 bytes


def test_base_url_validation_blocks_metadata_endpoints():
    assert validate_base_url("http://localhost:11434/v1/", "ollama") == "http://localhost:11434/v1"
    for bad in ("ftp://x", "http://169.254.169.254/latest", "http://metadata.google.internal/", "localhost:1234"):
        with pytest.raises(LLMError):
            validate_base_url(bad, "custom")


def test_hosted_provider_base_url_is_pinned(client, auth):
    resp = client.put("/api/v1/settings/llm", headers=auth, json={"provider": "groq", "base_url": "http://evil.test/v1"})
    assert resp.status_code == 200
    assert resp.json()["base_url"] == "https://api.groq.com/openai/v1"
    resp = client.put("/api/v1/settings/llm", headers=auth, json={"provider": "custom", "base_url": "http://169.254.169.254/v1"})
    assert resp.status_code == 400
    assert client.put("/api/v1/settings/llm", headers=auth, json={"provider": "nope"}).status_code == 422
    client.put("/api/v1/settings/llm", headers=auth, json={"provider": "groq"})


def test_model_listing_uses_post_body(client, auth):
    assert client.get("/api/v1/settings/llm/models", headers=auth, params={"provider": "groq"}).status_code in (404, 405)
    assert client.get("/api/v1/does-not-exist", headers=auth).status_code == 404  # the SPA catch-all must not answer API paths
    resp = client.post("/api/v1/settings/llm/models", headers=auth, json={"provider": "groq", "api_key": "gsk_secret"})
    assert resp.status_code == 200 and "fake-model" in resp.json()["models"]


def test_health_hides_configuration_without_auth(client, auth):
    anon = client.get("/api/v1/system/health").json()
    assert set(anon) == {"status", "version", "rag_engine"}
    full = client.get("/api/v1/system/health", headers=auth).json()
    assert "providers_ready" in full and "vector_store" in full


def test_health_counts_only_the_callers_passages(client, auth, other_auth, document):
    """The sidebar's 'chunks indexed' figure must not reveal how much other users have uploaded."""
    mine = client.get("/api/v1/system/health", headers=auth).json()["vector_store"]["count"]
    theirs = client.get("/api/v1/system/health", headers=other_auth).json()["vector_store"]["count"]
    own_docs = client.get("/api/v1/documents", headers=other_auth).json()
    assert mine >= document["chunk_count"] > 0
    assert theirs == sum(d["chunk_count"] for d in own_docs)


def test_short_answer_rubric_hidden_until_revealed():
    row = {"id": 1, "position": 0, "qtype": "short_answer", "prompt": "Explain paging", "options": ["page table", "frames"], "topic": None, "marks": 3, "source_page": None, "answer_key": "x", "explanation": None}
    assert QuestionPublic.model_validate(row).options is None
    assert QuestionRevealed.model_validate(row).options == ["page table", "frames"]
    mcq = {**row, "qtype": "mcq", "options": ["A", "B"]}
    assert QuestionPublic.model_validate(mcq).options == ["A", "B"]


def test_question_normalisation_rejects_missing_answers():
    assert _normalise_question({"type": "mcq", "question": "Which one is right?", "options": ["a", "b", "c", "d"]}, []) is None
    assert _normalise_question({"type": "mcq", "question": "Which one is right?", "options": ["a", "b", "c", "d"], "answer": ""}, []) is None
    ok = _normalise_question({"type": "mcq", "question": "Which one is right?", "options": ["a", "b", "c", "d"], "answer": "C"}, [])
    assert ok and ok["answer_key"] == "C"


class _Q:
    def __init__(self, qtype, options, answer_key, marks=1):
        self.qtype, self.options, self.answer_key, self.marks = qtype, options, answer_key, marks


def test_grade_objective_handles_text_answers():
    q = _Q("mcq", ["Array", "Binary tree", "Cache", "Deque"], "B")
    assert grade_objective(q, "B") == (True, 1.0)
    assert grade_objective(q, "b)") == (True, 1.0)
    assert grade_objective(q, "Binary tree") == (True, 1.0)
    assert grade_objective(q, "Array") == (False, 0.0)  # option text starting with 'A' must not be read as letter A->wrong anyway
    assert grade_objective(q, "Cache")[0] is False
    tf = _Q("true_false", ["True", "False"], "False")
    assert grade_objective(tf, "false")[0] is True
    assert grade_objective(tf, "F")[0] is True
    assert grade_objective(tf, "fantastic")[0] is False
    assert grade_objective(tf, "")[0] is False


def test_chunk_page_attribution_uses_body_start():
    pages = [PageText(page_no=i, text=(f"P{i} " * 100).strip()) for i in (1, 2, 3)]
    cfg = ChunkingConfig(chunk_size=700, chunk_overlap=50)
    chunks = chunk_pages(pages, cfg)
    assert len(chunks) == 2
    assert chunks[0].page_no == 1 and chunks[1].page_no == 3  # second chunk's body is page 3 text even though it starts with page-2 overlap
    assert chunks[1].content.endswith("P3")
    assert all(len(c.content) <= cfg.chunk_size for c in chunks)
    # the overlap is separated from the body, never glued to its first word
    assert "P2\nP3" in chunks[1].content and "P2P3" not in chunks[1].content


def test_heading_detection_is_case_sensitive_for_caps_lines():
    assert detect_heading("this is just a lowercase line\nmore") is None
    assert detect_heading("MEMORY MANAGEMENT\nParagraph") == "MEMORY MANAGEMENT"
    assert detect_heading("Unit 2 Processes\ntext") == "Unit 2 Processes"


def test_make_snippet_marks_terms():
    text = "Paging divides memory into fixed-size pages. A page table maps pages to frames and a page fault loads them."
    snippet = make_snippet(text, ["page", "fault"], width=120)
    assert "[[page" in snippet.lower() and "[[fault" in snippet.lower()
    assert make_snippet("no terms here at all", ["xyz"], width=10).startswith("no terms")


def test_search_rejects_non_numeric_document_ids(client, auth):
    assert client.get("/api/v1/search", headers=auth, params={"q": "paging", "document_ids": "1,abc"}).status_code == 400
    assert client.get("/api/v1/search", headers=auth, params={"q": "paging", "document_ids": "٣"}).status_code == 400


def test_profile_semester_can_be_cleared(client, auth):
    assert client.patch("/api/v1/auth/me", headers=auth, json={"semester": 3}).json()["profile"]["semester"] == 3
    assert client.patch("/api/v1/auth/me", headers=auth, json={"semester": None}).json()["profile"]["semester"] is None


def test_upload_too_large_is_rejected(client, auth, monkeypatch):
    from app.core import config

    big = b"x" * (config.get_settings().max_upload_mb * 1024 * 1024 + 10)
    resp = client.post("/api/v1/documents", headers=auth, files={"file": ("big.txt", big, "text/plain")})
    assert resp.status_code == 413


def test_dashboard_timestamps_have_timezone(client, auth, document):
    dash = client.get("/api/v1/dashboard", headers=auth).json()
    assert dash["recent_activity"] and dash["recent_activity"][0]["created_at"].endswith("Z")
    for a in dash["quizzes"]["recent"]:
        assert a["submitted_at"].endswith("Z")


def test_demo_raw_recordings_not_tracked():
    assert not any(Path(ROOT_DIR, "docs", "demo", ".raw").glob("*.webm")) or True  # presence is fine; git-ignore is checked below
    gitignore = Path(ROOT_DIR, ".gitignore").read_text(encoding="utf-8")
    assert "docs/demo/.raw/" in gitignore


def _user_and_db(client, email):
    from app.core.database import get_session_factory
    from app.models import User
    from tests.conftest import register

    headers = register(client, email)
    db = get_session_factory()()
    return headers, db, db.query(User).filter(User.email == email).one()


def test_retired_provider_falls_back_to_server_default(client):
    """A provider saved before it was retired (GitHub Models) must not lock the account out of Settings,
    and none of its saved key, model or endpoint may leak into the provider used instead."""
    from app.core.security import encrypt_secret
    from app.models import UserSettings

    headers, db, user = _user_and_db(client, "retired-provider@example.com")
    with db:
        row = db.query(UserSettings).filter(UserSettings.user_id == user.id).one_or_none() or UserSettings(user_id=user.id)
        row.llm_provider, row.llm_model = "github", "openai/gpt-4.1-mini"
        row.llm_api_key_enc = encrypt_secret("github_pat_retired")
        row.llm_base_url = "https://models.github.ai/inference"
        db.add(row)
        db.commit()
    resp = client.get("/api/v1/settings/providers", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current"]["provider"] == "groq" and body["current"]["key_source"] == "env"
    assert body["current"]["model"] != "openai/gpt-4.1-mini"
    assert all(p["id"] != "github" for p in body["providers"])


def test_retired_server_default_falls_back(client, monkeypatch):
    """LLM_PROVIDER=github (documented in 1.0.0) must not break every account after upgrading."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_provider", "github")
    headers, db, _user = _user_and_db(client, "retired-env@example.com")
    db.close()
    resp = client.get("/api/v1/settings/providers", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["current"]["provider"] == "groq"


def test_server_key_never_sent_to_a_callers_endpoint(client, monkeypatch):
    """With LLM_PROVIDER=custom and a server LLM_API_KEY, a user who points 'custom' at another URL gets no key."""
    from app.core.config import get_settings
    from app.services.llm import resolve_llm

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "custom")
    monkeypatch.setattr(settings, "llm_base_url", "http://llm.internal:8080/v1")
    monkeypatch.setattr(settings, "llm_api_key", "server-secret")
    _headers, db, user = _user_and_db(client, "custom-endpoint@example.com")
    with db:
        theirs = resolve_llm(db, user, override={"provider": "custom", "base_url": "https://collector.example/v1"})
        assert theirs.api_key is None and theirs.base_url == "https://collector.example/v1"
        ours = resolve_llm(db, user, override={"provider": "custom"})
        assert ours.api_key == "server-secret" and ours.base_url == "http://llm.internal:8080/v1"
        same = resolve_llm(db, user, override={"provider": "custom", "base_url": " http://llm.internal:8080/v1/ "})
        assert same.api_key == "server-secret"
        own_key = resolve_llm(db, user, override={"provider": "custom", "base_url": "https://collector.example/v1", "api_key": "users-own"})
        assert own_key.api_key == "users-own"


def test_sdk_request_loggers_are_quiet(client):
    import logging

    for name in ("httpx", "httpx2"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING, name


def test_rate_limiter_counts_cost():
    from fastapi import HTTPException

    from app.core.deps import SlidingWindowLimiter

    limiter = SlidingWindowLimiter()
    limiter.check(1, limit=5, cost=3)
    with pytest.raises(HTTPException):
        limiter.check(1, limit=5, cost=3)
    limiter.check(2, limit=5, cost=50)  # bigger than the budget: allowed once, when the window is empty
    with pytest.raises(HTTPException):
        limiter.check(2, limit=5)


def test_reindex_refused_while_indexing_and_failed_documents_keep_no_passages(client, auth, document):
    from app.core.database import get_session_factory
    from app.models import Chunk, Document
    from app.services import document_service

    resp = client.post("/api/v1/documents", headers=auth, files={"file": ("extra.txt", b"Paging maps virtual pages to frames. " * 40, "text/plain")})
    assert resp.status_code == 202, resp.text
    doc_id = resp.json()["id"]
    with get_session_factory()() as db:
        doc = db.get(Document, doc_id)
        assert doc.status == "ready" and doc.chunk_count > 0
        doc.status = "processing"
        db.commit()
    assert client.post(f"/api/v1/documents/{doc_id}/reindex", headers=auth).status_code == 409
    with get_session_factory()() as db:
        document_service._mark_failed(db, doc_id, "Indexing failed: test")
        assert db.query(Chunk).filter(Chunk.document_id == doc_id).count() == 0
        assert db.get(Document, doc_id).status == "failed"
    assert client.post(f"/api/v1/documents/{doc_id}/reindex", headers=auth).status_code == 202
