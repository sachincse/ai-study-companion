from datetime import datetime, timedelta

import pytest

from app.services.sm2 import CardState, quality_from_rating, schedule


def test_intervals_grow_with_good_ratings():
    now = datetime(2026, 1, 1)
    state = CardState()
    r1 = schedule(state, 4, now)
    assert r1.state.interval_days == 1 and r1.state.repetitions == 1
    r2 = schedule(r1.state, 4, now)
    assert r2.state.interval_days == 6 and r2.state.repetitions == 2
    r3 = schedule(r2.state, 4, now)
    assert r3.state.interval_days == round(6 * r2.state.ease_factor)
    assert r3.due_at == now + timedelta(days=r3.state.interval_days)
    assert not r3.lapsed


def test_again_resets_and_counts_lapse():
    now = datetime(2026, 1, 1)
    state = CardState(ease_factor=2.5, interval_days=15, repetitions=4)
    r = schedule(state, 1, now)
    assert r.lapsed and r.state.repetitions == 0 and r.state.lapses == 1
    assert r.due_at == now + timedelta(minutes=10)
    assert r.state.ease_factor < 2.5


def test_ease_never_drops_below_floor():
    now = datetime(2026, 1, 1)
    state = CardState(ease_factor=1.3)
    for _ in range(5):
        state = schedule(state, 0, now).state
    assert state.ease_factor == 1.3


def test_easy_is_longer_than_hard():
    now = datetime(2026, 1, 1)
    base = CardState(ease_factor=2.5, interval_days=10, repetitions=3)
    easy = schedule(base, 5, now).state.interval_days
    hard = schedule(base, 3, now).state.interval_days
    good = schedule(base, 4, now).state.interval_days
    assert hard < good < easy


def test_rating_mapping():
    assert quality_from_rating("again") == 1
    assert quality_from_rating("easy") == 5
    assert quality_from_rating(3) == 3
    with pytest.raises(ValueError):
        quality_from_rating("meh")
