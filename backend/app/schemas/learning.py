from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import OptUtcDatetime, ORMModel, UtcDatetime


# ------------------------------------------------------------------ generation
class GenerateBase(BaseModel):
    topic: str | None = Field(default=None, max_length=255)
    document_ids: list[int] | None = None
    subject_id: int | None = None


class QuizGenerateRequest(GenerateBase):
    count: int = Field(default=8, ge=3, le=25)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    types: list[str] = Field(default_factory=lambda: ["mcq", "true_false", "short_answer"])
    time_limit_sec: int | None = Field(default=None, ge=60, le=7200)


class FlashcardGenerateRequest(GenerateBase):
    count: int = Field(default=12, ge=4, le=40)


class KeywordsRequest(GenerateBase):
    count: int = Field(default=15, ge=5, le=40)


class ConceptMapRequest(GenerateBase):
    style: str = Field(default="concept_map", pattern="^(concept_map|flowchart)$")


class StudyPlanRequest(BaseModel):
    exam_date: date
    subject_ids: list[int] = Field(min_length=1)
    daily_minutes: int = Field(default=120, ge=30, le=720)
    focus: str | None = Field(default=None, max_length=300)


# ----------------------------------------------------------------------- quizzes
class QuestionPublic(ORMModel):
    id: int
    position: int
    qtype: str
    prompt: str
    options: list[str] | None = None
    topic: str | None = None
    marks: int
    source_page: int | None = None


class QuestionRevealed(QuestionPublic):
    answer_key: str
    explanation: str | None = None


class QuizOut(ORMModel):
    id: int
    title: str
    subject_id: int | None = None
    topic: str | None = None
    document_ids: list[int] | None = None
    difficulty: str
    question_count: int
    time_limit_sec: int | None = None
    provider: str | None = None
    model: str | None = None
    created_at: UtcDatetime
    questions: list[QuestionPublic] = []


class QuizSummary(ORMModel):
    id: int
    title: str
    topic: str | None = None
    subject_id: int | None = None
    difficulty: str
    question_count: int
    time_limit_sec: int | None = None
    created_at: UtcDatetime
    attempt_count: int = 0
    best_percent: float | None = None
    last_percent: float | None = None


class AttemptOut(ORMModel):
    id: int
    quiz_id: int
    started_at: UtcDatetime
    submitted_at: OptUtcDatetime = None
    max_score: float


class SubmitAttemptRequest(BaseModel):
    answers: dict[int, str | None]
    time_taken_sec: int | None = Field(default=None, ge=0)


class AnswerResult(ORMModel):
    question_id: int
    answer: str | None = None
    is_correct: bool | None = None
    marks_awarded: float
    ai_feedback: str | None = None


class AttemptResult(ORMModel):
    id: int
    quiz_id: int
    quiz_title: str = ""
    started_at: UtcDatetime
    submitted_at: OptUtcDatetime = None
    score: float
    max_score: float
    percent: float
    time_taken_sec: int | None = None
    topic_breakdown: dict[str, Any] | None = None
    weak_topics: list[str] | None = None
    feedback: str | None = None
    answers: list[AnswerResult] = []
    questions: list[QuestionRevealed] = []


class AttemptHistoryItem(BaseModel):
    attempt_id: int
    quiz_id: int
    title: str
    percent: float
    score: float
    max_score: float
    submitted_at: OptUtcDatetime = None


# -------------------------------------------------------------------- flashcards
class FlashcardOut(ORMModel):
    id: int
    deck_id: int
    front: str
    back: str
    hint: str | None = None
    topic: str | None = None
    ease_factor: float
    interval_days: int
    repetitions: int
    lapses: int
    due_at: UtcDatetime
    last_reviewed_at: OptUtcDatetime = None


class DeckOut(ORMModel):
    id: int
    title: str
    subject_id: int | None = None
    topic: str | None = None
    document_ids: list[int] | None = None
    created_at: UtcDatetime
    card_count: int = 0
    due_count: int = 0
    mastered_count: int = 0
    new_count: int = 0


class DeckDetail(DeckOut):
    cards: list[FlashcardOut] = []


class ReviewRequest(BaseModel):
    rating: str = Field(pattern="^(again|hard|good|easy)$")


class ManualCardRequest(BaseModel):
    front: str = Field(min_length=1, max_length=1000)
    back: str = Field(min_length=1, max_length=2000)
    hint: str | None = Field(default=None, max_length=300)
    topic: str | None = Field(default=None, max_length=255)


class FlashcardStats(BaseModel):
    total: int
    due: int
    mastered: int
    reviewed_today: int
    due_next_7_days: int


# ----------------------------------------------------------------------- tools
class ArtifactOut(ORMModel):
    id: int
    kind: str
    title: str
    topic: str | None = None
    subject_id: int | None = None
    document_ids: list[int] | None = None
    content: Any = None
    sources: list[dict] | None = None
    provider: str | None = None
    model: str | None = None
    created_at: UtcDatetime


class ArtifactUpdate(BaseModel):
    content: Any
