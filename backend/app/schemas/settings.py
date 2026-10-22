from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.services.llm.registry import PROVIDERS


def _check_provider(value: str | None) -> str | None:
    if value is None:
        return None
    pid = value.strip().lower()
    if pid not in PROVIDERS:
        raise ValueError(f"Unknown provider '{value}'. Choose one of: {', '.join(PROVIDERS)}")
    return pid


class ProviderInfo(BaseModel):
    id: str
    name: str
    default_model: str
    docs_url: str
    key_hint: str = ""
    requires_key: bool = True
    free_tier: bool = False
    local: bool = False
    notes: str = ""
    env_key_configured: bool = False
    base_url: str | None = None


class ResolvedLLMOut(BaseModel):
    provider: str
    provider_name: str
    model: str
    base_url: str | None = None
    key_source: str  # user | env | none | override
    key_masked: str | None = None
    has_key: bool


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]
    current: ResolvedLLMOut
    embedding: dict
    vector_store: str


class LLMSettingsUpdate(BaseModel):
    provider: str
    model: str | None = Field(default=None, max_length=120)
    api_key: str | None = Field(default=None, max_length=512)
    base_url: str | None = Field(default=None, max_length=255)
    clear_key: bool = False

    _provider = field_validator("provider")(_check_provider)


class LLMTestRequest(BaseModel):
    provider: str | None = None
    model: str | None = Field(default=None, max_length=120)
    api_key: str | None = Field(default=None, max_length=512)
    base_url: str | None = Field(default=None, max_length=255)

    _provider = field_validator("provider")(_check_provider)


class ModelListRequest(BaseModel):
    """POST body for listing models: the key travels in the body, never in the URL."""

    provider: str
    api_key: str | None = Field(default=None, max_length=512)
    base_url: str | None = Field(default=None, max_length=255)

    _provider = field_validator("provider")(_check_provider)


class LLMTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_ms: int | None = None
    reply: str | None = None
    error: str | None = None


class ModelListResponse(BaseModel):
    provider: str
    models: list[str]
