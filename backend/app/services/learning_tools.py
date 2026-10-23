"""AI learning tools: topic summaries, keyword sheets, concept maps and study plans."""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GeneratedArtifact, Subject, Topic, User
from app.services.activity import log_activity
from app.services.generation import GenerationError, context_text, gather_context, generate_json, sources_payload, subject_hint
from app.services.llm import LLMProvider

MAX_NODES = 30


def _save(db: Session, user: User, *, kind: str, title: str, topic: str | None, subject_id: int | None, document_ids, content, sources, result) -> GeneratedArtifact:  # noqa: ANN001
    artifact = GeneratedArtifact(
        user_id=user.id,
        kind=kind,
        title=title[:255],
        topic=topic,
        subject_id=subject_id,
        document_ids=document_ids or None,
        content=content,
        sources=sources,
        provider=getattr(result, "provider", None),
        model=getattr(result, "model", None),
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    log_activity(db, user.id, kind, ref_id=artifact.id, topic=topic, subject_id=subject_id, detail=title)
    return artifact


async def generate_summary(db: Session, user: User, llm: LLMProvider, *, topic: str | None, document_ids: list[int] | None, subject_id: int | None) -> GeneratedArtifact:
    sources = gather_context(db, user.id, topic=topic, document_ids=document_ids, top_k=10)
    if not sources and not topic:
        raise GenerationError("Pick a topic or upload notes first.")
    subj = subject_hint(db, subject_id)
    focus = f"the topic '{topic}'" if topic else "these notes"
    instructions = f"""Write an exam-revision summary of {focus}{' for ' + subj if subj else ''} in Markdown with exactly these sections:
## Definition
## Core concepts
## Important formulas / algorithms (write "None" if not applicable; use LaTeX $...$ for math)
## Worked example
## Exam keywords (bold each keyword, comma separated)
## Common mistakes
## 60-second revision
Use exactly these headings, word for word. Under "60-second revision" write exactly 5 short bullet points.
Ground every statement in the notes when notes are given. Return JSON: {{"title": "...", "markdown": "..."}}"""
    data, result = await generate_json(llm, instructions, context=context_text(sources), max_tokens=4096)
    markdown = str((data or {}).get("markdown") or "").strip() if isinstance(data, dict) else ""
    if len(markdown) < 40:
        raise GenerationError("The summary came back empty. Try again.")
    title = str(data.get("title") or (topic or "Summary")).strip()
    return _save(db, user, kind="summary", title=title, topic=topic, subject_id=subject_id, document_ids=document_ids, content={"markdown": markdown}, sources=sources_payload(sources), result=result)


async def generate_keywords(db: Session, user: User, llm: LLMProvider, *, topic: str | None, document_ids: list[int] | None, subject_id: int | None, count: int = 15) -> GeneratedArtifact:
    sources = gather_context(db, user.id, topic=topic, document_ids=document_ids, top_k=10)
    if not sources and not topic:
        raise GenerationError("Pick a topic or upload notes first.")
    focus = f"'{topic}'" if topic else "these notes"
    instructions = f"""Extract the {count} most exam-relevant keywords/terms for {focus}.
For each give a one-sentence definition a student can memorise and an importance level (high/medium/low) based on how often it appears in exams.
Return JSON: {{"title": "...", "keywords": [{{"term": "...", "definition": "...", "importance": "high", "source": 1}}]}}"""
    data, result = await generate_json(llm, instructions, context=context_text(sources), max_tokens=3000)
    items = data.get("keywords") if isinstance(data, dict) else data
    keywords = []
    for raw in items or []:
        if not isinstance(raw, dict) or not raw.get("term"):
            continue
        importance = str(raw.get("importance") or "medium").lower()
        keywords.append(
            {
                "term": str(raw["term"]).strip()[:120],
                "definition": str(raw.get("definition") or "").strip()[:500],
                "importance": importance if importance in ("high", "medium", "low") else "medium",
                "source": raw.get("source"),
            }
        )
    if not keywords:
        raise GenerationError("No keywords were extracted. Try again.")
    title = str((data.get("title") if isinstance(data, dict) else None) or f"Keywords: {topic or 'notes'}")
    return _save(db, user, kind="keywords", title=title, topic=topic, subject_id=subject_id, document_ids=document_ids, content={"keywords": keywords}, sources=sources_payload(sources), result=result)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "node"


def validate_concept_map(data: dict) -> dict:
    """Validate/clean a concept map produced by the model (ids, edges, limits)."""
    nodes_raw = data.get("nodes") if isinstance(data, dict) else None
    edges_raw = data.get("edges") if isinstance(data, dict) else None
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise GenerationError("The concept map has no nodes.")
    nodes: list[dict] = []
    id_map: dict[str, str] = {}
    for raw in nodes_raw[:MAX_NODES]:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or raw.get("name") or "").strip()
        if not label:
            continue
        rid = str(raw.get("id") or label)
        nid = _slug(rid)
        base = nid
        n = 2
        while nid in id_map.values():
            nid = f"{base}-{n}"
            n += 1
        id_map[rid] = nid
        id_map[label] = nid
        ntype = str(raw.get("type") or "concept").lower()
        nodes.append(
            {
                "id": nid,
                "label": label[:80],
                "type": ntype if ntype in ("concept", "process", "example", "definition", "root") else "concept",
                "description": str(raw.get("description") or "").strip()[:300],
            }
        )
    if not nodes:
        raise GenerationError("The concept map has no valid nodes.")
    valid_ids = {n["id"] for n in nodes}
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in edges_raw or []:
        if not isinstance(raw, dict):
            continue
        s = id_map.get(str(raw.get("source") or raw.get("from") or ""), _slug(str(raw.get("source") or "")))
        t = id_map.get(str(raw.get("target") or raw.get("to") or ""), _slug(str(raw.get("target") or "")))
        if s in valid_ids and t in valid_ids and s != t and (s, t) not in seen:
            seen.add((s, t))
            edges.append({"id": f"e-{s}-{t}", "source": s, "target": t, "label": str(raw.get("label") or "").strip()[:40]})
    if not edges and len(nodes) > 1:
        root = nodes[0]["id"]
        edges = [{"id": f"e-{root}-{n['id']}", "source": root, "target": n["id"], "label": ""} for n in nodes[1:]]
    return {"title": str(data.get("title") or nodes[0]["label"]), "nodes": nodes, "edges": edges}


async def generate_concept_map(db: Session, user: User, llm: LLMProvider, *, topic: str | None, document_ids: list[int] | None, subject_id: int | None, style: str = "concept_map") -> GeneratedArtifact:
    sources = gather_context(db, user.id, topic=topic, document_ids=document_ids, top_k=8)
    if not sources and not topic:
        raise GenerationError("Pick a topic or upload notes first.")
    focus = f"'{topic}'" if topic else "the main ideas in these notes"
    if style == "flowchart":
        shape = "Produce a FLOWCHART of the process/algorithm: nodes are steps or decisions in execution order; edges follow the flow (label decision branches yes/no). Use type 'process' for steps and 'concept' for decisions."
    else:
        shape = "Produce a CONCEPT MAP: one root node, main concepts connected to it, sub-concepts and examples below them; edge labels are short relation verbs (is a, uses, leads to, part of)."
    instructions = f"""Build a knowledge graph for {focus}. {shape}
Limits: 8-{MAX_NODES} nodes, every node must be connected, unique string ids, labels under 8 words, optional one-line description.
Return JSON: {{"title": "...", "nodes": [{{"id": "root", "label": "...", "type": "root", "description": "..."}}], "edges": [{{"source": "root", "target": "n1", "label": "includes"}}]}}"""
    data, result = await generate_json(llm, instructions, context=context_text(sources), max_tokens=4000)
    graph = validate_concept_map(data if isinstance(data, dict) else {"nodes": data})
    graph["style"] = style
    return _save(db, user, kind="concept_map", title=graph["title"], topic=topic, subject_id=subject_id, document_ids=document_ids, content=graph, sources=sources_payload(sources), result=result)


async def generate_study_plan(
    db: Session,
    user: User,
    llm: LLMProvider,
    *,
    exam_date: date,
    subject_ids: list[int],
    daily_minutes: int,
    weak_topics: list[str],
    focus: str | None = None,
) -> GeneratedArtifact:
    today = date.today()
    days_left = (exam_date - today).days
    if days_left < 1:
        raise GenerationError("Exam date must be in the future.")
    days_left = min(days_left, 30)
    subjects = list(db.execute(select(Subject).where(Subject.id.in_(subject_ids))).scalars()) if subject_ids else []
    if not subjects:
        raise GenerationError("Select at least one subject from the syllabus.")
    outline_parts = []
    for s in subjects:
        topics = db.execute(select(Topic).where(Topic.subject_id == s.id).order_by(Topic.unit, Topic.order_index)).scalars().all()
        units: dict[int, list[str]] = {}
        unit_titles: dict[int, str] = {}
        for t in topics:
            units.setdefault(t.unit, []).append(t.name)
            unit_titles[t.unit] = t.unit_title
        unit_lines = "\n".join(f"  Unit {u} - {unit_titles[u]}: " + "; ".join(names[:12]) for u, names in sorted(units.items()))
        outline_parts.append(f"{s.code} {s.name}\n{unit_lines}")
    outline = "\n\n".join(outline_parts)
    weak = ", ".join(weak_topics) if weak_topics else "none recorded yet"
    instructions = f"""Create a day-by-day revision plan from {today.isoformat()} to {exam_date.isoformat()} ({days_left} days) for these AKTU subjects:

{outline}

Constraints: about {daily_minutes} minutes per day; weak topics from recent quizzes: {weak}. {('Extra focus: ' + focus) if focus else ''}
Mix activities: read/revise notes, quiz, flashcards, past-paper practice; keep the last 2 days for full-syllabus revision and mock tests; interleave subjects.
Return JSON: {{"title": "...", "days": [{{"date": "YYYY-MM-DD", "focus": "...", "tasks": [{{"title": "...", "subject": "BCS401", "type": "read|quiz|flashcards|practice|revise", "minutes": 45}}]}}], "tips": ["...", "..."]}}"""
    data, result = await generate_json(llm, instructions, context="", max_tokens=6000, temperature=0.5)
    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, list) or not days:
        raise GenerationError("The plan came back empty. Try again.")
    cleaned_days = []
    for d in days[:days_left]:
        if not isinstance(d, dict):
            continue
        tasks = [
            {
                "title": str(t.get("title") or "").strip()[:160],
                "subject": str(t.get("subject") or "").strip()[:20],
                "type": str(t.get("type") or "read").lower(),
                "minutes": int(t.get("minutes") or 30) if str(t.get("minutes") or "").lstrip("-").isdigit() else 30,
                "done": False,
            }
            for t in (d.get("tasks") or [])
            if isinstance(t, dict) and t.get("title")
        ]
        cleaned_days.append({"date": str(d.get("date") or ""), "focus": str(d.get("focus") or "").strip()[:200], "tasks": tasks})
    content = {
        "exam_date": exam_date.isoformat(),
        "daily_minutes": daily_minutes,
        "subjects": [{"id": s.id, "code": s.code, "name": s.name} for s in subjects],
        "days": cleaned_days,
        "tips": [str(t) for t in (data.get("tips") or [])][:6],
    }
    title = str(data.get("title") or f"Study plan until {exam_date.isoformat()}")
    return _save(db, user, kind="study_plan", title=title, topic=None, subject_id=subjects[0].id, document_ids=None, content=content, sources=None, result=result)


def list_artifacts(db: Session, user: User, kind: str | None = None, limit: int = 50) -> list[GeneratedArtifact]:
    stmt = select(GeneratedArtifact).where(GeneratedArtifact.user_id == user.id)
    if kind:
        stmt = stmt.where(GeneratedArtifact.kind == kind)
    return list(db.execute(stmt.order_by(GeneratedArtifact.created_at.desc()).limit(limit)).scalars())


def get_owned_artifact(db: Session, user: User, artifact_id: int) -> GeneratedArtifact | None:
    art = db.get(GeneratedArtifact, artifact_id)
    return art if art and art.user_id == user.id else None
