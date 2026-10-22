# Contributing

Thanks for helping make AI Study Companion better for students.

## Development setup

```bash
git clone https://github.com/sachincse/ai-study-companion.git
cd ai-study-companion
cp .env.example .env          # add at least one provider key, or use Ollama

# backend
cd backend
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173, proxies /api to :8000
```

## Running checks

```bash
cd backend && ruff check app tests && pytest -q
cd frontend && npm run lint && npm run build
```

The backend tests run fully offline: they use a deterministic hashing embedder,
an in-memory vector store and a fake LLM (see `backend/tests/conftest.py`).
If you touch retrieval or generation, also run the live benchmark
(`benchmarks/run_benchmark.py`) and paste the before/after numbers in the PR.

## Where things live

| Area | Path |
|---|---|
| API routes | `backend/app/api/v1/` |
| Business logic | `backend/app/services/` |
| LLM providers | `backend/app/services/llm/` (add a provider = one entry in `registry.py`) |
| ORM models | `backend/app/models/tables.py` |
| Syllabus data | `data/syllabus/*.yaml` (one file per subject) |
| Frontend pages | `frontend/src/pages/` |
| Shared UI | `frontend/src/components/` |

## Adding a subject to the syllabus

Create `data/syllabus/<CODE>.yaml` following the existing files (code, name,
semester, units with topics). It is seeded on the next server start; existing
progress is preserved because topics are matched by unit number + name.

## Adding an LLM provider

If it speaks the OpenAI chat-completions protocol, add a `ProviderSpec` in
`backend/app/services/llm/registry.py` and an env var in `config.py` /
`.env.example`. Anything else needs a small class implementing `stream`,
`complete` and `list_models` (see `anthropic_provider.py`).

## Pull requests

- Keep PRs focused; include tests for backend changes.
- Run the formatter/linters above.
- Describe how you verified the change (screenshots for UI).
- Never commit `.env`, `storage/` or downloaded textbooks.
