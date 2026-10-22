"""SM-2 spaced-repetition scheduler (the algorithm behind SuperMemo/Anki).

``quality`` is the student's self-rating from 0 (blackout) to 5 (perfect).
The UI exposes four buttons mapped to: Again=1, Hard=3, Good=4, Easy=5.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

RATING_TO_QUALITY = {"again": 1, "hard": 3, "good": 4, "easy": 5}
MIN_EASE = 1.3
RELEARN_DELAY = timedelta(minutes=10)


@dataclass
class CardState:
    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0


@dataclass
class ScheduleResult:
    state: CardState
    due_at: datetime
    lapsed: bool


def schedule(state: CardState, quality: int, now: datetime) -> ScheduleResult:
    quality = max(0, min(5, int(quality)))
    ease = state.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ease = max(MIN_EASE, round(ease, 3))

    if quality < 3:
        new_state = CardState(ease_factor=ease, interval_days=0, repetitions=0, lapses=state.lapses + 1)
        return ScheduleResult(state=new_state, due_at=now + RELEARN_DELAY, lapsed=True)

    if state.repetitions == 0:
        interval = 1
    elif state.repetitions == 1:
        interval = 6
    else:
        interval = max(1, round(state.interval_days * ease))
    if quality == 5 and interval > 1:
        interval = round(interval * 1.3)  # "easy" bonus
    elif quality == 3 and interval > 1:
        interval = max(1, round(interval * 0.8))  # "hard" penalty

    new_state = CardState(ease_factor=ease, interval_days=interval, repetitions=state.repetitions + 1, lapses=state.lapses)
    return ScheduleResult(state=new_state, due_at=now + timedelta(days=interval), lapsed=False)


def quality_from_rating(rating: str | int) -> int:
    if isinstance(rating, int):
        return max(0, min(5, rating))
    try:
        return RATING_TO_QUALITY[str(rating).lower()]
    except KeyError as exc:
        raise ValueError("rating must be one of again, hard, good, easy (or 0-5)") from exc
