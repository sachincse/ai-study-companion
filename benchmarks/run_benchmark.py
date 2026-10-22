#!/usr/bin/env python
"""Benchmark retrieval and answer quality on the open-textbook corpus.

Retrieval (no LLM needed): for every eval question, run keyword / semantic /
hybrid search and check whether the ground-truth passage is retrieved
(Hit@1, Hit@3, Hit@5, MRR) and how long it takes.

Answer quality (needs a chat model): answer each question with the normal RAG
pipeline, then have a *different* model grade the answer against the reference
(correctness 0-5), check whether it cites sources, and whether the keywords are
present. Results are written to benchmarks/results/ and summarised in
benchmarks/RESULTS.md.

    python benchmarks/run_benchmark.py --retrieval-only
    python benchmarks/run_benchmark.py --answer-provider groq --judge-provider gemini
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from common import EVAL_SET, RESULTS_DIR, ROOT, bench_session, bench_user, ensure_corpus, get_llm  # noqa: E402
from sqlalchemy import select

from app.models import Chunk, Document
from app.services.llm import extract_json
from app.services.rag_service import answer_once
from app.services.search_service import RetrievedChunk, hybrid_search

MODES = ["keyword", "semantic", "hybrid"]
K = 5

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
    if doc_titles.get(hit.document_id) != item["book"]:
        return False
    if hit.content.startswith(item["chunk_prefix"][:80]):
        return True
    return item["page_no"] is not None and hit.page_no == item["page_no"]


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
        n = len(ranks)
        out[mode] = {
            "hit@1": round(sum(1 for r in ranks if r == 1) / n, 3),
            "hit@3": round(sum(1 for r in ranks if r and r <= 3) / n, 3),
            f"hit@{K}": round(sum(1 for r in ranks if r and r <= K) / n, 3),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 3),
            "p50_latency_ms": round(statistics.median(latencies), 1),
            "misses": [items[i]["id"] for i, r in enumerate(ranks) if r is None],
        }
        print(f"  {mode:9s} hit@1={out[mode]['hit@1']:.2f} hit@3={out[mode]['hit@3']:.2f} hit@{K}={out[mode][f'hit@{K}']:.2f} mrr={out[mode]['mrr']:.2f} p50={out[mode]['p50_latency_ms']}ms")
    return out


async def evaluate_answers(db, user_id: int, items: list[dict], answerer, judge, limit: int | None) -> dict:  # noqa: ANN001
    rows = []
    subset = items[:limit] if limit else items
    for i, item in enumerate(subset, start=1):
        t0 = time.perf_counter()
        try:
            answer, ctx = await answer_once(answerer, db, user_id, item["question"], answer_mode="short")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i}/{len(subset)}] answer failed: {exc}")
            rows.append({"id": item["id"], "error": str(exc)[:200]})
            continue
        latency = (time.perf_counter() - t0) * 1000
        cited = "[1]" in answer or "[2]" in answer
        keywords_hit = sum(1 for k in item["keywords"] if k.lower() in answer.lower())
        score, reason = None, None
        try:
            res = await judge.complete(
                [{"role": "system", "content": "Reply with JSON only."}, {"role": "user", "content": JUDGE_PROMPT.format(question=item["question"], reference=item["reference_answer"], candidate=answer[:3000])}],
                temperature=0.0,
                max_tokens=1024,  # reasoning models spend tokens thinking before the JSON
                json_mode=True,
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
    scored = [r for r in rows if r.get("judge_score") is not None]
    summary = {
        "answered": len([r for r in rows if "answer" in r]),
        "judged": len(scored),
        "mean_score": round(statistics.mean(r["judge_score"] for r in scored), 2) if scored else None,
        "accuracy_ge4": round(sum(1 for r in scored if r["judge_score"] >= 4) / len(scored), 3) if scored else None,
        "cited_rate": round(sum(1 for r in rows if r.get("cited")) / max(1, len([r for r in rows if "answer" in r])), 3),
        "p50_latency_ms": round(statistics.median(r["latency_ms"] for r in rows if "latency_ms" in r), 0) if any("latency_ms" in r for r in rows) else None,
    }
    return {"summary": summary, "rows": rows}


def write_results_md(result: dict) -> None:
    md = [
        "# Benchmark results",
        "",
        f"Last run: {result['run_at']} · corpus: {', '.join(result['corpus'])} ({result['chunks']} chunks, {result['questions']} questions)",
        "",
        f"Embeddings: `{result['embedding']}` · vector store: `{result['vector_store']}`",
        "",
        "## Retrieval (does the ground-truth passage come back?)",
        "",
        "| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | p50 latency |",
        "|---|---|---|---|---|---|",
    ]
    for mode, m in result["retrieval"].items():
        md.append(f"| {mode} | {m['hit@1']:.2f} | {m['hit@3']:.2f} | {m['hit@5']:.2f} | {m['mrr']:.2f} | {m['p50_latency_ms']} ms |")
    if result.get("answers"):
        s = result["answers"]["summary"]
        md += [
            "",
            f"## Answer quality (answerer: `{result['answerer']}`, judge: `{result['judge']}`)",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Questions answered / judged | {s['answered']} / {s['judged']} |",
            f"| Mean judge score (0-5) | {s['mean_score']} |",
            f"| Accuracy (score >= 4) | {s['accuracy_ge4']} |",
            f"| Answers with citations | {s['cited_rate']} |",
            f"| p50 end-to-end latency | {s['p50_latency_ms']} ms |",
        ]
    md += ["", "Reproduce: `python scripts/fetch_open_notes.py && python benchmarks/run_benchmark.py`.", "Raw per-question output lives in `benchmarks/results/`."]
    (ROOT / "benchmarks" / "RESULTS.md").write_text("\n".join(md) + "\n", encoding="utf-8")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--answer-provider", default=None)
    ap.add_argument("--answer-model", default=None)
    ap.add_argument("--judge-provider", default=None)
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--limit", type=int, default=None, help="answer only the first N questions")
    args = ap.parse_args()

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
        result["answers"] = await evaluate_answers(db, user.id, items, answerer, judge, args.limit)
        print("\nSummary:", json.dumps(result["answers"]["summary"]))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RESULTS_DIR / f"{stamp}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_results_md(result)
    print(f"\nSaved {out} and benchmarks/RESULTS.md")


if __name__ == "__main__":
    asyncio.run(main())
