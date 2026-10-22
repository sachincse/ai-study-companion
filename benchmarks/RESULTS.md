# Benchmark results

Last run: 2026-10-22 22:46 UTC · corpus: Database Design 2nd Edition (Watt Eng) CC-BY-4.0, Discrete Mathematics An Open Introduction 3e (Levin) CC-BY-SA-4.0, Open Data Structures (Morin) CC-BY-2.5, Operating Systems and Middleware (Hailperin) CC-BY-SA-3.0 (2016 chunks, 39 questions)

Embeddings: `BAAI/bge-small-en-v1.5` · vector store: `chroma`

## Retrieval (does the ground-truth passage come back?)

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | p50 latency |
|---|---|---|---|---|---|
| keyword | 0.61 | 0.80 | 0.87 | 0.72 | 25.3 ms |
| semantic | 0.51 | 0.77 | 0.87 | 0.65 | 41.3 ms |
| hybrid | 0.61 | 0.85 | 0.87 | 0.73 | 52.5 ms |

## Answer quality (answerer: `groq/openai/gpt-oss-120b`, judge: `gemini/gemini-3.5-flash`)

| Metric | Value |
|---|---|
| Questions answered / judged | 8 / 8 |
| Mean judge score (0-5) | 4.62 |
| Accuracy (score >= 4) | 0.875 |
| Answers with citations | 0.375 |
| p50 end-to-end latency | 8695.0 ms |

Reproduce: `python scripts/fetch_open_notes.py && python benchmarks/run_benchmark.py`.
Raw per-question output lives in `benchmarks/results/`.
