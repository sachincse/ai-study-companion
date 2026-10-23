# Benchmark results

Last run: 2026-10-23 02:16 UTC · corpus: Database Design 2nd Edition (Watt Eng) CC-BY-4.0, Discrete Mathematics An Open Introduction 3e (Levin) CC-BY-SA-4.0, Open Data Structures (Morin) CC-BY-2.5, Operating Systems and Middleware (Hailperin) CC-BY-SA-3.0 (2016 chunks, 39 questions)

Embeddings: `BAAI/bge-small-en-v1.5` · vector store: `chroma`

## Retrieval (does the ground-truth passage come back?)

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | p50 latency |
|---|---|---|---|---|---|
| keyword | 0.61 | 0.80 | 0.87 | 0.72 | 13.7 ms |
| semantic | 0.51 | 0.77 | 0.87 | 0.65 | 38.4 ms |
| hybrid | 0.61 | 0.85 | 0.87 | 0.73 | 45.5 ms |

## Answer quality (answerer: `gemini/gemini-3.5-flash-lite`, judge: `groq/openai/gpt-oss-20b`)

| Metric | Value |
|---|---|
| Questions answered / judged / failed | 39 / 39 / 0 |
| Mean judge score (0-5) | 4.72 |
| Accuracy (score >= 4) | 0.923 |
| Answers with citations | 0.872 |
| p50 end-to-end latency | 1945 ms |

Reproduce: `python scripts/fetch_open_notes.py && python benchmarks/run_benchmark.py`.
Raw per-question output lives in `benchmarks/results/`.
