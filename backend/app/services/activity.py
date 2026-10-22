"""Study-activity logging used by the dashboard (streaks, recent activity)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import StudyActivity


def log_activity(
    db: Session,
    user_id: int,
    activity_type: str,
    *,
    ref_id: int | None = None,
    topic: str | None = None,
    subject_id: int | None = None,
    detail: str | None = None,
    value: float | None = None,
    commit: bool = True,
) -> StudyActivity:
    row = StudyActivity(
        user_id=user_id,
        activity_type=activity_type,
        ref_id=ref_id,
        topic=(topic or None),
        subject_id=subject_id,
        detail=(detail[:255] if detail else None),
        value=value,
    )
    db.add(row)
    if commit:
        db.commit()
    else:
        db.flush()
    return row
