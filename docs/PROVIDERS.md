# Model providers

You need exactly one chat model. Pick whichever you have a key for (or run Ollama
locally and skip keys entirely). Keys can go in `.env` (shared by everyone on
that server) or be pasted per account in **Settings** (encrypted at rest).

| Provider | Env var | Default model | Free tier | Notes |
|---|---|---|---|---|
| Groq | `GROQ_API_KEY` | `openai/gpt-oss-120b` | yes | Fastest; great default for students. Keys: https://console.groq.com/keys |
| Google Gemini | `GEMINI_API_KEY` | `gemini-3.5-flash` | yes | https://aistudio.google.com/apikey; `gemini-flash-lite-latest` is the fastest, the `gemini-flash-latest` alias can be slow |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` | no | https://platform.openai.com/api-keys |
| Anthropic Claude | `ANTHROPIC_API_KEY` | `claude-opus-5-5` | no | Official SDK; adaptive thinking; server-side refusal fallbacks enabled |
| xAI Grok | `XAI_API_KEY` | `grok-4.7` | no | Keys from https://console.x.ai start with `xai-` |
| OpenRouter | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini` | some `:free` models | https://openrouter.ai/keys |
| Mistral | `MISTRAL_API_KEY` | `mistral-small-latest` | yes | https://console.mistral.ai/api-keys |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` | no | https://platform.deepseek.com/api_keys |
| Together AI | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | trial credits | https://api.together.xyz |
| Cerebras | `CEREBRAS_API_KEY` | `llama-3.3-70b` | yes | https://cloud.cerebras.ai (very fast) |
| SambaNova Cloud | `SAMBANOVA_API_KEY` | `Meta-Llama-3.3-70B-Instruct` | yes | https://cloud.sambanova.ai |
| GitHub Models | `GITHUB_MODELS_TOKEN` | `openai/gpt-4.1-mini` | yes (rate-limited) | fine-grained PAT with the **models:read** permission; the gh CLI's OAuth token does not work |
| Hugging Face Inference | `HF_TOKEN` | `meta-llama/Llama-3.3-70B-Instruct` | monthly credits | https://huggingface.co/settings/tokens; HTTP 402 means the credits are used up |
| NVIDIA NIM | `NVIDIA_API_KEY` | `meta/llama-3.3-70b-instruct` | signup credits | https://build.nvidia.com |
| Ollama (local) | `OLLAMA_BASE_URL` | `qwen2.5:7b` | free, offline | `ollama pull qwen2.5:7b` |
| Custom | `LLM_BASE_URL`, `LLM_API_KEY` | - | - | LM Studio, vLLM, LiteLLM, text-generation-webui |

## Free options, honestly

You do not need to pay to run this. In rough order of generosity: a local Ollama
(free forever, needs ~5 GB RAM for a 7B model), Groq, Google AI Studio, Cerebras,
SambaNova, GitHub Models and Mistral all hand out free API keys on signup, and
OpenRouter exposes a set of `:free` models. The community-maintained list at
https://github.com/cheahjs/free-llm-api-resources tracks current limits.

Create the key under **your own** account. Keys that other people leaked in public
repositories or paste sites are not "free keys": using them is unauthorised access to
someone else's account, the keys get revoked within hours, and your app breaks with
them. This project will never ship with or look for such keys.

Set `LLM_PROVIDER=<id>` and optionally `LLM_MODEL=<model id>` in `.env`. The
Settings page can list the live model catalogue of any provider, so you never
have to guess a model id.

## Embeddings

Embeddings are deployment-wide (changing them means re-indexing notes):

| `EMBEDDING_PROVIDER` | Model | Dimensions | Needs |
|---|---|---|---|
| `local` (default) | fastembed `BAAI/bge-small-en-v1.5` | 384 | nothing; ~65 MB download on first run, CPU |
| `openai` | `text-embedding-3-small` | 1536 | `OPENAI_API_KEY` |
| `gemini` | `gemini-embedding-001` | 3072 | `GEMINI_API_KEY` |
| `ollama` | `nomic-embed-text` | 768 | `ollama pull nomic-embed-text` |

## Troubleshooting

- **"rejected the API key"**: the key is wrong for that provider. Groq keys start with `gsk_`, OpenAI with `sk-`, Anthropic with `sk-ant-`, xAI with `xai-`.
- **"does not know the model"**: click *Load models* in Settings and pick one from the live list.
- **Empty answers from reasoning models**: raise `max_tokens` (reasoning models spend tokens thinking); the app already requests 2048+ for chat.
- **Ollama slow**: the first request loads the model into memory; subsequent ones are faster. A 7B model needs ~5 GB RAM.
- **Local embeddings fail to download**: set `HF_ENDPOINT` to a mirror or switch to an API embedder.
