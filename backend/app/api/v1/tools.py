from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ai_rate_limit, get_current_user
from app.models import User
from app.schemas.common import Message
from app.schemas.learning import ArtifactOut, ArtifactUpdate, ConceptMapRequest, GenerateBase, KeywordsRequest, StudyPlanRequest
from app.services import learning_tools
from app.services.dashboard_service import topic_accuracy
from app.services.llm import get_llm

router = APIRouter(prefix="/tools", tags=["learning-tools"])


@router.post("/summary", response_model=ArtifactOut, status_code=status.HTTP_201_CREATED)
async def summary(payload: GenerateBase, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> ArtifactOut:
    llm = get_llm(db, user)
    art = await learning_tools.generate_summary(db, user, llm, topic=payload.topic, document_ids=payload.document_ids, subject_id=payload.subject_id)
    return ArtifactOut.model_validate(art)


@router.post("/keywords", response_model=ArtifactOut, status_code=status.HTTP_201_CREATED)
async def keywords(payload: KeywordsRequest, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> ArtifactOut:
    llm = get_llm(db, user)
    art = await learning_tools.generate_keywords(db, user, llm, topic=payload.topic, document_ids=payload.document_ids, subject_id=payload.subject_id, count=payload.count)
    return ArtifactOut.model_validate(art)


@router.post("/concept-map", response_model=ArtifactOut, status_code=status.HTTP_201_CREATED)
async def concept_map(payload: ConceptMapRequest, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> ArtifactOut:
    llm = get_llm(db, user)
    art = await learning_tools.generate_concept_map(db, user, llm, topic=payload.topic, document_ids=payload.document_ids, subject_id=payload.subject_id, style=payload.style)
    return ArtifactOut.model_validate(art)


@router.post("/study-plan", response_model=ArtifactOut, status_code=status.HTTP_201_CREATED)
async def study_plan(payload: StudyPlanRequest, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> ArtifactOut:
    llm = get_llm(db, user)
    weak = [a["topic"] for a in topic_accuracy(db, user) if a["percent"] < 60][:6]
    art = await learning_tools.generate_study_plan(db, user, llm, exam_date=payload.exam_date, subject_ids=payload.subject_ids, daily_minutes=payload.daily_minutes, weak_topics=weak, focus=payload.focus)
    return ArtifactOut.model_validate(art)


@router.get("/artifacts", response_model=list[ArtifactOut])
def list_artifacts(kind: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ArtifactOut]:
    return [ArtifactOut.model_validate(a) for a in learning_tools.list_artifacts(db, user, kind=kind)]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
def get_artifact(artifact_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ArtifactOut:
    art = learning_tools.get_owned_artifact(db, user, artifact_id)
    if art is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return ArtifactOut.model_validate(art)


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactOut)
def update_artifact(artifact_id: int, payload: ArtifactUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ArtifactOut:
    art = learning_tools.get_owned_artifact(db, user, artifact_id)
    if art is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if art.kind != "study_plan":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only study plans can be edited")
    art.content = payload.content
    db.commit()
    db.refresh(art)
    return ArtifactOut.model_validate(art)


@router.delete("/artifacts/{artifact_id}", response_model=Message)
def delete_artifact(artifact_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Message:
    art = learning_tools.get_owned_artifact(db, user, artifact_id)
    if art is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(art)
    db.commit()
    return Message(detail="Deleted")
