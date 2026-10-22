"""Chat provider for every OpenAI-compatible API (OpenAI, Groq, xAI, Gemini, Ollama...)."""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from app.services.llm.base import LLMError, LLMResult, ThinkTagFilter
from app.services.llm.registry import ProviderSpec


def _friendly(exc: Exception, spec: ProviderSpec, model: str) -> LLMError:
    name = spec.name
    if isinstance(exc, AuthenticationError):
        return LLMError(f"{name} rejected the API key. Check it in Settings.", status=401, provider=spec.id)
    if isinstance(exc, PermissionDeniedError):
        return LLMError(f"{name} denied access to '{model}' (permission or region restriction).", status=403, provider=spec.id)
    if isinstance(exc, NotFoundError):
        return LLMError(f"{name} does not know the model '{model}'. Pick another model in Settings.", status=404, provider=spec.id)
    if isinstance(exc, RateLimitError):
        return LLMError(f"{name} rate limit or quota reached. Wait a moment or switch provider.", status=429, provider=spec.id)
    if isinstance(exc, BadRequestError):
        detail = getattr(exc, "message", str(exc))
        return LLMError(f"{name} rejected the request: {detail[:200]}", status=400, provider=spec.id)
    if isinstance(exc, APIConnectionError):
        target = spec.base_url or "the provider"
        return LLMError(f"Could not connect to {name} ({target}). Is it running / reachable?", status=503, provider=spec.id)
    if isinstance(exc, APIStatusError) and exc.status_code == 402:
        return LLMError(f"{name} says the account has no credits left (HTTP 402). Top up or switch provider.", status=402, provider=spec.id)
    if isinstance(exc, APIStatusError):
        return LLMError(f"{name} returned HTTP {exc.status_code}.", status=exc.status_code, provider=spec.id)
    return LLMError(f"{name} call failed: {str(exc)[:200]}", provider=spec.id)


class OpenAICompatProvider:
    def __init__(self, spec: ProviderSpec, *, model: str, api_key: str | None, base_url: str | None, timeout: float = 120.0) -> None:
        self.spec = spec
        self.id = spec.id
        self.model = model
        self.base_url = base_url or spec.base_url
        key = api_key or ("not-needed" if not spec.requires_key else None)
        if not key:
            raise LLMError(f"No API key configured for {spec.name}. Add one in Settings or set {spec.key_env}.", status=401, provider=spec.id)
        self._client = AsyncOpenAI(api_key=key, base_url=self.base_url, timeout=timeout, max_retries=3)  # SDK backs off on 429/5xx

    async def stream(self, messages, *, temperature: float = 0.3, max_tokens: int = 2048) -> AsyncIterator[str]:  # noqa: ANN001
        think = ThinkTagFilter()
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
                if text:
                    cleaned = think.feed(text)
                    if cleaned:
                        yield cleaned
            tail = think.flush()
            if tail:
                yield tail
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _friendly(exc, self.spec, self.model) from exc

    async def complete(self, messages, *, temperature: float = 0.3, max_tokens: int = 2048, json_mode: bool = False) -> LLMResult:  # noqa: ANN001
        kwargs: dict = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode and self.spec.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            try:
                resp = await self._client.chat.completions.create(**kwargs)
            except BadRequestError:
                if "response_format" not in kwargs:
                    raise
                kwargs.pop("response_format")  # provider/model without JSON mode: retry plain
                resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise _friendly(exc, self.spec, self.model) from exc
        if not hasattr(resp, "choices"):
            hint = " GitHub Models needs a fine-grained personal access token with the 'models:read' permission." if self.spec.id == "github" else ""
            raise LLMError(f"{self.spec.name} returned an unexpected response: {str(resp)[:120]}.{hint}", status=502, provider=self.id)
        choice = resp.choices[0] if resp.choices else None
        text = (choice.message.content if choice and choice.message else "") or ""
        if not text.strip() and choice is not None:
            # reasoning models that spent the budget on thinking
            reasoning = getattr(choice.message, "reasoning", None) or getattr(choice.message, "reasoning_content", None)
            if reasoning and json_mode:
                text = reasoning
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
        filt = ThinkTagFilter()
        cleaned = filt.feed(text) + filt.flush()
        return LLMResult(text=cleaned.strip(), provider=self.id, model=self.model, usage=usage, finish_reason=getattr(choice, "finish_reason", None))

    async def list_models(self) -> list[str]:
        try:
            if self.spec.models_url:
                ids = sorted(await self._list_from_catalog())
            else:
                page = await self._client.models.list()
                ids = sorted({m.id.removeprefix("models/") for m in page.data})
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _friendly(exc, self.spec, self.model) from exc
        # keep chat-capable models near the top for the big catalogues
        chatty = [m for m in ids if not any(x in m.lower() for x in ("embed", "whisper", "tts", "audio", "image", "moderation", "guard", "rerank", "dall-e", "realtime", "transcribe", "search"))]
        return chatty or ids

    async def _list_from_catalog(self) -> set[str]:
        """Catalogue endpoints that are not /models (e.g. GitHub Models)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.spec.models_url or "", headers={"Authorization": f"Bearer {self._client.api_key}", "Accept": "application/vnd.github+json"})
        if resp.status_code == 401:
            raise LLMError(f"{self.spec.name} rejected the token. Check it in Settings.", status=401, provider=self.id)
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data") or data.get("models") or []
        return {str(m.get("id") or m.get("name")) for m in items if isinstance(m, dict) and (m.get("id") or m.get("name"))}
