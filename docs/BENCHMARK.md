# Benchmarking the RAG pipeline

The benchmark runs on **real, openly licensed textbooks** (see
`data/sample_notes/SOURCES.md`) rather than synthetic text, and it exercises the
exact service code the API uses (no HTTP, no mocks).

## What is measured

**Retrieval** - for each evaluation question we know which passage it was written
from (document, page, text prefix). We run keyword-only (SQLite FTS5 / BM25),
semantic-only (vector cosine) and hybrid (Reciprocal Rank Fusion) search and
report Hit@1, Hit@3, Hit@5, MRR and median latency.

**Answer quality** - the full RAG pipeline answers each question with the
configured chat model. A second model acts as judge and scores correctness
0-5 against the reference answer (LLM-as-judge). Pass `--judge-provider` /
`--judge-model` to keep the judge different from the answerer (the published
numbers use Groq to answer and Gemini to judge). We also report the share of
answers that cite sources and end-to-end latency.

## How to run

```bash
python scripts/fetch_open_notes.py                      # download the books (once)
python benchmarks/build_eval_set.py --per-book 12       # writes benchmarks/eval_set.json (committed)
python benchmarks/run_benchmark.py --retrieval-only     # no model calls needed
python benchmarks/run_benchmark.py --answer-provider groq --judge-provider gemini --judge-model gemini-3.5-flash
python benchmarks/sync_readme.py                          # copies the tables into README.md
```

The benchmark uses its own storage directory (`storage/benchmark`) and user, so
it never touches real accounts. Results are written to `benchmarks/results/` and
summarised in `benchmarks/RESULTS.md`.

## Caveats

- The evaluation questions are model-written (then spot-checked); they measure
  "can the system find and explain what the book says", not exam difficulty.
- LLM-as-judge scores are indicative, not ground truth. Use the same judge when
  comparing two configurations.
- Retrieval numbers depend on the embedding model and chunk size; re-run after
  changing either.
