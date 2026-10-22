"""Flashcard decks: AI generation from notes and SM-2 review scheduling."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import CardReview, Flashcard, FlashcardDeck, User
from app.services.activity import log_activity
from app.services.generation import GenerationError, context_text, gather_context, generate_json, subject_hint
from app.services.llm import LLMProvider
from app.services.sm2 import CardState, quality_from_rating, schedule

MASTERED_INTERVAL_DAYS = 21


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _instructions(topic: str | None, count: int, subject: str | None) -> str:
    focus = f"on '{topic}'" if topic else "covering the key facts in the notes"
    subj = f" for {subject}" if subject else ""
    return f"""Create {count} flashcards{subj} {focus} for active recall.
Rules:
- "front" is a precise question or term (max 20 words); "back" is the answer (max 60 words), exam-ready.
- Cover definitions, formulas, comparisons, steps of algorithms and common pitfalls. No duplicates.
- "hint" is an optional short nudge; "topic" is a 2-5 word label; "source" is the notes number used, or null.
Return JSON: {{"title": "...", "cards": [{{"front": "...", "back": "...", "hint": "...", "topic": "...", "source": 1}}]}}"""


async def generate_deck(
    db: Session,
    user: User,
    llm: LLMProvider,
    *,
    topic: str | None,
    document_ids: list[int] | None,
    subject_id: int | None,
    count: int = 12,
) -> FlashcardDeck:
    count = max(4, min(40, count))
    sources = gather_context(db, user.id, topic=topic, document_ids=document_ids, top_k=10)
    if not sources and not topic:
        raise GenerationError("Pick a topic or upload notes first so the deck has something to draw from.")
    data, result = await generate_json(llm, _instructions(topic, count, subject_hint(db, subject_id)), context=context_text(sources), max_tokens=5000)
    raw_cards = data.get("cards") if isinstance(data, dict) else data
    if not isinstance(raw_cards, list):
        raise GenerationError("The model returned no cards. Try again.")
    cards: list[Flashcard] = []
    seen: set[str] = set()
    for raw in raw_cards:
        if not isinstance(raw, dict):
            continue
        front = str(raw.get("front") or raw.get("question") or "").strip()
        back = str(raw.get("back") or raw.get("answer") or "").strip()
        if len(front) < 3 or len(back) < 2 or front.lower() in seen:
            continue
        seen.add(front.lower())
        src_idx = raw.get("source")
        chunk_id = None
        try:
            if src_idx is not None and 1 <= int(src_idx) <= len(sources):
                chunk_id = sources[int(src_idx) - 1].chunk_id
        except (TypeError, ValueError):
            pass
        cards.append(
            Flashcard(
                user_id=user.id,
                front=front[:1000],
                back=back[:2000],
                hint=(str(raw.get("hint") or "").strip()[:300] or None),
                topic=(str(raw.get("topic") or topic or "").strip()[:255] or None),
                source_chunk_id=chunk_id,
                due_at=_utcnow(),
            )
        )
    if len(cards) < 2:
        raise GenerationError("Could not build a valid deck from the model output. Try again.")
    title = (data.get("title") if isinstance(data, dict) else None) or (f"{topic} flashcards" if topic else "Flashcards from notes")
    deck = FlashcardDeck(user_id=user.id, title=str(title)[:200], subject_id=subject_id, topic=topic, document_ids=document_ids or None)
    db.add(deck)
    db.flush()
    for c in cards:
        c.deck_id = deck.id
        db.add(c)
    db.commit()
    db.refresh(deck)
    log_activity(db, user.id, "flashcards", ref_id=deck.id, topic=topic, subject_id=subject_id, detail=deck.title, value=len(cards))
    return deck


def list_decks(db: Session, user: User) -> list[dict]:
    now = _utcnow()
    decks = db.execute(
        select(FlashcardDeck).options(selectinload(FlashcardDeck.cards)).where(FlashcardDeck.user_id == user.id).order_by(FlashcardDeck.created_at.desc())
    ).scalars().all()
    out = []
    for deck in decks:
        cards = deck.cards
        out.append(
            {
                "deck": deck,
                "card_count": len(cards),
                "due_count": sum(1 for c in cards if c.due_at <= now),
                "mastered_count": sum(1 for c in cards if c.interval_days >= MASTERED_INTERVAL_DAYS),
                "new_count": sum(1 for c in cards if c.repetitions == 0 and c.last_reviewed_at is None),
            }
        )
    return out


def get_owned_deck(db: Session, user: User, deck_id: int) -> FlashcardDeck | None:
    return db.execute(
        select(FlashcardDeck).options(selectinload(FlashcardDeck.cards)).where(FlashcardDeck.id == deck_id, FlashcardDeck.user_id == user.id)
    ).scalar_one_or_none()


def due_cards(db: Session, user: User, *, deck_id: int | None = None, limit: int = 30, include_new: bool = True) -> list[Flashcard]:
    now = _utcnow()
    stmt = select(Flashcard).where(Flashcard.user_id == user.id, Flashcard.due_at <= now)
    if deck_id:
        stmt = stmt.where(Flashcard.deck_id == deck_id)
    if not include_new:
        stmt = stmt.where(Flashcard.repetitions > 0)
    stmt = stmt.order_by(Flashcard.due_at.asc(), Flashcard.id.asc()).limit(limit)
    return list(db.execute(stmt).scalars())


def review_card(db: Session, user: User, card: Flashcard, rating: str | int) -> Flashcard:
    quality = quality_from_rating(rating)
    now = _utcnow()
    before = card.interval_days
    result = schedule(CardState(card.ease_factor, card.interval_days, card.repetitions, card.lapses), quality, now)
    card.ease_factor = result.state.ease_factor
    card.interval_days = result.state.interval_days
    card.repetitions = result.state.repetitions
    card.lapses = result.state.lapses
    card.due_at = result.due_at
    card.last_reviewed_at = now
    db.add(CardReview(flashcard_id=card.id, user_id=user.id, rating=quality, interval_before=before, interval_after=card.interval_days, reviewed_at=now))
    db.commit()
    db.refresh(card)
    log_activity(db, user.id, "review", ref_id=card.id, topic=card.topic, detail=card.front[:120], value=float(quality))
    return card


def flashcard_stats(db: Session, user: User) -> dict:
    now = _utcnow()
    total = db.scalar(select(func.count(Flashcard.id)).where(Flashcard.user_id == user.id)) or 0
    due = db.scalar(select(func.count(Flashcard.id)).where(Flashcard.user_id == user.id, Flashcard.due_at <= now)) or 0
    mastered = db.scalar(select(func.count(Flashcard.id)).where(Flashcard.user_id == user.id, Flashcard.interval_days >= MASTERED_INTERVAL_DAYS)) or 0
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reviewed_today = db.scalar(select(func.count(CardReview.id)).where(CardReview.user_id == user.id, CardReview.reviewed_at >= day_start)) or 0
    upcoming = db.scalar(
        select(func.count(Flashcard.id)).where(Flashcard.user_id == user.id, Flashcard.due_at > now, Flashcard.due_at <= now + timedelta(days=7))
    ) or 0
    return {"total": int(total), "due": int(due), "mastered": int(mastered), "reviewed_today": int(reviewed_today), "due_next_7_days": int(upcoming)}
