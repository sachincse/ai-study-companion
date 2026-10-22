"""Common types for LLM providers."""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None


class LLMError(RuntimeError):
    """Raised when a provider call fails; ``user_message`` is safe to show in the UI."""

    def __init__(self, user_message: str, *, status: int | None = None, provider: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.status = status
        self.provider = provider


class LLMProvider(Protocol):
    id: str
    model: str

    async def stream(
        self, messages: list[dict[str, str]], *, temperature: float = 0.3, max_tokens: int = 2048
    ) -> AsyncIterator[str]: ...

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResult: ...

    async def list_models(self) -> list[str]: ...


class ThinkTagFilter:
    """Strip ``<think>...</think>`` reasoning blocks from a token stream.

    Some open models (Qwen3, DeepSeek-R1) emit their chain of thought inline.
    Students should only see the answer, so we filter it out while streaming.
    """

    def __init__(self) -> None:
        self._inside = False
        self._pending = ""

    def feed(self, token: str) -> str:
        buf = self._pending + token
        self._pending = ""
        out = ""
        while buf:
            if self._inside:
                end = buf.find("</think>")
                if end < 0:
                    # keep a tail in case the closing tag is split across tokens
                    self._pending = buf[-8:]
                    return out
                buf = buf[end + len("</think>") :]
                self._inside = False
                continue
            start = buf.find("<think>")
            if start < 0:
                # hold back a partial opening tag
                lt = buf.rfind("<")
                if lt >= 0 and "<think>".startswith(buf[lt:]):
                    out += buf[:lt]
                    self._pending = buf[lt:]
                else:
                    out += buf
                return out
            out += buf[:start]
            buf = buf[start + len("<think>") :]
            self._inside = True
        return out

    def flush(self) -> str:
        tail = "" if self._inside else self._pending
        self._pending = ""
        return tail


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of an LLM reply (fences, prose, etc.)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    candidates: list[str] = []
    m = _JSON_FENCE.search(text)
    if m:
        candidates.append(m.group(1).strip())
    candidates.append(text)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start >= 0 and end > start:
            candidates.append(text[start : end + 1])
    last_error: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as exc:
            last_error = exc
            # try to repair trailing commas
            repaired = re.sub(r",\s*([}\]])", r"\1", cand)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Model did not return valid JSON: {last_error}")
