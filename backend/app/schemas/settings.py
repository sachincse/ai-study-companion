from __future__ import annotations

from pydantic import BaseModel, Field


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


class LLMTestRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


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
