import os
import logging
from dataclasses import dataclass
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.output import debug_log

logger = logging.getLogger(__name__)

INVALID_API_KEYS = {"mock-openai-key", "mock-google-key", "mock-key", ""}
DEFAULT_MODELS = {
    "google": "gemini-2.5-flash",
    "openai": "gpt-4.1-mini",
}
_config_printed = False


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    key_source: str
    api_key: str


def _validate_api_key(provider: str, api_key: str | None, key_source: str) -> None:
    if not api_key:
        raise ValueError(
            f"{provider.upper()} API key is not configured. "
            f"Expected a valid key from {key_source}."
        )

    if api_key in INVALID_API_KEYS:
        raise ValueError(
            f"{provider.upper()} API key from {key_source} is a placeholder. "
            "Configure a real API key before running LLM classification."
        )


def _env_key(provider: str) -> tuple[str | None, str]:
    env_var = "OPENAI_API_KEY" if provider == "openai" else "GOOGLE_API_KEY"
    api_key = os.environ.get(env_var)
    key_source = env_var if api_key else "missing"
    return api_key, key_source


def resolve_provider(provider: str | None = None, model: str | None = None, **kwargs) -> LLMConfig:
    """
    Resolves the LLM provider once for all agents/chains.

    Default priority:
      1. GOOGLE_API_KEY
      2. OPENAI_API_KEY

    Explicit provider/model arguments are honored as configuration, but still
    fail fast when the corresponding key is missing or a placeholder.
    """
    explicit_api_key = kwargs.pop("api_key", None)
    explicit_openai_key = kwargs.pop("openai_api_key", None)
    explicit_google_key = kwargs.pop("google_api_key", None)

    selected_provider = provider.lower() if provider else None
    if selected_provider == "gemini":
        selected_provider = "google"

    if selected_provider and selected_provider not in {"google", "openai"}:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. Supported providers: google, openai"
        )

    if not selected_provider:
        google_key = explicit_google_key or explicit_api_key or os.environ.get("GOOGLE_API_KEY")
        openai_key = explicit_openai_key or explicit_api_key or os.environ.get("OPENAI_API_KEY")

        if google_key and google_key not in INVALID_API_KEYS:
            selected_provider = "google"
        elif openai_key and openai_key not in INVALID_API_KEYS:
            selected_provider = "openai"
        else:
            raise ValueError(
                "No valid LLM API key configured. Set GOOGLE_API_KEY or OPENAI_API_KEY. "
                "Google is preferred when both are present."
            )

    if selected_provider == "google":
        api_key = explicit_google_key or explicit_api_key
        key_source = "google_api_key argument" if explicit_google_key else "api_key argument"
        if not api_key:
            api_key, key_source = _env_key("google")
    else:
        api_key = explicit_openai_key or explicit_api_key
        key_source = "openai_api_key argument" if explicit_openai_key else "api_key argument"
        if not api_key:
            api_key, key_source = _env_key("openai")

    selected_model = model or os.environ.get(
        "GOOGLE_MODEL" if selected_provider == "google" else "OPENAI_MODEL"
    ) or DEFAULT_MODELS[selected_provider]

    _validate_api_key(selected_provider, api_key, key_source)
    return LLMConfig(
        provider=selected_provider,
        model=selected_model,
        key_source=key_source,
        api_key=api_key,
    )


def print_llm_config_once(config: LLMConfig) -> None:
    global _config_printed
    if _config_printed:
        return

    debug_log(
        logger,
        "[LLM CONFIG] Provider: %s | Model: %s | Key Source: %s",
        config.provider,
        config.model,
        config.key_source,
    )
    _config_printed = True


def get_llm(provider: str | None = None, model: str | None = None, **kwargs):
    """
    Centralized provider factory for LangChain chat models.
    Supports:
        - openai
        - gemini / google

    Fails fast if required API keys are not configured.
    """

    config = resolve_provider(provider=provider, model=model, **kwargs)
    kwargs.pop("api_key", None)
    kwargs.pop("openai_api_key", None)
    kwargs.pop("google_api_key", None)
    provider = config.provider

    if provider == "openai":
        kwargs.setdefault("max_retries", int(os.getenv("LLM_MAX_RETRIES", "2")))
        kwargs.setdefault("request_timeout", float(os.getenv("LLM_TIMEOUT_SECONDS", "8")))
        logger.debug(
            "[LLM PROVIDER] provider=%s model=%s api_key_source=%s",
            provider,
            config.model,
            config.key_source,
        )

        return ChatOpenAI(
            model=config.model,
            openai_api_key=config.api_key,
            **kwargs,
        )

    elif provider in ["gemini", "google"]:
        kwargs.setdefault("max_retries", int(os.getenv("LLM_MAX_RETRIES", "2")))
        kwargs.setdefault("timeout", float(os.getenv("LLM_TIMEOUT_SECONDS", "8")))
        logger.debug(
            "[LLM PROVIDER] provider=%s model=%s api_key_source=%s",
            provider,
            config.model,
            config.key_source,
        )

        return ChatGoogleGenerativeAI(
            model=config.model,
            google_api_key=config.api_key,
            **kwargs,
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Supported providers: openai, gemini"
        )
