# Benchmark results

Last run: 2026-10-23 02:16 UTC · corpus: Database Design 2nd Edition (Watt Eng) CC-BY-4.0, Discrete Mathematics An Open Introduction 3e (Levin) CC-BY-SA-4.0, Open Data Structures (Morin) CC-BY-2.5, Operating Systems and Middleware (Hailperin) CC-BY-SA-3.0 (2016 chunks, 39 questions)

Embeddings: `BAAI/bge-small-en-v1.5` · vector store: `chroma`

## Retrieval (does the source passage, or another passage from the same page, come back?)

A question is a hit at k when the passage it was written from, or another passage from the same page of the same book, is among the top k results. MRR is the mean of 1/rank of the first such result (0 when none is in the top 5).

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | p50 latency |
|---|---|---|---|---|---|
| keyword | 0.62 | 0.79 | 0.87 | 0.72 | 13.7 ms |
| semantic | 0.51 | 0.77 | 0.87 | 0.65 | 38.4 ms |
| hybrid | 0.62 | 0.85 | 0.87 | 0.73 | 45.5 ms |

## Answer quality (answerer: `gemini/gemini-3.5-flash-lite`, judge: `groq/openai/gpt-oss-20b`)

| Metric | Value |
|---|---|
| Questions answered / judged / failed | 39 / 39 / 0 |
| Mean judge score (0-5) | 4.72 |
| Accuracy (score >= 4) | 0.923 |
| Answers with citations | 0.872 |
| p50 end-to-end latency | 1945 ms |

Reproduce: run `python scripts/fetch_open_notes.py` first (it downloads the books), then `python benchmarks/run_benchmark.py --answer-provider gemini --answer-model gemini-3.5-flash-lite --judge-provider groq --judge-model openai/gpt-oss-20b`.
Raw per-question output for this run: `benchmarks/results/20261023-022300.json`.
