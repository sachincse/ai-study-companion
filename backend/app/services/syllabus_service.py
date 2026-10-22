"""AKTU syllabus: seeded from ``data/syllabus/*.yaml`` and tracked per student."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import Subject, Topic, TopicProgress, User
from app.services.activity import log_activity

log = logging.getLogger(__name__)


def load_syllabus_files(directory: Path | None = None) -> list[dict]:
    directory = directory or (get_settings().data_dir / "syllabus")
    items: list[dict] = []
    if not directory.exists():
        return items
    for path in sorted(directory.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict) and data.get("code"):
            items.append(data)
    return items


def seed_syllabus(db: Session, directory: Path | None = None) -> int:
    """Upsert subjects + topics from YAML. Returns number of subjects processed."""
    count = 0
    for data in load_syllabus_files(directory):
        code = str(data["code"]).upper().strip()
        subject = db.execute(select(Subject).where(Subject.code == code)).scalar_one_or_none()
        if subject is None:
            subject = Subject(code=code, name=data.get("name", code), semester=int(data.get("semester", 0)))
            db.add(subject)
            db.flush()
        subject.name = data.get("name", subject.name)
        subject.semester = int(data.get("semester", subject.semester or 0))
        subject.branch = data.get("branch", "CSE")
        subject.credits = data.get("credits")
        subject.description = data.get("description")
        existing = {(t.unit, t.name): t for t in db.execute(select(Topic).where(Topic.subject_id == subject.id)).scalars()}
        order = 0
        for unit in data.get("units", []):
            unit_no = int(unit.get("number", 0))
            unit_title = str(unit.get("title", f"Unit {unit_no}"))
            for name in unit.get("topics", []):
                name = str(name).strip()
                if not name:
                    continue
                topic = existing.get((unit_no, name))
                if topic is None:
                    topic = Topic(subject_id=subject.id, unit=unit_no, unit_title=unit_title, name=name, order_index=order)
                    db.add(topic)
                else:
                    topic.unit_title = unit_title
                    topic.order_index = order
                order += 1
        count += 1
    db.commit()
    return count


def list_subjects(db: Session, user: User | None = None, semester: int | None = None) -> list[dict]:
    stmt = select(Subject).order_by(Subject.semester, Subject.code)
    if semester:
        stmt = stmt.where(Subject.semester == semester)
    subjects = db.execute(stmt).scalars().all()
    totals = dict(db.execute(select(Topic.subject_id, func.count(Topic.id)).group_by(Topic.subject_id)).all())
    done: dict[int, int] = {}
    if user is not None:
        done = dict(
            db.execute(
                select(Topic.subject_id, func.count(TopicProgress.id))
                .join(Topic, Topic.id == TopicProgress.topic_id)
                .where(TopicProgress.user_id == user.id, TopicProgress.completed.is_(True))
                .group_by(Topic.subject_id)
            ).all()
        )
    out = []
    for s in subjects:
        total = int(totals.get(s.id, 0))
        completed = int(done.get(s.id, 0))
        out.append(
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "semester": s.semester,
                "branch": s.branch,
                "credits": s.credits,
                "description": s.description,
                "topic_count": total,
                "completed_count": completed,
                "percent": round(100.0 * completed / total, 1) if total else 0.0,
            }
        )
    return out


def subject_detail(db: Session, user: User | None, subject_id: int) -> dict | None:
    subject = db.execute(select(Subject).options(selectinload(Subject.topics)).where(Subject.id == subject_id)).scalar_one_or_none()
    if subject is None:
        return None
    completed: set[int] = set()
    if user is not None:
        completed = {
            tid for (tid,) in db.execute(select(TopicProgress.topic_id).where(TopicProgress.user_id == user.id, TopicProgress.completed.is_(True))).all()
        }
    units: dict[int, dict] = {}
    for t in subject.topics:
        unit = units.setdefault(t.unit, {"number": t.unit, "title": t.unit_title, "topics": []})
        unit["topics"].append({"id": t.id, "name": t.name, "completed": t.id in completed})
    total = len(subject.topics)
    done = sum(1 for t in subject.topics if t.id in completed)
    return {
        "id": subject.id,
        "code": subject.code,
        "name": subject.name,
        "semester": subject.semester,
        "branch": subject.branch,
        "credits": subject.credits,
        "description": subject.description,
        "units": [units[k] for k in sorted(units)],
        "topic_count": total,
        "completed_count": done,
        "percent": round(100.0 * done / total, 1) if total else 0.0,
    }


def set_topic_progress(db: Session, user: User, topic_id: int, completed: bool) -> TopicProgress:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise ValueError("Unknown topic")
    row = db.execute(select(TopicProgress).where(TopicProgress.user_id == user.id, TopicProgress.topic_id == topic_id)).scalar_one_or_none()
    if row is None:
        row = TopicProgress(user_id=user.id, topic_id=topic_id, completed=completed)
        db.add(row)
    else:
        row.completed = completed
    db.commit()
    if completed:
        log_activity(db, user.id, "syllabus", ref_id=topic_id, topic=topic.name, subject_id=topic.subject_id, detail=topic.name)
    return row


def unit_topics(db: Session, subject_id: int, unit: int) -> list[str]:
    return [t.name for t in db.execute(select(Topic).where(Topic.subject_id == subject_id, Topic.unit == unit).order_by(Topic.order_index)).scalars()]
