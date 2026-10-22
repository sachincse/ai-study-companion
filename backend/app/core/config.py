"""Application configuration.

All settings come from environment variables or a ``.env`` file. The project
root ``.env`` is the canonical location (see ``.env.example``); a ``backend/.env``
is also honoured for people who only run the API.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- general -----------------------------------------------------------
    app_name: str = "AI Study Companion"
    app_env: str = Field(default="development", description="development | production | test")
    secret_key: str = Field(default="change-me-in-production")
    access_token_expire_minutes: int = 60 * 24 * 7
    allow_registration: bool = True
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"]
    )

    # --- storage -----------------------------------------------------------
    storage_dir: Path = ROOT_DIR / "storage"
    data_dir: Path = ROOT_DIR / "data"
    database_url: str | None = None  # defaults to a sqlite file inside storage_dir
    max_upload_mb: int = 25

    # --- retrieval -----------------------------------------------------------
    vector_store: str = Field(default="chroma", description="chroma | memory")
    embedding_provider: str = Field(default="local", description="local | openai | gemini | ollama")
    embedding_model: str | None = None
    chunk_size_chars: int = 2000  # roughly 500 tokens
    chunk_overlap_chars: int = 200
    retrieval_top_k: int = 6

    # --- LLM providers -------------------------------------------------------
    llm_provider: str = Field(default="groq", description="default provider id, see services/llm/registry.py")
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    xai_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    mistral_api_key: str | None = None
    deepseek_api_key: str | None = None
    together_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    llm_timeout_seconds: float = 120.0

    # --- resources -----------------------------------------------------------
    youtube_api_key: str | None = None
    enable_ytdlp_fallback: bool = True

    # --- limits ----------------------------------------------------------------
    ai_rate_limit_per_minute: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):  # noqa: ANN001
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    # --- derived -----------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.storage_dir / "chroma"

    @property
    def models_cache_dir(self) -> Path:
        return self.storage_dir / "models"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.storage_dir / 'study_companion.db').as_posix()}"

    def ensure_dirs(self) -> None:
        for d in (self.storage_dir, self.uploads_dir, self.chroma_dir, self.models_cache_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
