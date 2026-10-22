#!/usr/bin/env python
"""Build a question/answer evaluation set from the open textbooks.

For every book we sample passages spread across the whole text and ask an LLM
to write one exam-style question that is answerable from that passage only,
plus a short reference answer and the key terms a correct answer must contain.
The passage (document, page, text prefix) is the retrieval ground truth.

    python benchmarks/build_eval_set.py --per-book 12 --provider groq
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import asyncio
import json
import random
import re
from datetime import datetime, timezone

from common import EVAL_SET, bench_session, bench_user, ensure_corpus, get_llm  # noqa: E402
from sqlalchemy import select

from app.models import Chunk
from app.services.llm import extract_json

PROMPT = """You write university exam questions. Below is one passage from a textbook.

PASSAGE:
{passage}

Write ONE question that a student could answer using ONLY this passage, and that would be a fair
short-answer exam question (not trivia about formatting, figure numbers or exercises).
Rules: do not mention "the passage", "the text" or "the author"; the question must stand on its own.
Also give a concise reference answer (1-3 sentences, using the passage's wording) and 3-5 keywords
(distinctive terms from the passage that any correct answer must mention).
Return JSON: {{"question": "...", "answer": "...", "keywords": ["...", "..."]}}"""


def usable(chunk: Chunk) -> bool:
    text = chunk.content
    if len(text) < 700:
        return False
    letters = sum(c.isalpha() for c in text)
    if letters / max(1, len(text)) < 0.7:
        return False  # tables of contents, code listings, index pages
    if re.search(r"\.{4,}|\bexercises?\b.*\d\.\d|\bcontents\b", text[:300], re.IGNORECASE):
        return False
    return True


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-book", type=int, default=12)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args()

    random.seed(args.seed)
    db = bench_session()
    user = bench_user(db)
    print("Preparing corpus...")
    docs = ensure_corpus(db, user)
    llm = get_llm(db, args.provider, args.model)
    print(f"Question writer: {llm.id} / {llm.model}")

    items: list[dict] = []
    if args.append and EVAL_SET.exists():
        items = json.loads(EVAL_SET.read_text(encoding="utf-8"))["items"]

    for doc in docs:
        chunks = [c for c in db.execute(select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.chunk_index)).scalars() if usable(c)]
        if not chunks:
            print(f"  {doc.title}: no usable chunks")
            continue
        step = max(1, len(chunks) // args.per_book)
        picked = chunks[step // 2 :: step][: args.per_book]
        print(f"  {doc.title}: {len(chunks)} usable chunks -> {len(picked)} questions")
        for chunk in picked:
            try:
                result = await llm.complete(
                    [{"role": "system", "content": "Reply with JSON only."}, {"role": "user", "content": PROMPT.format(passage=chunk.content[:3500])}],
                    temperature=0.4,
                    max_tokens=600,
                    json_mode=True,
                )
                data = extract_json(result.text)
                question = str(data["question"]).strip()
                answer = str(data["answer"]).strip()
                keywords = [str(k).strip() for k in data.get("keywords", []) if str(k).strip()]
                if len(question) < 15 or len(answer) < 5:
                    continue
                items.append(
                    {
                        "id": f"{doc.id}-{chunk.id}",
                        "book": doc.title,
                        "filename": doc.filename,
                        "page_no": chunk.page_no,
                        "chunk_prefix": chunk.content[:120],
                        "question": question,
                        "reference_answer": answer,
                        "keywords": keywords[:5],
                    }
                )
                print(f"    q: {question[:90]}")
            except Exception as exc:  # noqa: BLE001
                print(f"    skipped chunk {chunk.id}: {exc}")

    EVAL_SET.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "writer": {"provider": llm.id, "model": llm.model},
                "per_book": args.per_book,
                "items": items,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {len(items)} questions to {EVAL_SET}")


if __name__ == "__main__":
    asyncio.run(main())
