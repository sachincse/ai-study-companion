from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ai_rate_limit, get_current_user
from app.models import User
from app.schemas.common import Message
from app.schemas.learning import (
    AttemptHistoryItem,
    AttemptOut,
    AttemptResult,
    QuestionRevealed,
    QuizGenerateRequest,
    QuizOut,
    QuizSummary,
    SubmitAttemptRequest,
)
from app.services import quiz_service
from app.services.llm import LLMError, get_llm

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.post("/generate", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
async def generate(payload: QuizGenerateRequest, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> QuizOut:
    llm = get_llm(db, user)
    quiz = await quiz_service.generate_quiz(
        db, user, llm,
        topic=payload.topic, document_ids=payload.document_ids, subject_id=payload.subject_id,
        count=payload.count, difficulty=payload.difficulty, types=payload.types, time_limit_sec=payload.time_limit_sec,
    )
    return QuizOut.model_validate(quiz_service.get_owned_quiz(db, user, quiz.id))


@router.get("", response_model=list[QuizSummary])
def list_quizzes(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[QuizSummary]:
    out = []
    for quiz in quiz_service.list_quizzes(db, user):
        done = [a for a in quiz.attempts if a.submitted_at is not None]
        done.sort(key=lambda a: a.submitted_at)
        out.append(
            QuizSummary(
                id=quiz.id, title=quiz.title, topic=quiz.topic, subject_id=quiz.subject_id, difficulty=quiz.difficulty,
                question_count=quiz.question_count, time_limit_sec=quiz.time_limit_sec, created_at=quiz.created_at,
                attempt_count=len(done), best_percent=max((a.percent for a in done), default=None), last_percent=done[-1].percent if done else None,
            )
        )
    return out


@router.get("/attempts", response_model=list[AttemptHistoryItem])
def attempts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[AttemptHistoryItem]:
    return [
        AttemptHistoryItem(attempt_id=a.id, quiz_id=a.quiz_id, title=a.quiz.title, percent=a.percent, score=a.score, max_score=a.max_score, submitted_at=a.submitted_at)
        for a in quiz_service.attempt_history(db, user)
    ]


@router.get("/attempts/{attempt_id}", response_model=AttemptResult)
def get_attempt(attempt_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AttemptResult:
    attempt = quiz_service.get_owned_attempt(db, user, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    return _attempt_result(attempt)


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptResult)
async def submit(attempt_id: int, payload: SubmitAttemptRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AttemptResult:
    attempt = quiz_service.get_owned_attempt(db, user, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    needs_ai = any(q.qtype == "short_answer" for q in attempt.quiz.questions)
    llm = None
    if needs_ai:
        try:
            llm = get_llm(db, user)
        except LLMError:
            llm = None  # keyword fallback grader
    attempt = await quiz_service.submit_attempt(db, user, attempt, payload.answers, llm=llm, time_taken_sec=payload.time_taken_sec)
    return _attempt_result(quiz_service.get_owned_attempt(db, user, attempt.id))


@router.get("/{quiz_id}", response_model=QuizOut)
def get_quiz(quiz_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> QuizOut:
    quiz = quiz_service.get_owned_quiz(db, user, quiz_id)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    return QuizOut.model_validate(quiz)


@router.delete("/{quiz_id}", response_model=Message)
def delete_quiz(quiz_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Message:
    quiz = quiz_service.get_owned_quiz(db, user, quiz_id)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    db.delete(quiz)
    db.commit()
    return Message(detail="Quiz deleted")


@router.post("/{quiz_id}/attempts", response_model=AttemptOut, status_code=status.HTTP_201_CREATED)
def start_attempt(quiz_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AttemptOut:
    quiz = quiz_service.get_owned_quiz(db, user, quiz_id)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    return AttemptOut.model_validate(quiz_service.start_attempt(db, user, quiz))


def _attempt_result(attempt) -> AttemptResult:  # noqa: ANN001
    data = AttemptResult.model_validate(attempt)
    data.quiz_title = attempt.quiz.title
    if attempt.submitted_at is not None:
        data.questions = [QuestionRevealed.model_validate(q) for q in attempt.quiz.questions]
    return data
