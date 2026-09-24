"""Central, provider-agnostic chat model factory.

Model, provider and base URL come **only** from the environment (`.env`); there
are intentionally no defaults. When the variables are not configured, the LLM
path is disabled and the deterministic flow keeps working.

Supported providers:
  * ``openai``     -> official OpenAI API (base URL optional)
  * ``openrouter`` -> OpenRouter (dedicated integration)
  * ``litellm``    -> LiteLLM proxy/router (dedicated integration)
  * anything else  -> any OpenAI-compatible endpoint (base URL required)
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from config import PACKAGE_DIR

try:  # optional import so the deterministic flow never depends on the LLM stack
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]

PLACEHOLDERS = frozenset(
    {"", "changeme", "sua-chave", "your-key", "your_api_key", "sk-...", "coloque-a-chave", "todo", "xxx"}
)
MIN_KEY_LENGTH = 20

# Providers that do not need an explicit base URL.
_OPTIONAL_BASE_URL = frozenset({"openai", "openrouter", "litellm"})


class LLMConfigError(Exception):
    """The LLM environment is missing or invalid."""


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    base_url: str | None
    api_key: str


def _load_dotenv() -> None:
    if load_dotenv is None:
        return
    for path in (PACKAGE_DIR.parent / ".env", PACKAGE_DIR / ".env"):
        if path.exists():
            load_dotenv(path, override=False)
            return


def load_llm_settings(
    env: Mapping[str, str] | None = None,
    *,
    required: bool = True,
) -> LLMSettings | None:
    """Validate LLM_* variables. Returns None (instead of raising) when not required."""
    if env is None:
        _load_dotenv()
        env = os.environ

    provider = str(env.get("LLM_PROVIDER", "")).strip().lower()
    model = str(env.get("LLM_MODEL", "")).strip()
    base_url = str(env.get("LLM_BASE_URL", "")).strip().rstrip("/")
    api_key = str(env.get("LLM_API_KEY", "")).strip()

    missing = [name for name, value in (("LLM_PROVIDER", provider), ("LLM_MODEL", model), ("LLM_API_KEY", api_key)) if not value]
    if missing:
        if not required:
            return None
        raise LLMConfigError(f"Defina {', '.join(missing)} no ambiente ou no .env (veja .env.example).")

    if api_key.casefold() in PLACEHOLDERS or len(api_key) < MIN_KEY_LENGTH:
        if not required:
            return None
        raise LLMConfigError("LLM_API_KEY está vazia, é o valor de exemplo ou parece incompleta.")
    if base_url and not base_url.startswith(("http://", "https://")):
        raise LLMConfigError("LLM_BASE_URL precisa começar com http:// ou https://.")
    if not base_url and provider not in _OPTIONAL_BASE_URL:
        raise LLMConfigError(f"LLM_BASE_URL é obrigatória para o provedor '{provider}'.")

    return LLMSettings(provider=provider, model=model, base_url=base_url or None, api_key=api_key)


def llm_available() -> bool:
    """True when a valid LLM configuration is present."""
    return load_llm_settings(required=False) is not None


def get_chat_model(settings: LLMSettings | None = None, *, temperature: float = 0.0):
    """Build a chat model for the configured provider (no defaults)."""
    settings = settings or load_llm_settings()
    assert settings is not None  # load_llm_settings raises when required

    if settings.provider == "openrouter":
        from langchain_openrouter import ChatOpenRouter

        kwargs = {"model": settings.model, "api_key": settings.api_key, "temperature": temperature}
        if settings.base_url:
            kwargs["base_url"] = settings.base_url
        return ChatOpenRouter(**kwargs)

    if settings.provider == "litellm":
        from langchain_litellm import ChatLiteLLM

        kwargs = {"model": settings.model, "api_key": settings.api_key, "temperature": temperature}
        if settings.base_url:
            kwargs["api_base"] = settings.base_url
        return ChatLiteLLM(**kwargs)

    from langchain_openai import ChatOpenAI

    kwargs = {"model": settings.model, "api_key": settings.api_key, "temperature": temperature}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return ChatOpenAI(**kwargs)
