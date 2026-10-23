#!/usr/bin/env python
"""Benchmark retrieval and answer quality on the open-textbook corpus.

Retrieval (no LLM needed): for every eval question, run keyword / semantic /
hybrid search and record the rank of the first result that is the question's
source passage or another passage from the same page of the same book (see
is_hit). Hit@1, Hit@3, Hit@5 and MRR are computed from those ranks, alongside
search latency.

Answer quality (needs a chat model): answer each question with the normal RAG
pipeline, then have a *different* model grade the answer against the reference
(correctness 0-5), check whether it cites sources, and whether the keywords are
present. Results are written to benchmarks/results/ and summarised in
benchmarks/RESULTS.md.

Run scripts/fetch_open_notes.py first (it downloads the books). --render-only
rewrites RESULTS.md from a saved results file without searching or calling any
model.

    python benchmarks/run_benchmark.py --retrieval-only
    python benchmarks/run_benchmark.py --answer-provider gemini --answer-model gemini-3.5-flash-lite --judge-provider groq --judge-model openai/gpt-oss-20b
    python benchmarks/run_benchmark.py --render-only benchmarks/results/20261023-022300.json
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import asyncio
import json
import shlex
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from common import EVAL_SET, RESULTS_DIR, ROOT, bench_session, bench_user, ensure_corpus, get_llm  # noqa: E402
from sqlalchemy import select

from app.models import Chunk, Document
from app.services.llm import LLMError, extract_json
from app.services.rag_service import answer_once
from app.services.search_service import RetrievedChunk, hybrid_search

MODES = ["keyword", "semantic", "hybrid"]
K = 5
RESULTS_MD = ROOT / "benchmarks" / "RESULTS.md"

JUDGE_PROMPT = """You are grading a tutoring system's answer to a university exam question.

Question: {question}
Reference answer (ground truth): {reference}
Candidate answer: {candidate}

Score the candidate's CORRECTNESS from 0 to 5 compared with the reference:
5 = fully correct and complete, 4 = correct with minor omissions, 3 = partially correct,
2 = mostly wrong or vague, 1 = wrong, 0 = no answer / refuses.
Ignore formatting, citations like [1], and extra correct detail.
Return JSON: {{"score": <0-5>, "reason": "<one sentence>"}}"""


def is_hit(item: dict, hit: RetrievedChunk, doc_titles: dict[int, str]) -> bool:
    """A hit is the source passage itself or any other passage from the same page of the same book."""
    if doc_titles.get(hit.document_id) != item["book"]:
        return False
    if hit.content.startswith(item["chunk_prefix"][:80]):
        return True
    return item["page_no"] is not None and hit.page_no == item["page_no"]


def retrieval_metrics(ranks: list[int | None]) -> dict:
    """Hit@1, Hit@3, Hit@K and MRR from per-question ranks (None = not in the top K), unrounded."""
    n = len(ranks)
    return {
        "hit@1": sum(1 for r in ranks if r == 1) / n,
        "hit@3": sum(1 for r in ranks if r and r <= 3) / n,
        f"hit@{K}": sum(1 for r in ranks if r and r <= K) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
    }


def _close(value: float, stored: float) -> bool:
    return abs(value - stored) <= 0.0005 + 1e-9  # the stored value was rounded to 3 decimals


def ranks_from_rounded(m: dict, n: int) -> list[int | None] | None:
    """Rebuild the ranks behind a results file saved before per-question ranks were kept.

    Those files store Hit@1/3/5 and MRR rounded to 3 decimals. A Hit@k is a count over n
    questions, so for n < 1000 the count survives the rounding exactly; the split of the
    remaining hits over ranks 2-3 and 4-5 is whichever one reproduces the stored MRR.
    Returns None when the stored values are inconsistent or more than one split fits.
    """
    c1, c3, c5 = (round(m[f"hit@{k}"] * n) for k in (1, 3, 5))
    if not (0 < n < 1000 and 0 <= c1 <= c3 <= c5 <= n) or ("misses" in m and len(m["misses"]) != n - c5):
        return None
    if not all(_close(c / n, m[f"hit@{k}"]) for c, k in ((c1, 1), (c3, 3), (c5, 5))):
        return None
    fits = [
        [1] * c1 + [2] * two + [3] * (c3 - c1 - two) + [4] * four + [5] * (c5 - c3 - four) + [None] * (n - c5)
        for two in range(c3 - c1 + 1)
        for four in range(c5 - c3 + 1)
        if _close((c1 + two / 2 + (c3 - c1 - two) / 3 + four / 4 + (c5 - c3 - four) / 5) / n, m["mrr"])
    ]
    return fits[0] if len(fits) == 1 else None


def evaluate_retrieval(db, user_id: int, items: list[dict], doc_titles: dict[int, str]) -> dict:  # noqa: ANN001
    out: dict[str, dict] = {}
    for mode in MODES:
        ranks: list[int | None] = []
        latencies: list[float] = []
        for item in items:
            t0 = time.perf_counter()
            hits = hybrid_search(db, user_id, item["question"], top_k=K, mode=mode)
            latencies.append((time.perf_counter() - t0) * 1000)
            rank = next((i + 1 for i, h in enumerate(hits) if is_hit(item, h, doc_titles)), None)
            ranks.append(rank)
        out[mode] = {
            **retrieval_metrics(ranks),  # unrounded: RESULTS.md rounds once, when it formats them
            "p50_latency_ms": round(statistics.median(latencies), 1),
            "misses": [items[i]["id"] for i, r in enumerate(ranks) if r is None],
            "ranks": [[item["id"], r] for item, r in zip(items, ranks, strict=True)],  # a list: question ids may repeat
        }
        print(f"  {mode:9s} hit@1={out[mode]['hit@1']:.2f} hit@3={out[mode]['hit@3']:.2f} hit@{K}={out[mode][f'hit@{K}']:.2f} mrr={out[mode]['mrr']:.2f} p50={out[mode]['p50_latency_ms']}ms")
    return out


async def _with_backoff(coro_factory, what: str, attempts: int = 5):  # noqa: ANN001
    """Free tiers throttle hard; wait and retry instead of losing the question."""
    delay = 20.0
    for attempt in range(attempts):
        try:
            return await coro_factory()
        except LLMError as exc:
            if exc.status != 429 or attempt == attempts - 1:
                raise
            print(f"    {what}: rate limited, waiting {delay:.0f}s (attempt {attempt + 1}/{attempts})")
            await asyncio.sleep(delay)
            delay = min(delay * 1.6, 120.0)


def answer_summary(rows: list[dict]) -> dict:
    """Aggregate the per-question answer rows, unrounded."""
    answered = [r for r in rows if "answer" in r]
    scored = [r for r in rows if r.get("judge_score") is not None]
    latencies = [r["latency_ms"] for r in rows if "latency_ms" in r]
    return {
        "answered": len(answered),
        "failed": len([r for r in rows if "error" in r]),
        "judged": len(scored),
        "mean_score": statistics.mean(r["judge_score"] for r in scored) if scored else None,
        "accuracy_ge4": sum(1 for r in scored if r["judge_score"] >= 4) / len(scored) if scored else None,
        "cited_rate": sum(1 for r in answered if r.get("cited")) / max(1, len(answered)),
        "p50_latency_ms": statistics.median(latencies) if latencies else None,
    }


async def evaluate_answers(db, user_id: int, items: list[dict], answerer, judge, limit: int | None, pause: float = 8.0) -> dict:  # noqa: ANN001
    rows = []
    subset = items[:limit] if limit else items
    for i, item in enumerate(subset, start=1):
        if i > 1 and pause:
            await asyncio.sleep(pause)  # stay under per-minute token limits
        t0 = time.perf_counter()
        try:
            answer, ctx = await _with_backoff(lambda: answer_once(answerer, db, user_id, item["question"], answer_mode="exam"), "answer")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i}/{len(subset)}] answer failed: {exc}")
            rows.append({"id": item["id"], "error": str(exc)[:200]})
            continue
        latency = (time.perf_counter() - t0) * 1000
        cited = "[1]" in answer or "[2]" in answer
        keywords_hit = sum(1 for k in item["keywords"] if k.lower() in answer.lower())
        score, reason = None, None
        try:
            res = await _with_backoff(
                lambda: judge.complete(
                    [{"role": "system", "content": "Reply with JSON only."}, {"role": "user", "content": JUDGE_PROMPT.format(question=item["question"], reference=item["reference_answer"], candidate=answer[:3000])}],
                    temperature=0.0,
                    max_tokens=1024,  # reasoning models spend tokens thinking before the JSON
                    json_mode=True,
                ),
                "judge",
            )
            if not res.text.strip():
                raise ValueError("judge returned an empty response")
            data = extract_json(res.text)
            score = max(0, min(5, int(data.get("score", 0))))
            reason = str(data.get("reason", ""))[:300]
        except Exception as exc:  # noqa: BLE001
            reason = f"judge failed: {str(exc)[:120]}"
        rows.append(
            {
                "id": item["id"],
                "book": item["book"],
                "question": item["question"],
                "answer": answer,
                "sources": [{"doc": s.document_title, "page": s.page_no} for s in ctx.sources],
                "grounded": ctx.grounded,
                "cited": cited,
                "keywords_hit": f"{keywords_hit}/{len(item['keywords'])}",
                "judge_score": score,
                "judge_reason": reason,
                "latency_ms": round(latency),
            }
        )
        print(f"  [{i}/{len(subset)}] score={score} cited={cited} kw={keywords_hit}/{len(item['keywords'])} {latency:.0f}ms  {item['question'][:70]}")
    return {"summary": answer_summary(rows), "rows": rows}


def retrieval_table(result: dict) -> dict[str, dict]:
    """Per-mode metrics for RESULTS.md, recomputed from the per-question ranks rather than stored summaries."""
    table: dict[str, dict] = {}
    for mode, m in result["retrieval"].items():
        ranks = [r for _, r in m["ranks"]] if "ranks" in m else ranks_from_rounded(m, result["questions"])
        if ranks is None:
            print(f"  warning: {mode} has no per-question ranks and its stored metrics are ambiguous; showing them as stored")
            table[mode] = m
        else:
            table[mode] = {**retrieval_metrics(ranks), "p50_latency_ms": m["p50_latency_ms"]}
    return table


def reproduce_command(result: dict) -> str:
    """The run_benchmark.py command for a saved run, built from the providers and models it recorded."""
    cmd = ["python", "benchmarks/run_benchmark.py"]
    if not result.get("answers"):
        return " ".join(cmd + ["--retrieval-only"])
    for role, label in (("answer", result["answerer"]), ("judge", result["judge"])):
        provider, _, model = label.partition("/")  # split at the first "/" only: model ids can contain "/"
        cmd += [f"--{role}-provider", provider] + ([f"--{role}-model", model] if model else [])
    rows = result["answers"].get("rows")
    if rows and len(rows) < result["questions"]:
        cmd += ["--limit", str(len(rows))]
    return " ".join(shlex.quote(c) for c in cmd)


def _fmt(value: float | None, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def _rel(path: Path) -> str:
    path = path.resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name


def write_results_md(result: dict, source: Path) -> None:
    md = [
        "# Benchmark results",
        "",
        f"Last run: {result['run_at']} · corpus: {', '.join(result['corpus'])} ({result['chunks']} chunks, {result['questions']} questions)",
        "",
        f"Embeddings: `{result['embedding']}` · vector store: `{result['vector_store']}`",
        "",
        "## Retrieval (does the source passage, or another passage from the same page, come back?)",
        "",
        "A question is a hit at k when the passage it was written from, or another passage from the same page of the same book, "
        f"is among the top k results. MRR is the mean of 1/rank of the first such result (0 when none is in the top {K}).",
        "",
        f"| Mode | Hit@1 | Hit@3 | Hit@{K} | MRR | p50 latency |",
        "|---|---|---|---|---|---|",
    ]
    for mode, m in retrieval_table(result).items():
        md.append(f"| {mode} | {m['hit@1']:.2f} | {m['hit@3']:.2f} | {m[f'hit@{K}']:.2f} | {m['mrr']:.2f} | {m['p50_latency_ms']} ms |")
    if result.get("answers"):
        rows = result["answers"].get("rows")
        s = answer_summary(rows) if rows else result["answers"]["summary"]
        md += [
            "",
            f"## Answer quality (answerer: `{result['answerer']}`, judge: `{result['judge']}`)",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Questions answered / judged / failed | {s['answered']} / {s['judged']} / {s.get('failed', 0)} |",
            f"| Mean judge score (0-5) | {_fmt(s['mean_score'], '.2f')} |",
            f"| Accuracy (score >= 4) | {_fmt(s['accuracy_ge4'], '.3f')} |",
            f"| Answers with citations | {_fmt(s['cited_rate'], '.3f')} |",
            f"| p50 end-to-end latency | {_fmt(s['p50_latency_ms'], '.0f')} ms |",
        ]
    md += [
        "",
        f"Reproduce: run `python scripts/fetch_open_notes.py` first (it downloads the books), then `{reproduce_command(result)}`.",
        f"Raw per-question output for this run: `{_rel(source)}`.",
    ]
    RESULTS_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--answer-provider", default=None)
    ap.add_argument("--answer-model", default=None)
    ap.add_argument("--judge-provider", default=None)
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--limit", type=int, default=None, help="answer only the first N questions")
    ap.add_argument("--pause", type=float, default=8.0, help="seconds between questions (free tiers have per-minute token limits)")
    ap.add_argument("--render-only", type=Path, default=None, metavar="RESULTS_JSON", help="rewrite benchmarks/RESULTS.md from a saved results file; no search, no model calls")
    args = ap.parse_args()

    if args.render_only:
        if not args.render_only.is_file():
            ap.error(f"results file not found: {args.render_only}")
        write_results_md(json.loads(args.render_only.read_text(encoding="utf-8")), args.render_only)
        print(f"Rendered benchmarks/RESULTS.md from {args.render_only}")
        return

    if not EVAL_SET.exists():
        raise SystemExit("No eval set. Run `python benchmarks/build_eval_set.py` first.")
    eval_set = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    items = eval_set["items"]

    db = bench_session()
    user = bench_user(db)
    print("Preparing corpus...")
    docs = ensure_corpus(db, user)
    doc_titles = {d.id: d.title for d in db.execute(select(Document).where(Document.user_id == user.id)).scalars()}
    chunk_count = db.query(Chunk).filter(Chunk.user_id == user.id).count()
    from app.core.config import get_settings
    from app.services.embeddings import get_embedder

    settings = get_settings()
    print(f"\nRetrieval over {chunk_count} chunks, {len(items)} questions (embeddings: {get_embedder().name})")
    retrieval = evaluate_retrieval(db, user.id, items, doc_titles)

    result = {
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "corpus": [d.title for d in docs],
        "chunks": chunk_count,
        "questions": len(items),
        "embedding": get_embedder().name,
        "vector_store": settings.vector_store,
        "retrieval": retrieval,
    }
    if not args.retrieval_only:
        answerer = get_llm(db, args.answer_provider, args.answer_model)
        judge = get_llm(db, args.judge_provider, args.judge_model)
        print(f"\nAnswering with {answerer.id}/{answerer.model}; judging with {judge.id}/{judge.model}")
        result["answerer"] = f"{answerer.id}/{answerer.model}"
        result["judge"] = f"{judge.id}/{judge.model}"
        result["answers"] = await evaluate_answers(db, user.id, items, answerer, judge, args.limit, pause=args.pause)
        print("\nSummary:", json.dumps(result["answers"]["summary"]))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RESULTS_DIR / f"{stamp}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_results_md(result, out)
    print(f"\nSaved {out} and benchmarks/RESULTS.md")


if __name__ == "__main__":
    asyncio.run(main())
