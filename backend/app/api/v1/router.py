from fastapi import APIRouter

from app.api.v1 import auth, chat, documents, flashcards, misc, quizzes, tools

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(quizzes.router)
api_router.include_router(flashcards.router)
api_router.include_router(tools.router)
api_router.include_router(misc.router)
