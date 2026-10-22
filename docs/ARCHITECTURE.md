# Architecture

AI Study Companion is a single FastAPI service plus a React single-page app.
Everything a student creates (documents, passages, vectors, chats, quizzes,
cards, artifacts) is scoped to their account.

```mermaid
flowchart TB
  subgraph Browser["React 19 + TypeScript (Vite, Tailwind, React Flow, Recharts)"]
    UI[Dashboard · Tutor · Notes · Quizzes · Revision Studio · Syllabus · Lectures · History · Settings]
  end
  UI -- "REST / JSON + Server-Sent Events" --> API

  subgraph API["FastAPI backend (async)"]
    AUTH[auth\nJWT · bcrypt]
    DOCS[document service\nparse → chunk → embed → index]
    RAG[rag service\nhybrid retrieval → prompt → stream]
    QUIZ[quiz & grading]
    CARDS[flashcards · SM-2]
    TOOLS[summaries · keywords · concept maps · study plans]
    DASH[dashboard analytics]
    VID[lecture finder]
  end

  DOCS --> SQL[(SQLite + FTS5\nmetadata, passages, chats, attempts)]
  DOCS --> VEC[(ChromaDB\ncosine HNSW index)]
  RAG --> SQL
  RAG --> VEC
  RAG --> LLM
  QUIZ --> LLM
  CARDS --> LLM
  TOOLS --> LLM
  VID --> YT[YouTube Data API / yt-dlp / curated channels]

  subgraph LLM["Provider layer"]
    OA[OpenAI-compatible client\nOpenAI · Groq · Gemini · xAI · OpenRouter · Mistral · DeepSeek · Together · Cerebras · SambaNova · GitHub Models · Hugging Face · NVIDIA · Ollama · custom]
    AN[Anthropic SDK\nClaude]
  end
  EMB[Embeddings\nfastembed bge-small (local) · OpenAI · Gemini · Ollama] --> VEC
```

## Request flow: asking the tutor

1. `POST /api/v1/chat/sessions/{id}/messages` validates the user, rate-limits AI calls and resolves which model to use (user settings -> `.env`).
2. **Retrieval** (`services/search_service.py`): the question is run through SQLite FTS5 (BM25, porter stemming) and the vector index (cosine similarity of the query embedding), each scoped to `user_id` and optional document filters. Rankings are fused with Reciprocal Rank Fusion (k = 60) and the top-k passages are hydrated with their page numbers and headings.
3. **Prompting** (`services/rag_service.py`): the system prompt sets the tutor persona and answer style (exam / beginner / detailed / short / steps / practice), the sources are numbered `[1]..[n]`, recent history is trimmed to a character budget, and document text is explicitly marked as untrusted data (prompt-injection guard).
4. **Streaming**: tokens are streamed as SSE events (`user_message`, `sources`, `token`, `done`, `error`). `<think>` blocks from reasoning models are filtered out on the fly.
5. **Persistence**: the assistant message, its sources (chunk, document, page, score, snippet) and three follow-up questions are saved; FTS5 triggers index the message for history search; a study-activity row feeds the dashboard streak.

## Ingestion

`parse_bytes` (pypdf / python-docx / text) -> `chunk_pages` (recursive character splitter, ~2000 chars = ~500 tokens, 200 overlap, page tracking, heading detection) -> embeddings in batches -> Chroma upsert with `{user_id, document_id, page_no}` metadata -> `chunks` rows (FTS5 trigger indexes them). Documents go `uploaded -> processing -> ready | failed`; failures carry a human-readable reason (e.g. scanned PDF without text).

## Quizzes and grading

Questions are generated as JSON from retrieved passages and normalised (option letters, true/false, rubric points). Grading is deterministic for MCQ and true/false. Short answers are graded by the model against the stored rubric and the source passage, returning marks and feedback; if the model is unavailable, a keyword-coverage grader steps in and says so. Attempts store every answer so the dashboard can compute accuracy per topic and surface weak topics.

## Flashcards

SM-2 (`services/sm2.py`): quality 0-5 from Again/Hard/Good/Easy, ease factor floor 1.3, intervals 1 -> 6 -> interval x ease, lapses reset repetitions and reschedule in 10 minutes. The review queue is simply `due_at <= now`.

## Data model

See `backend/app/models/tables.py`. Main tables: users, user_settings, subjects, topics, topic_progress, documents, chunks (+chunks_fts), chat_sessions, chat_messages (+chat_messages_fts), message_sources, quizzes, questions, quiz_attempts, attempt_answers, flashcard_decks, flashcards, card_reviews, generated_artifacts, study_activity.

## Security notes

- Every query filters by `user_id`; the test-suite includes cross-account access tests.
- API keys entered in Settings are encrypted at rest (Fernet, key derived from `SECRET_KEY`) and only ever masked in responses.
- Uploads are validated by extension and size (streamed with a cap plus a request-body limit); file names are sanitised; files live under `storage/uploads/user_<id>/`.
- Hosted providers are pinned to their registry endpoints; only Ollama and the custom provider accept a user-supplied base URL, which is validated (http/https only, cloud metadata hosts refused).
- Provider keys are only ever sent in request bodies, never in query strings, so they stay out of access logs.
- AI endpoints have a per-user sliding-window rate limit.

## Why these choices

- **SQLite + FTS5 + Chroma** keep the whole product runnable on a laptop with zero infrastructure. The vector store sits behind an interface; `DATABASE_URL` is accepted for other SQL databases, but only SQLite is tested and the FTS5 keyword index is SQLite-specific (other databases fall back to a LIKE scan).
- **Local embeddings by default** (fastembed, ONNX) mean notes never leave the machine for indexing and retrieval works offline; only generation needs a model API (or Ollama for fully offline use).
- **One chat protocol** (OpenAI-compatible) covers nearly every provider, so adding one is a registry entry; Anthropic uses its official SDK for streaming and refusal fallbacks.
