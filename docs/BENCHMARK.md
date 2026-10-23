# Benchmarking the RAG pipeline

The benchmark runs on **real, openly licensed textbooks** (see
`data/sample_notes/SOURCES.md`) rather than synthetic text, and it exercises the
exact service code the API uses (no HTTP, no mocks).

## What is measured

**Retrieval** - for each evaluation question we know which passage it was written
from (document, page, text prefix). We run keyword-only (SQLite FTS5 / BM25),
semantic-only (vector cosine) and hybrid (Reciprocal Rank Fusion) search and
report Hit@1, Hit@3, Hit@5, MRR and median latency. A result counts as a hit when
it is that source passage **or any other passage from the same page of the same
book**, so the numbers say whether the right page comes back (the page is what a
citation points to), not only the exact passage. MRR uses the rank of the first
hit in the top 5 and counts 0 when there is none.

**Answer quality** - the full RAG pipeline answers each question with the
configured chat model. A second model acts as judge and scores correctness
0-5 against the reference answer (LLM-as-judge). Pass `--judge-provider` /
`--judge-model` to keep the judge different from the answerer. The published
numbers in `benchmarks/RESULTS.md` were answered by Gemini
(`gemini-3.5-flash-lite`) and judged by Groq (`openai/gpt-oss-20b`); the
"Reproduce:" line at the end of that file names the exact providers and models of
the run it shows. We also report the share of answers that cite sources and
end-to-end latency.

## How to run

`scripts/fetch_open_notes.py` must run first: the benchmark indexes the books it
downloads. The answer run needs `GEMINI_API_KEY` and `GROQ_API_KEY` in `.env`.

```bash
python scripts/fetch_open_notes.py                      # download the books (run this first)
python benchmarks/run_benchmark.py --retrieval-only     # retrieval only, no model calls needed
# the published setup: Gemini answers, Groq judges
python benchmarks/run_benchmark.py --answer-provider gemini --answer-model gemini-3.5-flash-lite --judge-provider groq --judge-model openai/gpt-oss-20b
python benchmarks/sync_readme.py                        # copies the tables into README.md
```

Both runs use the committed evaluation set, `benchmarks/eval_set.json`.
`python benchmarks/build_eval_set.py --per-book 12` writes a new one (an LLM
writes the questions), so only run it when you want a fresh question set; numbers
from a new set are not comparable with the published ones.

To rebuild `benchmarks/RESULTS.md` from a saved run (for example after changing
the report format) without searching or calling any model:

```bash
python benchmarks/run_benchmark.py --render-only benchmarks/results/20261023-022300.json
python benchmarks/sync_readme.py
```

The benchmark uses its own storage directory (`storage/benchmark`) and user, so
it never touches real accounts. Each run writes one JSON file to
`benchmarks/results/` with the per-question results, including every question's
retrieval rank, and summarises it in `benchmarks/RESULTS.md`, whose tables are
computed from those per-question results and rounded once, for display. Older
results files such as `20261023-022300.json` kept only 3-decimal retrieval
summaries; `--render-only` recovers the exact count behind each Hit@k, and for
both files now in `benchmarks/results/` only one split of ranks matches the stored
MRR, so their metrics are exact. If an older file fits more than one split, it
prints a warning and shows the stored values.

## Caveats

- The evaluation questions are model-written (then spot-checked); they measure
  "can the system find and explain what the book says", not exam difficulty.
- Retrieval is scored at page level: another passage from the source page counts
  as a hit, which is more lenient than requiring the exact passage.
- LLM-as-judge scores are indicative, not ground truth. Use the same judge when
  comparing two configurations.
- Retrieval numbers depend on the embedding model and chunk size; re-run after
  changing either.
