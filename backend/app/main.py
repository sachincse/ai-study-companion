"""FastAPI application factory for AI Study Companion."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1.router import api_router
from app.core.config import ROOT_DIR, get_settings
from app.core.database import get_session_factory, init_db
from app.services.document_service import UploadError, reset_interrupted_ingestion
from app.services.embeddings import warm_up_in_background
from app.services.generation import GenerationError
from app.services.llm import LLMError
from app.services.llm.registry import PROVIDERS, default_provider_id
from app.services.syllabus_service import seed_syllabus

log = logging.getLogger("app")
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpx2"):  # openai>=3 / anthropic>=2 send requests through httpx2; hf_hub and our own calls use httpx
        logging.getLogger(noisy).setLevel(logging.WARNING)  # one INFO line per model request is noise
    settings.ensure_dirs()
    init_db()
    with get_session_factory()() as db:
        n = seed_syllabus(db)
        log.info("syllabus seeded (%s subjects)", n)
        stale = reset_interrupted_ingestion(db)
        if stale:
            log.warning("%s document(s) were still queued or indexing when the server stopped; marked as failed so they can be re-indexed", stale)
    if settings.llm_provider.strip().lower() not in PROVIDERS:
        log.warning("LLM_PROVIDER=%r is not a supported provider (GitHub Models was removed in 1.0.1); using %s. Valid values: %s", settings.llm_provider, default_provider_id(settings.llm_provider), ", ".join(PROVIDERS))
    if settings.secret_key == "change-me-in-production" and settings.is_production:
        log.warning("SECRET_KEY is still the default value - set it before exposing this server!")
    if settings.embedding_provider == "local" and settings.app_env != "test":
        warm_up_in_background()
    log.info("%s v%s ready (env=%s, provider=%s, embeddings=%s, vector=%s)", settings.app_name, __version__, settings.app_env, settings.llm_provider, settings.embedding_provider, settings.vector_store)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="RAG-powered personal study assistant: grounded tutoring, notes search, quizzes, flashcards and analytics.",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    _add_body_limit(app, settings.max_upload_mb)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.exception_handler(LLMError)
    async def _llm_error(_: Request, exc: LLMError) -> JSONResponse:
        # 400 = bad input (unknown provider, bad URL), 429 = provider quota; anything else is upstream trouble.
        # Never forward a provider's 401/403: the browser would treat it as a logged-out session.
        status = exc.status if exc.status in (400, 429) else 502
        return JSONResponse(status_code=status, content={"detail": exc.user_message, "provider": exc.provider, "kind": "llm_error"})

    @app.exception_handler(GenerationError)
    async def _generation_error(_: Request, exc: GenerationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc), "kind": "generation_error"})

    @app.exception_handler(UploadError)
    async def _upload_error(_: Request, exc: UploadError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc), "kind": "upload_error"})

    mount_frontend(app)
    return app


def _add_body_limit(app: FastAPI, max_upload_mb: int) -> None:
    """Reject oversized request bodies before they are buffered (defence in depth for uploads)."""
    try:
        from starlette.middleware.body_limit import RequestBodyLimitMiddleware
    except ImportError:  # older starlette: the upload endpoint still enforces the limit while reading
        return
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=max_upload_mb * 1024 * 1024 + 1024 * 1024)


def mount_frontend(app: FastAPI) -> None:
    """Serve the built React app (frontend/dist) when present - single-container deploys."""
    if not FRONTEND_DIST.exists():
        return
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):  # noqa: ANN202
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")  # never serve the SPA for API paths
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file() and candidate.resolve().is_relative_to(FRONTEND_DIST.resolve()):
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
