"""Anthropic Claude provider using the official ``anthropic`` SDK.

Notes on current API behaviour (2026):
* Thinking is adaptive by default on the Claude 5 family, so we simply omit the
  ``thinking`` parameter.
* Server-side refusal fallbacks are enabled for the models that support them
  (``fallbacks="default"``), so a safety-classifier decline re-runs the request
  on a fallback model inside the same call instead of failing the student.
* Responses are always streamed.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic

from app.services.llm.base import LLMError, LLMResult, ThinkTagFilter
from app.services.llm.registry import ProviderSpec

FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_CAPABLE_PREFIXES = ("claude-opus-5", "claude-sonnet-5-5", "claude-fable")


def _split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    convo = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    if not convo or convo[0]["role"] != "user":
        convo.insert(0, {"role": "user", "content": "(context)"})
    return "\n\n".join(system_parts), convo


def _friendly(exc: Exception, spec: ProviderSpec, model: str) -> LLMError:
    if isinstance(exc, anthropic.AuthenticationError):
        return LLMError("Anthropic rejected the API key. Check it in Settings.", status=401, provider=spec.id)
    if isinstance(exc, anthropic.PermissionDeniedError):
        return LLMError("Anthropic API key lacks permission for this request.", status=403, provider=spec.id)
    if isinstance(exc, anthropic.NotFoundError):
        return LLMError(f"Anthropic does not know the model '{model}'.", status=404, provider=spec.id)
    if isinstance(exc, anthropic.RateLimitError):
        return LLMError("Anthropic rate limit reached. Wait a moment and retry.", status=429, provider=spec.id)
    if isinstance(exc, anthropic.BadRequestError):
        return LLMError(f"Anthropic rejected the request: {getattr(exc, 'message', str(exc))[:200]}", status=400, provider=spec.id)
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMError("Could not connect to the Anthropic API.", status=503, provider=spec.id)
    if isinstance(exc, anthropic.APIStatusError):
        return LLMError(f"Anthropic returned HTTP {exc.status_code}.", status=exc.status_code, provider=spec.id)
    return LLMError(f"Anthropic call failed: {str(exc)[:200]}", provider=spec.id)


class AnthropicProvider:
    def __init__(self, spec: ProviderSpec, *, model: str, api_key: str | None, base_url: str | None = None, timeout: float = 120.0) -> None:
        self.spec = spec
        self.id = spec.id
        self.model = model
        if not api_key:
            raise LLMError("No Anthropic API key configured. Add one in Settings or set ANTHROPIC_API_KEY.", status=401, provider=spec.id)
        kwargs: dict = {"api_key": api_key, "timeout": timeout, "max_retries": 1}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.AsyncAnthropic(**kwargs)

    def _fallback_capable(self) -> bool:
        return self.model.startswith(FALLBACK_CAPABLE_PREFIXES)

    def _stream_ctx(self, system: str, convo: list[dict[str, str]], *, max_tokens: int, temperature: float):
        common = {"model": self.model, "max_tokens": max_tokens, "messages": convo}
        if system:
            common["system"] = system
        if self._fallback_capable():
            return self._client.beta.messages.stream(betas=[FALLBACK_BETA], fallbacks="default", **common)
        return self._client.messages.stream(**common)

    async def stream(self, messages, *, temperature: float = 0.3, max_tokens: int = 4096) -> AsyncIterator[str]:  # noqa: ANN001
        system, convo = _split_system(messages)
        think = ThinkTagFilter()
        try:
            async with self._stream_ctx(system, convo, max_tokens=max_tokens, temperature=temperature) as stream:
                async for text in stream.text_stream:
                    cleaned = think.feed(text)
                    if cleaned:
                        yield cleaned
                final = await stream.get_final_message()
                if final.stop_reason == "refusal":
                    yield "\n\n_I can't help with that request. Try rephrasing it around your study material._"
            tail = think.flush()
            if tail:
                yield tail
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _friendly(exc, self.spec, self.model) from exc

    async def complete(self, messages, *, temperature: float = 0.3, max_tokens: int = 4096, json_mode: bool = False) -> LLMResult:  # noqa: ANN001
        if json_mode:
            messages = list(messages) + [{"role": "user", "content": "Respond with valid JSON only, no prose and no code fences."}]
        system, convo = _split_system(messages)
        parts: list[str] = []
        try:
            async with self._stream_ctx(system, convo, max_tokens=max_tokens, temperature=temperature) as stream:
                async for text in stream.text_stream:
                    parts.append(text)
                final = await stream.get_final_message()
        except Exception as exc:  # noqa: BLE001
            raise _friendly(exc, self.spec, self.model) from exc
        if final.stop_reason == "refusal":
            raise LLMError("Anthropic declined this request (safety classifier).", status=400, provider=self.id)
        usage = {"input_tokens": final.usage.input_tokens, "output_tokens": final.usage.output_tokens}
        filt = ThinkTagFilter()
        text = filt.feed("".join(parts)) + filt.flush()
        return LLMResult(text=text.strip(), provider=self.id, model=self.model, usage=usage, finish_reason=final.stop_reason)

    async def list_models(self) -> list[str]:
        try:
            ids: list[str] = []
            async for m in self._client.models.list():
                ids.append(m.id)
            return sorted(ids)
        except Exception as exc:  # noqa: BLE001
            raise _friendly(exc, self.spec, self.model) from exc
