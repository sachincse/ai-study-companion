"""Provider factory: resolves which LLM to use for a given user.

Resolution order: the user's own settings (provider/model/key saved from the
Settings page) -> environment defaults (``LLM_PROVIDER``, ``*_API_KEY``).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decrypt_secret
from app.models import User, UserSettings
from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.base import LLMError, LLMProvider, LLMResult, extract_json
from app.services.llm.openai_compat import OpenAICompatProvider
from app.services.llm.registry import PROVIDERS, ProviderSpec, get_spec

__all__ = ["LLMError", "LLMProvider", "LLMResult", "ResolvedLLM", "build_provider", "extract_json", "resolve_llm"]


@dataclass
class ResolvedLLM:
    provider_id: str
    model: str
    api_key: str | None
    base_url: str | None
    source: str  # user | env
    spec: ProviderSpec


def env_key_for(spec: ProviderSpec, settings: Settings) -> str | None:
    if settings.llm_api_key and settings.llm_provider.lower() == spec.id:
        return settings.llm_api_key
    if not spec.key_env:
        return None
    return getattr(settings, spec.key_env.lower(), None)


def resolve_llm(db: Session, user: User | None, *, override: dict | None = None) -> ResolvedLLM:
    """Figure out provider/model/key for this user without instantiating a client."""
    settings = get_settings()
    override = override or {}
    user_settings: UserSettings | None = None
    if user is not None:
        user_settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).one_or_none()

    provider_id = override.get("provider") or (user_settings.llm_provider if user_settings and user_settings.llm_provider else None) or settings.llm_provider
    spec = get_spec(provider_id)

    api_key = override.get("api_key")
    source = "override" if api_key else ""
    if api_key is None and user_settings and user_settings.llm_provider == spec.id and user_settings.llm_api_key_enc:
        api_key = decrypt_secret(user_settings.llm_api_key_enc)
        source = "user"
    if api_key is None:
        api_key = env_key_for(spec, settings)
        source = "env" if api_key else "none"

    model = override.get("model") or (user_settings.llm_model if user_settings and user_settings.llm_provider == spec.id and user_settings.llm_model else None)
    if not model:
        model = settings.llm_model if settings.llm_provider.lower() == spec.id and settings.llm_model else spec.default_model

    base_url = override.get("base_url") or (user_settings.llm_base_url if user_settings and user_settings.llm_provider == spec.id else None)
    if not base_url:
        if spec.id == "ollama":
            base_url = settings.ollama_base_url.rstrip("/") + "/v1"
        elif settings.llm_base_url and settings.llm_provider.lower() == spec.id:
            base_url = settings.llm_base_url
        else:
            base_url = spec.base_url
    return ResolvedLLM(provider_id=spec.id, model=model, api_key=api_key, base_url=base_url, source=source, spec=spec)


def build_provider(resolved: ResolvedLLM) -> LLMProvider:
    settings = get_settings()
    if resolved.spec.kind == "anthropic":
        return AnthropicProvider(resolved.spec, model=resolved.model, api_key=resolved.api_key, base_url=resolved.base_url, timeout=settings.llm_timeout_seconds)
    if resolved.spec.id == "custom" and not resolved.base_url:
        raise LLMError("Custom provider needs a base URL (e.g. http://localhost:1234/v1). Set it in Settings.", status=400, provider="custom")
    if not resolved.model:
        raise LLMError(f"Pick a model for {resolved.spec.name} in Settings.", status=400, provider=resolved.spec.id)
    return OpenAICompatProvider(resolved.spec, model=resolved.model, api_key=resolved.api_key, base_url=resolved.base_url, timeout=settings.llm_timeout_seconds)


def get_llm(db: Session, user: User | None, *, override: dict | None = None) -> LLMProvider:
    return build_provider(resolve_llm(db, user, override=override))


def provider_catalogue() -> list[dict]:
    settings = get_settings()
    out = []
    for spec in PROVIDERS.values():
        out.append(
            {
                "id": spec.id,
                "name": spec.name,
                "default_model": spec.default_model,
                "docs_url": spec.docs_url,
                "key_hint": spec.key_hint,
                "requires_key": spec.requires_key,
                "free_tier": spec.free_tier,
                "local": spec.local,
                "notes": spec.notes,
                "env_key_configured": bool(env_key_for(spec, settings)),
                "base_url": settings.ollama_base_url.rstrip("/") + "/v1" if spec.id == "ollama" else spec.base_url,
            }
        )
    return out
