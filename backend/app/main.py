"""FastAPI application factory for AI Study Companion."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1.router import api_router
from app.core.config import ROOT_DIR, get_settings
from app.core.database import get_session_factory, init_db
from app.services.document_service import UploadError
from app.services.embeddings import warm_up_in_background
from app.services.generation import GenerationError
from app.services.llm import LLMError
from app.services.syllabus_service import seed_syllabus

log = logging.getLogger("app")
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings.ensure_dirs()
    init_db()
    with get_session_factory()() as db:
        n = seed_syllabus(db)
        log.info("syllabus seeded (%s subjects)", n)
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
        status = 429 if exc.status == 429 else 502
        return JSONResponse(status_code=status, content={"detail": exc.user_message, "provider": exc.provider, "kind": "llm_error"})

    @app.exception_handler(GenerationError)
    async def _generation_error(_: Request, exc: GenerationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc), "kind": "generation_error"})

    @app.exception_handler(UploadError)
    async def _upload_error(_: Request, exc: UploadError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc), "kind": "upload_error"})

    mount_frontend(app)
    return app


def mount_frontend(app: FastAPI) -> None:
    """Serve the built React app (frontend/dist) when present - single-container deploys."""
    if not FRONTEND_DIST.exists():
        return
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):  # noqa: ANN202
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file() and candidate.resolve().is_relative_to(FRONTEND_DIST.resolve()):
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
