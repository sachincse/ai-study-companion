"""Quiz generation, attempts and grading (deterministic + rubric-based AI grading)."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AttemptAnswer, Question, Quiz, QuizAttempt, User
from app.services.activity import log_activity
from app.services.generation import GenerationError, context_text, gather_context, generate_json, subject_hint
from app.services.llm import LLMError, LLMProvider, extract_json
from app.services.search_service import RetrievedChunk

log = logging.getLogger(__name__)

QTYPES = {"mcq", "true_false", "short_answer"}
LETTERS = "ABCDEF"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ----------------------------------------------------------------- generation
def _quiz_instructions(*, topic: str | None, count: int, difficulty: str, types: list[str], subject: str | None) -> str:
    type_text = ", ".join(types)
    focus = f"on the topic '{topic}'" if topic else "covering the main ideas in the notes"
    subj = f" for the subject {subject}" if subject else ""
    return f"""Create a {difficulty} difficulty practice quiz{subj} {focus} with exactly {count} questions.
Allowed question types: {type_text}. Mix them sensibly (MCQs should dominate when allowed).

Rules:
- Every question must be answerable from the notes when notes are provided; reference the source number you used in "source" (the number in brackets), or null.
- MCQ: exactly 4 options, one correct; "answer" is the letter A-D. Make distractors plausible, no "all of the above".
- true_false: "answer" is "True" or "False".
- short_answer: 2-4 mark descriptive question; "answer" is a model answer of 2-4 sentences; "rubric" lists 2-4 key points worth marks.
- "explanation" teaches why the answer is right in 1-3 sentences.
- "topic" is a short topic label (2-5 words) used for analytics.
- "marks": 1 for mcq/true_false, 2-4 for short_answer.

Return JSON: {{"title": "...", "questions": [{{"type": "mcq", "question": "...", "options": ["...", "...", "...", "..."], "answer": "B", "explanation": "...", "topic": "...", "marks": 1, "source": 1}}, {{"type": "short_answer", "question": "...", "answer": "...", "rubric": ["...", "..."], "explanation": "...", "topic": "...", "marks": 3, "source": 2}}]}}"""


def _normalise_question(raw: dict, sources: list[RetrievedChunk]) -> dict | None:
    qtype = str(raw.get("type") or raw.get("qtype") or "mcq").lower().replace("-", "_").replace(" ", "_")
    if qtype in ("truefalse", "true/false", "tf"):
        qtype = "true_false"
    if qtype in ("short", "descriptive", "long_answer", "saq"):
        qtype = "short_answer"
    if qtype not in QTYPES:
        return None
    prompt = str(raw.get("question") or raw.get("prompt") or "").strip()
    if len(prompt) < 8:
        return None
    answer = str(raw.get("answer") if raw.get("answer") is not None else "").strip()
    options: list | None = None
    if qtype == "mcq":
        opts = [str(o).strip() for o in (raw.get("options") or []) if str(o).strip()]
        if len(opts) < 2:
            return None
        opts = opts[:6]
        # strip leading "A." / "A)" labels
        opts = [re.sub(r"^[A-Fa-f][\.\)\:]\s*", "", o) for o in opts]
        letter = answer[:1].upper()
        if letter in LETTERS[: len(opts)] and (len(answer) <= 2 or answer[1:2] in ").:"):
            answer = letter
        else:
            # answer given as option text
            matches = [i for i, o in enumerate(opts) if o.lower() == answer.lower().strip()]
            if not matches:
                return None
            answer = LETTERS[matches[0]]
        options = opts
    elif qtype == "true_false":
        low = answer.lower()
        if low.startswith("t"):
            answer = "True"
        elif low.startswith("f"):
            answer = "False"
        else:
            return None
        options = ["True", "False"]
    else:
        rubric = [str(r).strip() for r in (raw.get("rubric") or []) if str(r).strip()]
        if not answer:
            return None
        options = rubric or None
    source_idx = raw.get("source")
    source_chunk_ids: list[int] = []
    source_page: int | None = None
    try:
        if source_idx is not None and 1 <= int(source_idx) <= len(sources):
            src = sources[int(source_idx) - 1]
            source_chunk_ids = [src.chunk_id]
            source_page = src.page_no
    except (TypeError, ValueError):
        pass
    try:
        marks = int(raw.get("marks") or (1 if qtype != "short_answer" else 3))
    except (TypeError, ValueError):
        marks = 1
    return {
        "qtype": qtype,
        "prompt": prompt,
        "options": options,
        "answer_key": answer,
        "explanation": (str(raw.get("explanation") or "").strip() or None),
        "topic": (str(raw.get("topic") or "").strip()[:255] or None),
        "marks": max(1, min(10, marks)),
        "source_chunk_ids": source_chunk_ids or None,
        "source_page": source_page,
    }


async def generate_quiz(
    db: Session,
    user: User,
    llm: LLMProvider,
    *,
    topic: str | None,
    document_ids: list[int] | None,
    subject_id: int | None,
    count: int = 8,
    difficulty: str = "medium",
    types: list[str] | None = None,
    time_limit_sec: int | None = None,
) -> Quiz:
    types = [t for t in (types or ["mcq", "true_false", "short_answer"]) if t in QTYPES] or ["mcq"]
    count = max(3, min(25, count))
    sources = gather_context(db, user.id, topic=topic, document_ids=document_ids, top_k=10)
    if not sources and not topic:
        raise GenerationError("Pick a topic or upload notes first so the quiz has something to draw from.")
    instructions = _quiz_instructions(topic=topic, count=count, difficulty=difficulty, types=types, subject=subject_hint(db, subject_id))
    data, result = await generate_json(llm, instructions, context=context_text(sources), max_tokens=6000)
    raw_questions = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(raw_questions, list):
        raise GenerationError("The model returned no questions. Try again.")
    questions = [q for q in (_normalise_question(r, sources) for r in raw_questions if isinstance(r, dict)) if q]
    if len(questions) < 2:
        raise GenerationError("Could not build a valid quiz from the model output. Try again or change the model.")

    title = (data.get("title") if isinstance(data, dict) else None) or (f"Quiz: {topic}" if topic else "Practice quiz")
    quiz = Quiz(
        user_id=user.id,
        title=str(title)[:200],
        subject_id=subject_id,
        topic=topic,
        document_ids=document_ids or None,
        difficulty=difficulty,
        question_count=len(questions),
        time_limit_sec=time_limit_sec,
        provider=result.provider,
        model=result.model,
    )
    db.add(quiz)
    db.flush()
    for i, q in enumerate(questions):
        db.add(Question(quiz_id=quiz.id, position=i, **q))
    db.commit()
    db.refresh(quiz)
    log_activity(db, user.id, "quiz_generated", ref_id=quiz.id, topic=topic, subject_id=subject_id, detail=quiz.title)
    return quiz


# ------------------------------------------------------------------- attempts
def get_owned_quiz(db: Session, user: User, quiz_id: int) -> Quiz | None:
    quiz = db.execute(
        select(Quiz).options(selectinload(Quiz.questions)).where(Quiz.id == quiz_id, Quiz.user_id == user.id)
    ).scalar_one_or_none()
    return quiz


def list_quizzes(db: Session, user: User) -> list[Quiz]:
    return list(
        db.execute(
            select(Quiz).options(selectinload(Quiz.attempts)).where(Quiz.user_id == user.id).order_by(Quiz.created_at.desc())
        ).scalars()
    )


def start_attempt(db: Session, user: User, quiz: Quiz) -> QuizAttempt:
    attempt = QuizAttempt(quiz_id=quiz.id, user_id=user.id, max_score=float(sum(q.marks for q in quiz.questions)))
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def get_owned_attempt(db: Session, user: User, attempt_id: int) -> QuizAttempt | None:
    return db.execute(
        select(QuizAttempt)
        .options(selectinload(QuizAttempt.answers), selectinload(QuizAttempt.quiz).selectinload(Quiz.questions))
        .where(QuizAttempt.id == attempt_id, QuizAttempt.user_id == user.id)
    ).scalar_one_or_none()


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def grade_objective(question: Question, answer: str | None) -> tuple[bool, float]:
    if not answer:
        return False, 0.0
    if question.qtype == "mcq":
        given = answer.strip().upper()[:1]
        if given not in LETTERS and question.options:
            matches = [i for i, o in enumerate(question.options) if _norm(o) == _norm(answer)]
            given = LETTERS[matches[0]] if matches else ""
        correct = given == question.answer_key.strip().upper()[:1]
    else:  # true_false
        correct = _norm(answer).startswith(_norm(question.answer_key)[:1])
    return correct, float(question.marks) if correct else 0.0


def keyword_overlap_grade(question: Question, answer: str) -> tuple[float, str]:
    """Fallback grader when the AI grader is unavailable: rubric keyword coverage."""
    rubric = list(question.options or []) or [question.answer_key]
    given = set(_norm(answer).split())
    covered = 0
    for point in rubric:
        words = {w for w in _norm(point).split() if len(w) > 3}
        if words and len(words & given) / len(words) >= 0.4:
            covered += 1
    fraction = covered / max(1, len(rubric))
    marks = round(question.marks * fraction, 1)
    return marks, f"Auto-graded by keyword coverage: {covered}/{len(rubric)} rubric points found (AI grader unavailable)."


async def grade_short_answer(llm: LLMProvider | None, question: Question, answer: str, source_text: str | None) -> tuple[float, str, bool]:
    if not answer or not answer.strip():
        return 0.0, "No answer given.", False
    if llm is None:
        marks, fb = keyword_overlap_grade(question, answer)
        return marks, fb, marks >= question.marks * 0.5
    rubric = "\n".join(f"- {p}" for p in (question.options or [])) or "- " + question.answer_key
    context = f"\nRelevant notes:\n{source_text[:3000]}\n" if source_text else ""
    prompt = [
        {
            "role": "system",
            "content": "You are a strict but fair university examiner. Grade the student's answer against the rubric and model answer. Award partial marks for partially correct points. Reply with JSON only: {\"marks\": number, \"feedback\": \"2-3 sentences: what was right, what was missing\"}.",
        },
        {
            "role": "user",
            "content": f"Question ({question.marks} marks): {question.prompt}\n\nModel answer: {question.answer_key}\n\nRubric:\n{rubric}\n{context}\nStudent answer: {answer}\n\nReturn marks between 0 and {question.marks}.",
        },
    ]
    try:
        result = await llm.complete(prompt, temperature=0.0, max_tokens=400, json_mode=True)
        data = extract_json(result.text)
        marks = float(data.get("marks", 0))
        marks = max(0.0, min(float(question.marks), round(marks * 2) / 2))
        feedback = str(data.get("feedback") or "").strip() or "Graded."
        return marks, feedback, marks >= question.marks * 0.5
    except (LLMError, ValueError, TypeError, AttributeError) as exc:
        log.warning("AI grading failed, using keyword fallback: %s", exc)
        marks, fb = keyword_overlap_grade(question, answer)
        return marks, fb, marks >= question.marks * 0.5


async def submit_attempt(
    db: Session,
    user: User,
    attempt: QuizAttempt,
    answers: dict[int, str | None],
    *,
    llm: LLMProvider | None,
    time_taken_sec: int | None = None,
) -> QuizAttempt:
    if attempt.submitted_at is not None:
        return attempt
    quiz = attempt.quiz
    from app.models import Chunk  # local import to avoid cycles

    total = 0.0
    topic_stats: dict[str, dict[str, float]] = {}
    for q in quiz.questions:
        given = answers.get(q.id)
        given = given.strip() if isinstance(given, str) else None
        feedback: str | None = None
        if q.qtype in ("mcq", "true_false"):
            correct, marks = grade_objective(q, given)
        else:
            source_text = None
            if q.source_chunk_ids:
                chunk = db.get(Chunk, q.source_chunk_ids[0])
                source_text = chunk.content if chunk and chunk.user_id == user.id else None
            marks, feedback, correct = await grade_short_answer(llm, q, given or "", source_text)
        total += marks
        db.add(AttemptAnswer(attempt_id=attempt.id, question_id=q.id, answer=given, is_correct=correct, marks_awarded=marks, ai_feedback=feedback))
        key = q.topic or quiz.topic or quiz.title
        stats = topic_stats.setdefault(key, {"correct": 0.0, "total": 0.0, "marks": 0.0, "max_marks": 0.0})
        stats["total"] += 1
        stats["correct"] += 1 if correct else 0
        stats["marks"] += marks
        stats["max_marks"] += q.marks

    attempt.score = round(total, 1)
    attempt.max_score = float(sum(q.marks for q in quiz.questions))
    attempt.percent = round(100.0 * attempt.score / attempt.max_score, 1) if attempt.max_score else 0.0
    attempt.submitted_at = _utcnow()
    attempt.time_taken_sec = time_taken_sec
    breakdown = {
        topic: {**s, "percent": round(100.0 * s["marks"] / s["max_marks"], 1) if s["max_marks"] else 0.0}
        for topic, s in topic_stats.items()
    }
    attempt.topic_breakdown = breakdown
    attempt.weak_topics = [t for t, s in sorted(breakdown.items(), key=lambda kv: kv[1]["percent"]) if s["percent"] < 60]
    attempt.feedback = _summarise(attempt)
    db.commit()
    db.refresh(attempt)
    log_activity(db, user.id, "quiz", ref_id=attempt.id, topic=quiz.topic, subject_id=quiz.subject_id, detail=quiz.title, value=attempt.percent)
    return attempt


def _summarise(attempt: QuizAttempt) -> str:
    pct = attempt.percent
    if pct >= 85:
        opener = "Excellent work"
    elif pct >= 60:
        opener = "Good effort"
    else:
        opener = "Keep going"
    weak = ", ".join(attempt.weak_topics or [])
    tail = f" Revise: {weak}." if weak else " No weak topics detected in this attempt."
    return f"{opener}: {attempt.score:g}/{attempt.max_score:g} ({pct:g}%).{tail}"


def attempt_history(db: Session, user: User, limit: int = 50) -> list[QuizAttempt]:
    return list(
        db.execute(
            select(QuizAttempt)
            .options(selectinload(QuizAttempt.quiz))
            .where(QuizAttempt.user_id == user.id, QuizAttempt.submitted_at.is_not(None))
            .order_by(QuizAttempt.submitted_at.desc())
            .limit(limit)
        ).scalars()
    )
