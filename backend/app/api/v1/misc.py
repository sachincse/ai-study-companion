"""Dashboard, syllabus, video resources, settings and system endpoints."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.core.database import fts_available, get_db
from app.core.deps import ai_rate_limit, bearer_scheme, get_current_user
from app.core.security import encrypt_secret, mask_secret
from app.models import Chunk, Subject, User, UserSettings
from app.schemas.settings import (
    LLMSettingsUpdate,
    LLMTestRequest,
    LLMTestResponse,
    ModelListRequest,
    ModelListResponse,
    ProviderInfo,
    ProvidersResponse,
    ResolvedLLMOut,
)
from app.services import dashboard_service, syllabus_service, video_service
from app.services.embeddings import embedder_status
from app.services.llm import CONFIGURABLE_BASE_URL, LLMError, build_provider, provider_catalogue, resolve_llm, validate_base_url
from app.services.llm.registry import default_provider_id, get_spec
from app.services.vector_store import get_vector_store

router = APIRouter(tags=["dashboard", "syllabus", "resources", "settings", "system"])


# ------------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return dashboard_service.overview(db, user)


# -------------------------------------------------------------------- syllabus
class TopicProgressRequest(BaseModel):
    completed: bool = True


@router.get("/syllabus/subjects")
def subjects(semester: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return syllabus_service.list_subjects(db, user, semester)


@router.get("/syllabus/subjects/{subject_id}")
def subject(subject_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    data = syllabus_service.subject_detail(db, user, subject_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")
    return data


@router.post("/syllabus/topics/{topic_id}/progress")
def topic_progress(topic_id: int, payload: TopicProgressRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        row = syllabus_service.set_topic_progress(db, user, topic_id, payload.completed)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"topic_id": row.topic_id, "completed": row.completed}


# ------------------------------------------------------------------- resources
@router.get("/resources/videos")
async def videos(
    q: str | None = None,
    subject_id: int | None = None,
    topic: str | None = None,
    max_results: int = 8,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    subject = db.get(Subject, subject_id) if subject_id else None
    query = q or video_service.build_query(subject.name if subject else None, topic, subject.code if subject else None)
    if not query.strip() or query.strip() == "AKTU":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a search query, a topic or a subject")
    results, source = await video_service.search_videos(query, max_results=min(max(max_results, 1), 15))
    curated = video_service.curated_for(subject.code if subject else None, topic, subject.name if subject else None)
    return {"query": query, "source": source, "videos": results, "curated": curated}


# -------------------------------------------------------------------- settings
def _resolved_out(db: Session, user: User) -> ResolvedLLMOut:
    r = resolve_llm(db, user)
    return ResolvedLLMOut(
        provider=r.provider_id, provider_name=r.spec.name, model=r.model, base_url=r.base_url,
        key_source=r.source, key_masked=mask_secret(r.api_key), has_key=bool(r.api_key) or not r.spec.requires_key,
    )


@router.get("/settings/providers", response_model=ProvidersResponse)
def providers(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProvidersResponse:
    settings = get_settings()
    return ProvidersResponse(
        providers=[ProviderInfo(**p) for p in provider_catalogue()],
        current=_resolved_out(db, user),
        embedding=embedder_status(),
        vector_store=settings.vector_store,
    )


@router.put("/settings/llm", response_model=ResolvedLLMOut)
def update_llm(payload: LLMSettingsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ResolvedLLMOut:
    spec = get_spec(payload.provider)
    row = db.execute(select(UserSettings).where(UserSettings.user_id == user.id)).scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user.id)
        db.add(row)
    switching = row.llm_provider != spec.id
    row.llm_provider = spec.id
    row.llm_model = (payload.model or "").strip() or (None if switching else row.llm_model)
    if switching:
        row.llm_base_url = None  # never carry a custom endpoint over to another provider
    if spec.id in CONFIGURABLE_BASE_URL:
        if payload.base_url is not None:
            row.llm_base_url = validate_base_url(payload.base_url, spec.id)
    else:
        row.llm_base_url = None  # hosted providers are pinned to their registry endpoint
    if payload.clear_key or switching:
        row.llm_api_key_enc = None
    if payload.api_key:
        row.llm_api_key_enc = encrypt_secret(payload.api_key.strip())
    db.commit()
    return _resolved_out(db, user)


@router.post("/settings/llm/test", response_model=LLMTestResponse)
async def test_llm(payload: LLMTestRequest, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> LLMTestResponse:
    override = {k: v for k, v in payload.model_dump().items() if v}
    resolved = resolve_llm(db, user, override=override)
    started = time.perf_counter()
    try:
        llm = build_provider(resolved)
        result = await llm.complete(
            [{"role": "system", "content": "You are a connectivity check."}, {"role": "user", "content": "Reply with exactly: Connection OK"}],
            temperature=0.0, max_tokens=512,  # reasoning models think before they answer
        )
        latency = int((time.perf_counter() - started) * 1000)
        if not result.text.strip():
            return LLMTestResponse(ok=False, provider=resolved.provider_id, model=resolved.model, latency_ms=latency, error="The model connected but returned an empty reply (finish reason: " + str(result.finish_reason) + "). Try another model.")
        return LLMTestResponse(ok=True, provider=resolved.provider_id, model=resolved.model, latency_ms=latency, reply=result.text[:200])
    except LLMError as exc:
        return LLMTestResponse(ok=False, provider=resolved.provider_id, model=resolved.model, error=exc.user_message)


@router.post("/settings/llm/models", response_model=ModelListResponse)
async def list_models(payload: ModelListRequest, user: User = Depends(ai_rate_limit), db: Session = Depends(get_db)) -> ModelListResponse:
    """List the provider's live model catalogue (POST so the key never appears in a URL or access log)."""
    override = {"provider": payload.provider}
    if payload.api_key:
        override["api_key"] = payload.api_key
    if payload.base_url:
        override["base_url"] = payload.base_url
    resolved = resolve_llm(db, user, override=override)
    try:
        llm = build_provider(resolved)
        models = await llm.list_models()
    except LLMError as exc:
        raise HTTPException(exc.status if exc.status in (400, 429) else status.HTTP_502_BAD_GATEWAY, exc.user_message) from exc
    return ModelListResponse(provider=payload.provider, models=models)


# ---------------------------------------------------------------------- system
@router.get("/system/health")
def health(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme), db: Session = Depends(get_db)) -> dict:
    """Liveness for everyone; configuration details only for signed-in users."""
    settings = get_settings()
    user: User | None = None
    if credentials is not None:
        try:
            user = get_current_user(credentials, db)
        except HTTPException:
            user = None
    if user is None:
        return {"status": "ok", "version": __version__, "rag_engine": "active" if embedder_status()["ready"] else "warming-up"}
    try:
        store = get_vector_store()
        store.count()  # reachability check; the number shown is the caller's own passages
        mine = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.user_id == user.id)) or 0
        vector = {"name": store.name, "count": mine}
    except Exception as exc:  # noqa: BLE001
        vector = {"name": settings.vector_store, "error": str(exc)[:200]}
    env_providers = [p["id"] for p in provider_catalogue() if p["env_key_configured"] or not p["requires_key"]]
    return {
        "status": "ok",
        "version": __version__,
        "app_env": settings.app_env,
        "embedding": embedder_status(),
        "vector_store": vector,
        "fts": fts_available(),
        "default_provider": default_provider_id(settings.llm_provider),
        "providers_ready": env_providers,
        "rag_engine": "active" if embedder_status()["ready"] else "warming-up",
    }


@router.get("/system/config")
def public_config() -> dict:
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "version": __version__,
        "allow_registration": settings.allow_registration,
        "max_upload_mb": settings.max_upload_mb,
        "supported_files": ["pdf", "docx", "txt", "md"],
        "default_provider": default_provider_id(settings.llm_provider),
    }
