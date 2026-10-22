"""End-to-end API flow with the fake LLM: notes -> chat -> quiz -> flashcards -> tools -> dashboard."""
import json


def test_health_and_config(client, auth):
    health = client.get("/api/v1/system/health", headers=auth).json()
    assert health["status"] == "ok" and health["fts"] is True
    assert health["embedding"]["provider"] == "hash"
    cfg = client.get("/api/v1/system/config").json()
    assert cfg["app_name"] == "AI Study Companion"


def test_auth_flow(client):
    resp = client.post("/api/v1/auth/register", json={"name": "Dup", "email": "dup@example.com", "password": "password123"})
    assert resp.status_code == 201
    assert client.post("/api/v1/auth/register", json={"name": "Dup", "email": "dup@example.com", "password": "password123"}).status_code == 409
    assert client.post("/api/v1/auth/login", json={"email": "dup@example.com", "password": "wrong-pass"}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": "dup@example.com", "password": "password123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["email"] == "dup@example.com"
    upd = client.patch("/api/v1/auth/me", headers=headers, json={"semester": 4, "answer_mode": "beginner"})
    assert upd.json()["profile"]["semester"] == 4
    assert client.get("/api/v1/auth/me").status_code == 401


def test_document_upload_and_search(client, auth, document):
    assert document["chunk_count"] >= 1 and document["status"] == "ready"
    listing = client.get("/api/v1/documents", headers=auth).json()
    assert any(d["id"] == document["id"] for d in listing)
    chunks = client.get(f"/api/v1/documents/{document['id']}/chunks", headers=auth).json()
    assert chunks and "Paging" in chunks[0]["content"]
    search = client.get("/api/v1/search", headers=auth, params={"q": "page fault", "mode": "hybrid"}).json()
    assert search["hits"] and search["hits"][0]["document_title"] == "OS Unit 4 - Memory Management"
    bad = client.post("/api/v1/documents", headers=auth, files={"file": ("virus.exe", b"MZ...", "application/octet-stream")})
    assert bad.status_code == 400
    stats = client.get("/api/v1/documents/stats", headers=auth).json()
    assert stats["ready"] >= 1


def test_privacy_other_user_cannot_see_documents(client, other_auth, document):
    assert client.get(f"/api/v1/documents/{document['id']}", headers=other_auth).status_code == 404
    assert client.get("/api/v1/documents", headers=other_auth).json() == []
    assert client.get("/api/v1/search", headers=other_auth, params={"q": "page table"}).json()["hits"] == []


def test_chat_sync_and_stream(client, auth, document, other_auth):
    session = client.post("/api/v1/chat/sessions", headers=auth, json={"answer_mode": "exam"}).json()
    resp = client.post(f"/api/v1/chat/sessions/{session['id']}/messages/sync", headers=auth, json={"content": "Explain paging and page tables"})
    assert resp.status_code == 200, resp.text
    assistant = resp.json()["assistant_message"]
    assert "[1]" in assistant["content"] and assistant["grounded"] is True
    assert assistant["sources"] and assistant["sources"][0]["document_id"] == document["id"]

    events = []
    with client.stream("POST", f"/api/v1/chat/sessions/{session['id']}/messages", headers=auth, json={"content": "What is a page fault?"}) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    types = [e["type"] for e in events]
    assert types[0] == "user_message" and "sources" in types and "token" in types and types[-1] == "done"
    done = events[-1]["message"]
    assert done["follow_ups"] == ["What is a TLB?", "Compare paging and segmentation", "What is thrashing?"]

    detail = client.get(f"/api/v1/chat/sessions/{session['id']}", headers=auth).json()
    assert len(detail["messages"]) == 4 and detail["title"] != "New chat"
    sessions = client.get("/api/v1/chat/sessions", headers=auth).json()
    assert sessions[0]["message_count"] == 4

    bm = client.post(f"/api/v1/chat/messages/{assistant['id']}/bookmark", headers=auth, json={"bookmarked": True}).json()
    assert bm["bookmarked"] is True
    assert client.get("/api/v1/chat/bookmarks", headers=auth).json()[0]["id"] == assistant["id"]
    hist = client.get("/api/v1/search/history", headers=auth, params={"q": "paging"}).json()
    assert hist and hist[0]["session_id"] == session["id"]

    assert client.get(f"/api/v1/chat/sessions/{session['id']}", headers=other_auth).status_code == 404
    assert client.post(f"/api/v1/chat/messages/{assistant['id']}/bookmark", headers=other_auth, json={"bookmarked": False}).status_code == 404


def test_quiz_generate_attempt_submit(client, auth, document):
    quiz = client.post("/api/v1/quizzes/generate", headers=auth, json={"topic": "Paging", "document_ids": [document["id"]], "count": 5}).json()
    assert quiz["question_count"] == 3 and all("answer_key" not in q for q in quiz["questions"])
    attempt = client.post(f"/api/v1/quizzes/{quiz['id']}/attempts", headers=auth).json()
    answers = {}
    for q in quiz["questions"]:
        if q["qtype"] == "mcq":
            answers[q["id"]] = "A"
        elif q["qtype"] == "true_false":
            answers[q["id"]] = "True"  # wrong on purpose
        else:
            answers[q["id"]] = "Pages are loaded on demand when referenced."
    result = client.post(f"/api/v1/quizzes/attempts/{attempt['id']}/submit", headers=auth, json={"answers": answers, "time_taken_sec": 90}).json()
    assert result["max_score"] == 4 and result["score"] == 2.5
    assert result["percent"] == 62.5
    assert result["topic_breakdown"]["Paging"]["correct"] == 1
    assert any(a["ai_feedback"] for a in result["answers"])
    assert result["questions"] and result["questions"][0]["answer_key"] == "A"
    summary = client.get("/api/v1/quizzes", headers=auth).json()
    assert summary[0]["attempt_count"] == 1 and summary[0]["best_percent"] == 62.5
    history = client.get("/api/v1/quizzes/attempts", headers=auth).json()
    assert history[0]["attempt_id"] == attempt["id"]


def test_flashcards_generate_and_review(client, auth, document):
    deck = client.post("/api/v1/flashcards/generate", headers=auth, json={"topic": "Paging", "document_ids": [document["id"]], "count": 6}).json()
    assert deck["card_count"] == 3 and deck["due_count"] == 3
    due = client.get("/api/v1/flashcards/due", headers=auth, params={"deck_id": deck["id"]}).json()
    assert len(due) == 3
    reviewed = client.post(f"/api/v1/flashcards/cards/{due[0]['id']}/review", headers=auth, json={"rating": "good"}).json()
    assert reviewed["interval_days"] == 1 and reviewed["repetitions"] == 1
    again = client.post(f"/api/v1/flashcards/cards/{due[1]['id']}/review", headers=auth, json={"rating": "again"}).json()
    assert again["lapses"] == 1
    stats = client.get("/api/v1/flashcards/stats", headers=auth).json()
    assert stats["total"] == 3 and stats["reviewed_today"] == 2
    manual = client.post(f"/api/v1/flashcards/decks/{deck['id']}/cards", headers=auth, json={"front": "TLB?", "back": "Translation lookaside buffer"})
    assert manual.status_code == 201
    assert client.get(f"/api/v1/flashcards/decks/{deck['id']}", headers=auth).json()["card_count"] == 4


def test_learning_tools(client, auth, document):
    summary = client.post("/api/v1/tools/summary", headers=auth, json={"topic": "Paging", "document_ids": [document["id"]]}).json()
    assert summary["kind"] == "summary" and "## Definition" in summary["content"]["markdown"]
    keywords = client.post("/api/v1/tools/keywords", headers=auth, json={"topic": "Paging"}).json()
    assert keywords["content"]["keywords"][0]["term"] == "Page table"
    cmap = client.post("/api/v1/tools/concept-map", headers=auth, json={"topic": "Paging", "style": "concept_map"}).json()
    graph = cmap["content"]
    assert {n["id"] for n in graph["nodes"]} == {"root", "pt", "frame"}
    assert all(e["source"] in {"root", "pt", "frame"} for e in graph["edges"]) and len(graph["edges"]) == 2
    subjects = client.get("/api/v1/syllabus/subjects", headers=auth).json()
    os_subject = next(s for s in subjects if s["code"] == "BCS401")
    plan = client.post("/api/v1/tools/study-plan", headers=auth, json={"exam_date": "2030-01-10", "subject_ids": [os_subject["id"]], "daily_minutes": 90})
    assert plan.status_code == 201, plan.text
    assert plan.json()["content"]["days"][0]["tasks"][0]["subject"] == "BCS401"
    artifacts = client.get("/api/v1/tools/artifacts", headers=auth, params={"kind": "summary"}).json()
    assert artifacts and artifacts[0]["id"] == summary["id"]


def test_syllabus_progress_and_dashboard(client, auth):
    subjects = client.get("/api/v1/syllabus/subjects", headers=auth).json()
    assert len(subjects) >= 9
    os_subject = next(s for s in subjects if s["code"] == "BCS401")
    detail = client.get(f"/api/v1/syllabus/subjects/{os_subject['id']}", headers=auth).json()
    assert len(detail["units"]) == 5
    topic_id = detail["units"][3]["topics"][0]["id"]
    assert client.post(f"/api/v1/syllabus/topics/{topic_id}/progress", headers=auth, json={"completed": True}).json()["completed"] is True
    detail = client.get(f"/api/v1/syllabus/subjects/{os_subject['id']}", headers=auth).json()
    assert detail["completed_count"] == 1

    dash = client.get("/api/v1/dashboard", headers=auth).json()
    assert dash["documents"]["ready"] >= 1
    assert dash["quizzes"]["attempts"] >= 1 and dash["quizzes"]["recent"]
    assert dash["streak"]["current"] >= 1 and dash["streak"]["active_today"] is True
    assert any(s["code"] == "BCS401" for s in dash["syllabus"]["subjects"])
    assert dash["recent_activity"] and dash["recommendations"]
    assert any(t["topic"] == "Paging" for t in dash["topic_accuracy"])


def test_settings_providers(client, auth):
    data = client.get("/api/v1/settings/providers", headers=auth).json()
    ids = {p["id"] for p in data["providers"]}
    assert {"groq", "gemini", "openai", "anthropic", "xai", "ollama"} <= ids
    assert data["current"]["provider"] == "groq" and data["current"]["key_source"] == "env"
    updated = client.put("/api/v1/settings/llm", headers=auth, json={"provider": "gemini", "model": "gemini-flash-latest", "api_key": "AIza-test-key-1234567890"}).json()
    assert updated["provider"] == "gemini" and updated["key_source"] == "user" and updated["key_masked"].startswith("AIza")
    test = client.post("/api/v1/settings/llm/test", headers=auth, json={}).json()
    assert test["ok"] is True and "Connection" in (test["reply"] or "") or test["ok"] is True
    models = client.post("/api/v1/settings/llm/models", headers=auth, json={"provider": "gemini"}).json()
    assert "fake-model" in models["models"]
    cleared = client.put("/api/v1/settings/llm", headers=auth, json={"provider": "groq"}).json()
    assert cleared["provider"] == "groq" and cleared["key_source"] == "env"


def test_video_resources_curated_without_network(client, auth):
    subjects = client.get("/api/v1/syllabus/subjects", headers=auth).json()
    os_subject = next(s for s in subjects if s["code"] == "BCS401")
    data = client.get("/api/v1/resources/videos", headers=auth, params={"subject_id": os_subject["id"], "topic": "Paging"}).json()
    assert data["query"].startswith("BCS401 Operating System Paging")
    assert data["curated"]["channels"] and data["curated"]["channels"][0]["search_url"].startswith("https://www.youtube.com/results")
    assert data["source"] == "none" and data["videos"] == []
