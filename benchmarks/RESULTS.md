# Benchmark results

Last run: 2026-10-22 21:29 UTC · corpus: Database Design 2nd Edition (Watt Eng) CC-BY-4.0, Discrete Mathematics An Open Introduction 3e (Levin) CC-BY-SA-4.0, Open Data Structures (Morin) CC-BY-2.5, Operating Systems and Middleware (Hailperin) CC-BY-SA-3.0 (2016 chunks, 39 questions)

Embeddings: `BAAI/bge-small-en-v1.5` · vector store: `chroma`

## Retrieval (does the ground-truth passage come back?)

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | p50 latency |
|---|---|---|---|---|---|
| keyword | 0.61 | 0.80 | 0.87 | 0.72 | 12.3 ms |
| semantic | 0.51 | 0.77 | 0.87 | 0.65 | 36.2 ms |
| hybrid | 0.61 | 0.85 | 0.87 | 0.73 | 49.2 ms |

Reproduce: `python scripts/fetch_open_notes.py && python benchmarks/run_benchmark.py`.
Raw per-question output lives in `benchmarks/results/`.
