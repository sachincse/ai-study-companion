from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ai_rate_limit, get_current_user
from app.models import Flashcard, User
from app.schemas.common import Message
from app.schemas.learning import DeckDetail, DeckOut, FlashcardGenerateRequest, FlashcardOut, FlashcardStats, ManualCardRequest, ReviewRequest
from app.services import flashcard_service
from app.services.llm import get_llm

router = APIRouter(prefix="/flashcards", tags=["flashcards"])


def _deck_out(item: dict) -> DeckOut:
    deck = item["deck"]
    return DeckOut(
        id=deck.id, title=deck.title, subject_id=deck.subject_id, topic=deck.topic, document_ids=deck.document_ids, created_at=deck.created_at,
        card_count=item["card_count"], due_count=item["due_count"], mastered_count=item["mastered_count"], new_count=item["new_count"],
    )


@router.post("/generate", response_model=DeckDetail, status_code=status.HTTP_201_CREATED)
async def generate(payload: FlashcardGenerateRequest, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> DeckDetail:
    llm = get_llm(db, user)
    deck = await flashcard_service.generate_deck(db, user, llm, topic=payload.topic, document_ids=payload.document_ids, subject_id=payload.subject_id, count=payload.count)
    return get_deck(deck.id, user, db)


@router.get("/decks", response_model=list[DeckOut])
def list_decks(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[DeckOut]:
    return [_deck_out(item) for item in flashcard_service.list_decks(db, user)]


@router.get("/stats", response_model=FlashcardStats)
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FlashcardStats:
    return FlashcardStats(**flashcard_service.flashcard_stats(db, user))


@router.get("/due", response_model=list[FlashcardOut])
def due(deck_id: int | None = None, limit: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[FlashcardOut]:
    return [FlashcardOut.model_validate(c) for c in flashcard_service.due_cards(db, user, deck_id=deck_id, limit=min(limit, 100))]


@router.get("/decks/{deck_id}", response_model=DeckDetail)
def get_deck(deck_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DeckDetail:
    deck = flashcard_service.get_owned_deck(db, user, deck_id)
    if deck is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deck not found")
    summary = next((i for i in flashcard_service.list_decks(db, user) if i["deck"].id == deck.id), None)
    base = _deck_out(summary).model_dump() if summary else DeckOut.model_validate(deck).model_dump()
    return DeckDetail(**base, cards=[FlashcardOut.model_validate(c) for c in deck.cards])


@router.delete("/decks/{deck_id}", response_model=Message)
def delete_deck(deck_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Message:
    deck = flashcard_service.get_owned_deck(db, user, deck_id)
    if deck is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deck not found")
    db.delete(deck)
    db.commit()
    return Message(detail="Deck deleted")


@router.post("/decks/{deck_id}/cards", response_model=FlashcardOut, status_code=status.HTTP_201_CREATED)
def add_card(deck_id: int, payload: ManualCardRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FlashcardOut:
    deck = flashcard_service.get_owned_deck(db, user, deck_id)
    if deck is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deck not found")
    card = Flashcard(deck_id=deck.id, user_id=user.id, front=payload.front, back=payload.back, hint=payload.hint, topic=payload.topic or deck.topic)
    db.add(card)
    db.commit()
    db.refresh(card)
    return FlashcardOut.model_validate(card)


@router.post("/cards/{card_id}/review", response_model=FlashcardOut)
def review(card_id: int, payload: ReviewRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FlashcardOut:
    card = db.get(Flashcard, card_id)
    if card is None or card.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")
    return FlashcardOut.model_validate(flashcard_service.review_card(db, user, card, payload.rating))


@router.delete("/cards/{card_id}", response_model=Message)
def delete_card(card_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Message:
    card = db.get(Flashcard, card_id)
    if card is None or card.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")
    db.delete(card)
    db.commit()
    return Message(detail="Card deleted")
