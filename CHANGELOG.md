# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-10-23

### Security
- With `LLM_PROVIDER=custom` (or Ollama) and an `LLM_API_KEY` in `.env`, a signed-in user could point the provider at a URL of their own and the server would send its key there. The server's key is now only ever sent to the server's own endpoint.

### Fixed
- Concept maps: nodes can be dragged, edges attach on the side the map flows along instead of looping round, the empty minimap is gone and labels are readable. "Copy as Mermaid" uses the direction shown on screen.
- A tutor answer whose citation was glued to a closing code fence rendered the rest of the answer as code. The fence is repaired before rendering, and the prompt asks the model not to do it.
- Pages open scrolled to the top after navigating.
- Chat-history results and the conversation list no longer show raw Markdown; long conversation titles end with an ellipsis.
- Flashcard review no longer flashes the next card's answer; deck titles wrap instead of being cut off.
- Summaries use the plain heading "60-second revision", which the model was mangling.
- Indexing a large document no longer stalls chat and search: embeddings are computed before the database write, and the local embedding model is locked per batch rather than per document.
- A failed or interrupted index leaves no half-built index behind. Re-indexing is refused while a document is still being indexed, and jobs cut short by a restart are marked as failed so they can be re-indexed.
- The sidebar's "chunks indexed" figure counts only your own passages, not every user's.

### Changed
- Removed GitHub Models, which GitHub retired on 30 July 2026. Accounts that saved it, and servers whose `.env` still says `LLM_PROVIDER=github`, fall back to Groq, and the server logs a warning at startup. **If your `.env` sets `LLM_PROVIDER=github`, change it.** A leftover `GITHUB_MODELS_TOKEN` is ignored.
- Provider labels: Cerebras now offers a trial credit rather than a free tier; the Gemini key hint mentions the new `AQ.` key format (both formats work); NVIDIA is described as rate-limited trial access.
- Rate limits: quiz grading counts one unit per answer the model grades, and uploads and re-indexing count against the per-user AI limit.
- Start scripts. On Windows, run `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1` (README updated); the flag bypasses the execution policy for that one run, so you no longer change the machine or user policy, and a plain `.\scripts\dev.ps1` still needs a policy that allows local scripts. Both scripts now write a random `SECRET_KEY` whenever `.env` holds the placeholder (this signs everyone out and clears keys saved in Settings once), check for Python 3.11+, retry an install that failed, and work in folders whose names contain spaces, apostrophes or brackets. `-SetupOnly` / `--setup-only` run the setup without starting the servers. `scripts/dev.sh` is executable and keeps LF endings on Windows checkouts.
- Quieter logs: the per-request INFO lines from the HTTP clients are gone.
- Benchmark reporting: metrics are rounded once (keyword and hybrid Hit@1 are 0.62, keyword Hit@3 is 0.79), every description says a hit is the source passage or another passage from the same page, `--render-only` re-renders `RESULTS.md` from a stored run, and the "Reproduce" line matches the published setup.
- Docs: Node.js 22.12 or newer; accurate wording about citations, free tiers and what each feature sends to the model provider.

### Added
- A narrated, full-length video tutorial, generated from `scripts/tutorial/` (narration, slides, real terminal output and the live app).

## [1.0.0] - 2026-10-23

First public release.

### Added
- AI tutor grounded in uploaded notes: hybrid retrieval (SQLite FTS5 BM25 fused with vector similarity via reciprocal-rank fusion), streamed answers with page-level citations, six answer styles, follow-up suggestions, bookmarks, feedback and full-text chat history.
- Notes library: PDF, DOCX, TXT and Markdown ingestion with page-aware chunking, local embeddings (fastembed `BAAI/bge-small-en-v1.5`) and ChromaDB indexing; keyword, semantic and hybrid search with highlighted snippets; per-page passage viewer.
- Quizzes: generation from topics, syllabus units or specific documents; MCQ, true/false and rubric-graded short answers; timers; per-topic accuracy and weak-topic detection; attempt history.
- Revision Studio: SM-2 spaced-repetition flashcards with keyboard review, exam summaries, keyword sheets, concept maps and flowcharts (React Flow, Mermaid export) and a day-by-day study plan built from the syllabus.
- AKTU B.Tech CSE syllabus (BCS301-303, 401-403, 501-503) with unit-wise topics, progress tracking and one-click quiz/flashcards/lectures per unit.
- Lecture finder (YouTube Data API or keyless yt-dlp search) with curated channels.
- Dashboard: accuracy by topic, score trend, 14-day activity, streaks, cards due, syllabus coverage and rule-based recommendations.
- Bring-your-own-model provider layer: Groq, Google Gemini, OpenAI, Anthropic Claude, xAI Grok, OpenRouter, Mistral, DeepSeek, Together, Cerebras, SambaNova, GitHub Models, Hugging Face, NVIDIA NIM, local Ollama and any OpenAI-compatible endpoint; per-account encrypted keys; live model catalogue and connection test in Settings.
- Open-textbook sample corpus (four Creative Commons books) and a reproducible retrieval/answer-quality benchmark.
- Offline test-suite, GitHub Actions CI, single-container Docker image and docker-compose.
