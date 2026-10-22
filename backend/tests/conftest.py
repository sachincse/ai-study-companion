"""Test configuration: isolated storage, deterministic embeddings, fake LLM."""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="asc-tests-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "SECRET_KEY": "test-secret-key",
        "STORAGE_DIR": str(_TMP / "storage"),
        "EMBEDDING_PROVIDER": "hash",
        "VECTOR_STORE": "memory",
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": "gsk_test_dummy",
        "ENABLE_YTDLP_FALLBACK": "false",
        "AI_RATE_LIMIT_PER_MINUTE": "1000",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import llm as llm_module  # noqa: E402
from app.services.llm.base import LLMResult  # noqa: E402


class FakeLLM:
    """Deterministic stand-in for a chat model. Answers depend on the prompt's intent."""

    id = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    @staticmethod
    def _last_user(messages: list[dict]) -> str:
        return next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    def _answer(self, messages: list[dict]) -> str:
        user = self._last_user(messages)
        low = user.lower()
        if "sources from my notes" in low:
            return "**Paging** divides memory into fixed-size pages [1]. A page table maps pages to frames [1]. This avoids external fragmentation."
        if "no relevant passages" in low:
            return "I could not find this in your notes. From general knowledge: a semaphore is a synchronisation primitive (general knowledge, not from your notes)."
        return "Here is an explanation of your question."

    def _json(self, messages: list[dict]) -> str:
        user = self._last_user(messages)
        low = user.lower()
        if "revision plan" in low:
            return json.dumps({"title": "Plan", "days": [{"date": "2030-01-01", "focus": "OS unit 4", "tasks": [{"title": "Read paging notes", "subject": "BCS401", "type": "read", "minutes": 45}]}], "tips": ["Sleep well"]})
        if "practice quiz" in low:
            return json.dumps(
                {
                    "title": "Paging quiz",
                    "questions": [
                        {"type": "mcq", "question": "What does a page table map?", "options": ["Pages to frames", "Files to disks", "Threads to cores", "Users to roles"], "answer": "A", "explanation": "Page tables translate page numbers to frame numbers.", "topic": "Paging", "marks": 1, "source": 1},
                        {"type": "true_false", "question": "Paging suffers from external fragmentation.", "answer": "False", "explanation": "Fixed-size pages avoid external fragmentation.", "topic": "Paging", "marks": 1, "source": 1},
                        {"type": "short_answer", "question": "Explain demand paging.", "answer": "Pages are loaded only when referenced, causing a page fault on first access.", "rubric": ["loaded on demand", "page fault"], "explanation": "Lazy loading of pages.", "topic": "Virtual memory", "marks": 2, "source": 1},
                    ],
                }
            )
        if "flashcards" in low and "create" in low:
            return json.dumps({"title": "Paging cards", "cards": [{"front": "What is a page?", "back": "A fixed-size block of logical memory.", "hint": "fixed size", "topic": "Paging", "source": 1}, {"front": "What is a frame?", "back": "A fixed-size block of physical memory.", "topic": "Paging", "source": 1}, {"front": "What causes a page fault?", "back": "Accessing a page not currently in memory.", "topic": "Virtual memory"}]})
        if "exam-relevant keywords" in low:
            return json.dumps({"title": "Keywords", "keywords": [{"term": "Page table", "definition": "Maps pages to frames.", "importance": "high", "source": 1}, {"term": "Frame", "definition": "Physical memory block.", "importance": "medium"}]})
        if "knowledge graph" in low:
            return json.dumps({"title": "Paging", "nodes": [{"id": "root", "label": "Paging", "type": "root"}, {"id": "pt", "label": "Page table", "type": "concept"}, {"id": "frame", "label": "Frame", "type": "concept"}], "edges": [{"source": "root", "target": "pt", "label": "uses"}, {"source": "pt", "target": "frame", "label": "maps to"}, {"source": "ghost", "target": "pt"}]})
        if "revision summary" in low:
            return json.dumps({"title": "Paging summary", "markdown": "## Definition\nPaging splits memory into pages.\n## Core concepts\n- page table\n## Important formulas / algorithms\nNone\n## Worked example\n...\n## Exam keywords\n**page**, **frame**\n## Common mistakes\n- confusing pages and frames\n## 60-second revision\n- pages map to frames"})
        if "examiner" in " ".join(m["content"].lower() for m in messages if m["role"] == "system"):
            return json.dumps({"marks": 1.5, "feedback": "Mentioned demand loading; missed page faults."})
        if "follow-up" in low:
            return json.dumps({"questions": ["What is a TLB?", "Compare paging and segmentation", "What is thrashing?"]})
        return json.dumps({"ok": True})

    async def stream(self, messages, *, temperature=0.3, max_tokens=2048) -> AsyncIterator[str]:  # noqa: ANN001
        self.calls.append(messages)
        for word in self._answer(messages).split(" "):
            yield word + " "

    async def complete(self, messages, *, temperature=0.3, max_tokens=2048, json_mode=False) -> LLMResult:  # noqa: ANN001
        self.calls.append(messages)
        text = self._json(messages) if json_mode else self._answer(messages)
        return LLMResult(text=text, provider=self.id, model=self.model, usage={"total_tokens": 42})

    async def list_models(self) -> list[str]:
        return ["fake-model", "fake-model-mini"]


@pytest.fixture(scope="session")
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture(scope="session", autouse=True)
def _patch_llm(fake_llm: FakeLLM):
    original = llm_module.build_provider
    llm_module.build_provider = lambda resolved: fake_llm  # type: ignore[assignment]
    import app.api.v1.misc as misc

    misc.build_provider = lambda resolved: fake_llm  # type: ignore[assignment]
    yield
    llm_module.build_provider = original
    misc.build_provider = original


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def register(client: TestClient, email: str, name: str = "Test Student", password: str = "password123") -> dict:
    resp = client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture(scope="session")
def auth(client: TestClient) -> dict:
    return register(client, "asha@example.com", "Asha")


@pytest.fixture(scope="session")
def other_auth(client: TestClient) -> dict:
    return register(client, "ravi@example.com", "Ravi")


SAMPLE_NOTES = """Unit 4: Memory Management

Paging is a memory management scheme that eliminates the need for contiguous allocation of physical memory.
The logical address space is divided into fixed-size blocks called pages, and physical memory is divided into
blocks of the same size called frames. A page table maps each page number to a frame number. Because pages
and frames are the same size, paging does not suffer from external fragmentation, although internal
fragmentation can occur in the last page of a process.

Demand paging loads a page into memory only when it is referenced. A reference to a page that is not in
memory raises a page fault; the operating system then finds a free frame, reads the page from disk and
updates the page table. Page replacement algorithms such as FIFO, optimal and LRU decide which frame to
free when memory is full. Thrashing occurs when a process spends more time paging than executing.

Segmentation divides a program into logical segments such as code, data and stack. Each segment has a base
and a limit. Segmentation supports sharing and protection but suffers from external fragmentation.
"""


@pytest.fixture(scope="session")
def document(client: TestClient, auth: dict) -> dict:
    resp = client.post(
        "/api/v1/documents",
        headers=auth,
        files={"file": ("os_unit4_notes.txt", SAMPLE_NOTES.encode("utf-8"), "text/plain")},
        data={"title": "OS Unit 4 - Memory Management"},
    )
    assert resp.status_code == 202, resp.text
    doc = client.get(f"/api/v1/documents/{resp.json()['id']}", headers=auth).json()
    assert doc["status"] == "ready", doc
    return doc
