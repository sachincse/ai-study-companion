"""Dashboard analytics: progress, accuracy by topic, streaks and recommendations."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AttemptAnswer, Document, Question, Quiz, QuizAttempt, StudyActivity, Subject, Topic, TopicProgress, User
from app.services.chat_service import chat_stats
from app.services.document_service import document_stats
from app.services.flashcard_service import flashcard_stats

WEAK_THRESHOLD = 60.0


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def topic_accuracy(db: Session, user: User, days: int = 60) -> list[dict]:
    since = _utcnow() - timedelta(days=days)
    rows = db.execute(
        select(Question.topic, Quiz.topic, Quiz.title, AttemptAnswer.is_correct, AttemptAnswer.marks_awarded, Question.marks)
        .join(Question, Question.id == AttemptAnswer.question_id)
        .join(QuizAttempt, QuizAttempt.id == AttemptAnswer.attempt_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(QuizAttempt.user_id == user.id, QuizAttempt.submitted_at.is_not(None), QuizAttempt.submitted_at >= since)
    ).all()
    agg: dict[str, dict[str, float]] = defaultdict(lambda: {"correct": 0.0, "total": 0.0, "marks": 0.0, "max_marks": 0.0})
    for q_topic, quiz_topic, quiz_title, is_correct, marks, max_marks in rows:
        key = (q_topic or quiz_topic or quiz_title or "General").strip()
        a = agg[key]
        a["total"] += 1
        a["correct"] += 1 if is_correct else 0
        a["marks"] += float(marks or 0)
        a["max_marks"] += float(max_marks or 1)
    out = []
    for topic, a in agg.items():
        pct = round(100.0 * a["marks"] / a["max_marks"], 1) if a["max_marks"] else 0.0
        out.append({"topic": topic, "questions": int(a["total"]), "correct": int(a["correct"]), "percent": pct})
    out.sort(key=lambda x: (x["percent"], -x["questions"]))
    return out


def streak(db: Session, user: User, window_days: int = 14) -> dict:
    today = _utcnow().date()
    since = datetime.combine(today - timedelta(days=window_days + 1), datetime.min.time())
    rows = db.execute(
        select(func.date(StudyActivity.created_at), func.count(StudyActivity.id))
        .where(StudyActivity.user_id == user.id, StudyActivity.created_at >= since)
        .group_by(func.date(StudyActivity.created_at))
    ).all()
    counts: dict[date, int] = {}
    for d, n in rows:
        d_obj = date.fromisoformat(str(d)[:10])
        counts[d_obj] = int(n)
    # current streak: consecutive days ending today (or yesterday if nothing yet today)
    current = 0
    cursor = today if counts.get(today) else today - timedelta(days=1)
    while counts.get(cursor):
        current += 1
        cursor -= timedelta(days=1)
    series = [
        {"date": (today - timedelta(days=i)).isoformat(), "count": counts.get(today - timedelta(days=i), 0)}
        for i in range(window_days - 1, -1, -1)
    ]
    return {"current": current, "active_today": bool(counts.get(today)), "last_14_days": series}


def syllabus_progress(db: Session, user: User) -> list[dict]:
    totals = dict(db.execute(select(Topic.subject_id, func.count(Topic.id)).group_by(Topic.subject_id)).all())
    done = dict(
        db.execute(
            select(Topic.subject_id, func.count(TopicProgress.id))
            .join(Topic, Topic.id == TopicProgress.topic_id)
            .where(TopicProgress.user_id == user.id, TopicProgress.completed.is_(True))
            .group_by(Topic.subject_id)
        ).all()
    )
    doc_subjects = {
        sid for (sid,) in db.execute(select(Document.subject_id).where(Document.user_id == user.id, Document.subject_id.is_not(None))).all()
    }
    subjects = db.execute(select(Subject).order_by(Subject.semester, Subject.code)).scalars().all()
    out = []
    for s in subjects:
        total = int(totals.get(s.id, 0))
        completed = int(done.get(s.id, 0))
        if completed == 0 and s.id not in doc_subjects:
            continue
        out.append(
            {
                "subject_id": s.id,
                "code": s.code,
                "name": s.name,
                "semester": s.semester,
                "topics": total,
                "completed": completed,
                "percent": round(100.0 * completed / total, 1) if total else 0.0,
            }
        )
    return out


def recent_attempts(db: Session, user: User, limit: int = 10) -> list[dict]:
    rows = db.execute(
        select(QuizAttempt, Quiz.title)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(QuizAttempt.user_id == user.id, QuizAttempt.submitted_at.is_not(None))
        .order_by(QuizAttempt.submitted_at.desc())
        .limit(limit)
    ).all()
    out = [
        {"attempt_id": a.id, "quiz_id": a.quiz_id, "title": title, "percent": a.percent, "score": a.score, "max_score": a.max_score, "submitted_at": a.submitted_at}
        for a, title in rows
    ]
    out.reverse()
    return out


def recent_activity(db: Session, user: User, limit: int = 12) -> list[dict]:
    rows = db.execute(
        select(StudyActivity).where(StudyActivity.user_id == user.id).order_by(StudyActivity.created_at.desc()).limit(limit)
    ).scalars().all()
    labels = {
        "chat": "Asked the tutor",
        "upload": "Indexed notes",
        "quiz": "Completed a quiz",
        "quiz_generated": "Generated a quiz",
        "review": "Reviewed a flashcard",
        "flashcards": "Created a flashcard deck",
        "summary": "Generated a summary",
        "keywords": "Extracted keywords",
        "concept_map": "Built a concept map",
        "study_plan": "Created a study plan",
        "syllabus": "Updated syllabus progress",
    }
    return [
        {
            "id": a.id,
            "type": a.activity_type,
            "label": labels.get(a.activity_type, a.activity_type.replace("_", " ").title()),
            "detail": a.detail,
            "topic": a.topic,
            "value": a.value,
            "created_at": a.created_at,
        }
        for a in rows
    ]


def recommendations(db: Session, user: User, *, weak: list[dict], cards: dict, docs: dict, attempts: list[dict], streak_info: dict) -> list[dict]:
    recs: list[dict] = []
    if docs["ready"] == 0:
        recs.append({"title": "Upload your first notes", "detail": "The tutor, quizzes and flashcards all work best when grounded in your own material.", "action": "notes", "params": {}})
    for w in weak[:2]:
        recs.append({"title": f"Retake a short quiz on {w['topic']}", "detail": f"Only {w['percent']:g}% on the last attempt(s). A focused 5-question quiz will help.", "action": "quiz", "params": {"topic": w["topic"]}})
    if cards["due"] > 0:
        recs.append({"title": f"Review {cards['due']} flashcard{'s' if cards['due'] != 1 else ''} due now", "detail": "Spaced repetition only works if you clear the queue.", "action": "flashcards", "params": {}})
    if docs["ready"] > 0 and not attempts:
        recs.append({"title": "Take your first quiz", "detail": "Generate a quiz from your notes to find weak spots early.", "action": "quiz", "params": {}})
    if not streak_info["active_today"]:
        recs.append({"title": "Keep your streak alive", "detail": "Ask one question or review a few cards today.", "action": "chat", "params": {}})
    if docs["ready"] > 0 and cards["total"] == 0:
        recs.append({"title": "Create flashcards from your notes", "detail": "Turn definitions and formulas into recall cards.", "action": "flashcards", "params": {}})
    return recs[:4]


def overview(db: Session, user: User) -> dict:
    docs = document_stats(db, user)
    chats = chat_stats(db, user)
    cards = flashcard_stats(db, user)
    accuracy = topic_accuracy(db, user)
    weak = [a for a in accuracy if a["percent"] < WEAK_THRESHOLD and a["questions"] >= 1]
    strong = [a for a in accuracy if a["percent"] >= 80 and a["questions"] >= 2]
    attempts = recent_attempts(db, user)
    attempt_count = db.scalar(select(func.count(QuizAttempt.id)).where(QuizAttempt.user_id == user.id, QuizAttempt.submitted_at.is_not(None))) or 0
    avg = round(sum(a["percent"] for a in attempts) / len(attempts), 1) if attempts else None
    best = max((a["percent"] for a in attempts), default=None)
    streak_info = streak(db, user)
    progress = syllabus_progress(db, user)
    overall_pct = round(sum(p["completed"] for p in progress) / max(1, sum(p["topics"] for p in progress)) * 100, 1) if progress else 0.0
    return {
        "documents": docs,
        "chats": chats,
        "flashcards": cards,
        "quizzes": {"attempts": int(attempt_count), "average_percent": avg, "best_percent": best, "recent": attempts},
        "topic_accuracy": accuracy[:12],
        "weak_topics": weak[:6],
        "strong_topics": strong[:6],
        "streak": streak_info,
        "syllabus": {"overall_percent": overall_pct, "subjects": progress},
        "recent_activity": recent_activity(db, user),
        "recommendations": recommendations(db, user, weak=weak, cards=cards, docs=docs, attempts=attempts, streak_info=streak_info),
    }
