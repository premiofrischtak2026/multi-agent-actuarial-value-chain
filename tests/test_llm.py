import pytest

from llm import LLMConfigError, LLMSettings, get_chat_model, llm_available, load_llm_settings


def _env(**overrides) -> dict:
    base = {
        "LLM_PROVIDER": "openrouter",
        "LLM_MODEL": "anthropic/claude-sonnet-4-6",
        "LLM_BASE_URL": "https://openrouter.ai/api/v1",
        "LLM_API_KEY": "k" * 25,
    }
    base.update(overrides)
    return base


def test_missing_env_returns_none_when_not_required():
    assert load_llm_settings(env={}, required=False) is None


def test_missing_env_raises_when_required():
    with pytest.raises(LLMConfigError):
        load_llm_settings(env={}, required=True)


def test_valid_settings_parse():
    settings = load_llm_settings(env=_env())
    assert settings == LLMSettings(
        provider="openrouter",
        model="anthropic/claude-sonnet-4-6",
        base_url="https://openrouter.ai/api/v1",
        api_key="k" * 25,
    )


def test_placeholder_key_is_rejected():
    assert load_llm_settings(env=_env(LLM_API_KEY="changeme"), required=False) is None
    with pytest.raises(LLMConfigError):
        load_llm_settings(env=_env(LLM_API_KEY="changeme"))


def test_custom_provider_requires_base_url():
    with pytest.raises(LLMConfigError):
        load_llm_settings(env=_env(LLM_PROVIDER="compat", LLM_BASE_URL=""))


def test_get_chat_model_openrouter():
    model = get_chat_model(load_llm_settings(env=_env()))
    assert type(model).__name__ == "ChatOpenRouter"


def test_get_chat_model_openai_compatible_defaults_to_chatopenai():
    env = _env(LLM_PROVIDER="compat", LLM_BASE_URL="https://api.example.com/v1")
    model = get_chat_model(load_llm_settings(env=env))
    assert type(model).__name__ == "ChatOpenAI"


def test_no_default_model_is_hardcoded():
    # A model name must never come from code: with an empty model it must fail.
    with pytest.raises(LLMConfigError):
        load_llm_settings(env=_env(LLM_MODEL=""))
    assert isinstance(llm_available(), bool)
