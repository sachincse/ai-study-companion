"""Catalogue of supported LLM providers.

Every provider except Anthropic speaks the OpenAI chat-completions protocol, so
one client implementation covers OpenAI, Groq, xAI (Grok), Google Gemini,
OpenRouter, Mistral, DeepSeek, Together, Cerebras, SambaNova, Hugging Face,
NVIDIA NIM, a local Ollama and any custom endpoint (LM Studio, vLLM, LiteLLM...).
Anthropic uses the official ``anthropic`` SDK.

Default model ids are a starting point only: the Settings page lists the live
``/models`` catalogue of whichever provider you pick, so stale defaults never
block you.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.llm.base import LLMError


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    kind: str  # openai_compat | anthropic
    base_url: str | None
    default_model: str
    key_env: str | None
    docs_url: str
    key_hint: str = ""
    requires_key: bool = True
    free_tier: bool = False
    local: bool = False
    supports_json_mode: bool = True
    notes: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        id="groq",
        name="Groq",
        kind="openai_compat",
        base_url="https://api.groq.com/openai/v1",
        default_model="openai/gpt-oss-120b",
        key_env="GROQ_API_KEY",
        docs_url="https://console.groq.com/keys",
        key_hint="gsk_...",
        free_tier=True,
        notes="Very fast inference with a generous free tier. Great default for students.",
    ),
    "gemini": ProviderSpec(
        id="gemini",
        name="Google Gemini",
        kind="openai_compat",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemini-3.5-flash",
        key_env="GEMINI_API_KEY",
        docs_url="https://aistudio.google.com/apikey",
        key_hint="AQ.... (older keys: AIza...)",
        free_tier=True,
        notes="Free tier via Google AI Studio. gemini-3.5-flash and gemini-flash-lite-latest answer in seconds; the gemini-flash-latest alias can be much slower.",
    ),
    "openai": ProviderSpec(
        id="openai",
        name="OpenAI",
        kind="openai_compat",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        key_env="OPENAI_API_KEY",
        docs_url="https://platform.openai.com/api-keys",
        key_hint="sk-...",
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        name="Anthropic Claude",
        kind="anthropic",
        base_url=None,
        default_model="claude-opus-5-5",
        key_env="ANTHROPIC_API_KEY",
        docs_url="https://console.anthropic.com/settings/keys",
        key_hint="sk-ant-...",
        supports_json_mode=False,
        notes="Uses the official Anthropic SDK (streaming, adaptive thinking, server-side refusal fallbacks).",
    ),
    "xai": ProviderSpec(
        id="xai",
        name="xAI Grok",
        kind="openai_compat",
        base_url="https://api.x.ai/v1",
        default_model="grok-4.7",
        key_env="XAI_API_KEY",
        docs_url="https://console.x.ai/",
        key_hint="xai-...",
        notes="Keys from console.x.ai start with 'xai-'.",
    ),
    "openrouter": ProviderSpec(
        id="openrouter",
        name="OpenRouter",
        kind="openai_compat",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4o-mini",
        key_env="OPENROUTER_API_KEY",
        docs_url="https://openrouter.ai/keys",
        key_hint="sk-or-v1-...",
        free_tier=True,
        notes="One key for hundreds of models; several ':free' models available.",
    ),
    "mistral": ProviderSpec(
        id="mistral",
        name="Mistral",
        kind="openai_compat",
        base_url="https://api.mistral.ai/v1",
        default_model="mistral-small-latest",
        key_env="MISTRAL_API_KEY",
        docs_url="https://console.mistral.ai/api-keys",
        free_tier=True,
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        name="DeepSeek",
        kind="openai_compat",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        key_env="DEEPSEEK_API_KEY",
        docs_url="https://platform.deepseek.com/api_keys",
    ),
    "together": ProviderSpec(
        id="together",
        name="Together AI",
        kind="openai_compat",
        base_url="https://api.together.xyz/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        key_env="TOGETHER_API_KEY",
        docs_url="https://api.together.xyz/settings/api-keys",
    ),
    "cerebras": ProviderSpec(
        id="cerebras",
        name="Cerebras",
        kind="openai_compat",
        base_url="https://api.cerebras.ai/v1",
        default_model="llama-3.3-70b",
        key_env="CEREBRAS_API_KEY",
        docs_url="https://cloud.cerebras.ai/",
        key_hint="csk-...",
        notes="Very fast inference. New accounts get a small trial credit after adding a payment method, then pay as you go.",
    ),
    "sambanova": ProviderSpec(
        id="sambanova",
        name="SambaNova Cloud",
        kind="openai_compat",
        base_url="https://api.sambanova.ai/v1",
        default_model="Meta-Llama-3.3-70B-Instruct",
        key_env="SAMBANOVA_API_KEY",
        docs_url="https://cloud.sambanova.ai/",
        free_tier=True,
        notes="Free tier for open-weight models (Llama, DeepSeek, Qwen).",
    ),
    "huggingface": ProviderSpec(
        id="huggingface",
        name="Hugging Face Inference",
        kind="openai_compat",
        base_url="https://router.huggingface.co/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct",
        key_env="HF_TOKEN",
        docs_url="https://huggingface.co/settings/tokens",
        key_hint="hf_...",
        free_tier=True,
        supports_json_mode=False,
        notes="Free monthly inference credits with a Hugging Face account; thousands of open models.",
    ),
    "nvidia": ProviderSpec(
        id="nvidia",
        name="NVIDIA NIM",
        kind="openai_compat",
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="meta/llama-3.3-70b-instruct",
        key_env="NVIDIA_API_KEY",
        docs_url="https://build.nvidia.com/",
        key_hint="nvapi-...",
        free_tier=True,
        notes="Free, rate-limited trial access for prototyping at build.nvidia.com.",
    ),
    "ollama": ProviderSpec(
        id="ollama",
        name="Ollama (local)",
        kind="openai_compat",
        base_url="http://localhost:11434/v1",
        default_model="qwen2.5:7b",
        key_env=None,
        docs_url="https://ollama.com/download",
        requires_key=False,
        free_tier=True,
        local=True,
        notes="Runs fully offline. Pull a model first, e.g. `ollama pull qwen2.5:7b`.",
    ),
    "custom": ProviderSpec(
        id="custom",
        name="Custom OpenAI-compatible",
        kind="openai_compat",
        base_url=None,
        default_model="",
        key_env=None,
        docs_url="https://platform.openai.com/docs/api-reference/chat",
        requires_key=False,
        local=True,
        notes="LM Studio, vLLM, LiteLLM, text-generation-webui... set the base URL in Settings.",
    ),
}

DEFAULT_PROVIDER_ORDER = list(PROVIDERS.keys())


DEFAULT_PROVIDER = "groq"  # same as Settings.llm_provider's default


def default_provider_id(configured: str | None) -> str:
    """The server default from LLM_PROVIDER, or Groq when that names an unknown or retired provider."""
    pid = (configured or "").strip().lower()
    return pid if pid in PROVIDERS else DEFAULT_PROVIDER


def get_spec(provider_id: str) -> ProviderSpec:
    try:
        return PROVIDERS[(provider_id or "").strip().lower()]
    except KeyError as exc:
        raise LLMError(f"Unknown LLM provider '{provider_id}'. Choose one of: {', '.join(PROVIDERS)}", status=400) from exc
