# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
