import logging
import os
from dataclasses import dataclass

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from utils.output import debug_log

logger = logging.getLogger(__name__)

INVALID_API_KEYS = {
    "mock-openai-key",
    "mock-google-key",
    "mock-key",
    "",
}

DEFAULT_MODELS = {
    "google": "gemini-2.5-flash",
    "openai": "gpt-4.1-mini",
    "ollama": "gemma3:4b",
}

DEFAULT_TIMEOUT_SECONDS = 30.0
MIN_GOOGLE_TIMEOUT_SECONDS = 10.0

_config_printed = False


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    key_source: str
    api_key: str


def provider_model_for_execution_mode(
    execution_mode: str | None,
) -> tuple[str | None, str | None]:
    """Return an explicit provider/model override for the given execution mode."""

    if (execution_mode or "").lower().strip() == "slm":
        return "ollama", DEFAULT_MODELS["ollama"]
    return None, None


def _validate_api_key(
    provider: str,
    api_key: str | None,
    key_source: str,
) -> None:
    """Validate API keys for cloud-based providers."""

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
    """Retrieve the corresponding provider API key from environment variables."""

    env_var = "OPENAI_API_KEY" if provider == "openai" else "GOOGLE_API_KEY"

    api_key = os.environ.get(env_var)
    key_source = env_var if api_key else "missing"

    return api_key, key_source


def _resolve_timeout(provider: str, kwargs: dict) -> float:
    if provider == "openai":
        raw_timeout = kwargs.get(
            "request_timeout",
            os.getenv("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        )
        return float(raw_timeout)

    raw_timeout = kwargs.get(
        "timeout",
        os.getenv("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
    )
    resolved_timeout = float(raw_timeout)
    return max(MIN_GOOGLE_TIMEOUT_SECONDS, resolved_timeout)


def resolve_provider(
    provider: str | None = None,
    model: str | None = None,
    **kwargs,
) -> LLMConfig:
    """
    Resolve the configured model provider.

    Supported providers:
        - google / gemini
        - openai
        - ollama / gemma / slm

    Default cloud-provider priority:
        1. Google
        2. OpenAI

    Ollama must be selected explicitly because it does not use an API key.
    """

    explicit_api_key = kwargs.pop("api_key", None)
    explicit_openai_key = kwargs.pop("openai_api_key", None)
    explicit_google_key = kwargs.pop("google_api_key", None)

    selected_provider = provider.lower().strip() if provider else None

    # Normalize provider aliases.
    if selected_provider == "gemini":
        selected_provider = "google"

    if selected_provider in {"gemma", "slm"}:
        selected_provider = "ollama"

    supported_providers = {
        "google",
        "openai",
        "ollama",
    }

    if selected_provider and selected_provider not in supported_providers:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            "Supported providers: google, openai, ollama"
        )

    # Automatically select a cloud provider when no provider was supplied.
    if not selected_provider:
        google_key = (
            explicit_google_key or explicit_api_key or os.environ.get("GOOGLE_API_KEY")
        )

        openai_key = (
            explicit_openai_key or explicit_api_key or os.environ.get("OPENAI_API_KEY")
        )

        if google_key and google_key not in INVALID_API_KEYS:
            selected_provider = "google"
        elif openai_key and openai_key not in INVALID_API_KEYS:
            selected_provider = "openai"
        else:
            raise ValueError(
                "No valid LLM API key configured. "
                "Set GOOGLE_API_KEY or OPENAI_API_KEY, "
                "or explicitly use provider='ollama'."
            )

    # Local Ollama does not require an API key.
    if selected_provider == "ollama":
        selected_model = (
            model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODELS["ollama"]
        )

        return LLMConfig(
            provider="ollama",
            model=selected_model,
            key_source="not_required_local",
            api_key="",
        )

    # Resolve Google or OpenAI credentials.
    if selected_provider == "google":
        api_key = explicit_google_key or explicit_api_key

        if explicit_google_key:
            key_source = "google_api_key argument"
        elif explicit_api_key:
            key_source = "api_key argument"
        else:
            api_key, key_source = _env_key("google")

        selected_model = (
            model or os.environ.get("GOOGLE_MODEL") or DEFAULT_MODELS["google"]
        )

    else:
        api_key = explicit_openai_key or explicit_api_key

        if explicit_openai_key:
            key_source = "openai_api_key argument"
        elif explicit_api_key:
            key_source = "api_key argument"
        else:
            api_key, key_source = _env_key("openai")

        selected_model = (
            model or os.environ.get("OPENAI_MODEL") or DEFAULT_MODELS["openai"]
        )

    _validate_api_key(
        selected_provider,
        api_key,
        key_source,
    )

    return LLMConfig(
        provider=selected_provider,
        model=selected_model,
        key_source=key_source,
        api_key=api_key,
    )


def print_llm_config_once(config: LLMConfig) -> None:
    """Print the active model configuration only once per program run."""

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


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    **kwargs,
):
    """
    Centralized LangChain chat-model factory.

    Supported providers:
        - openai
        - gemini / google
        - ollama / gemma / slm
    """

    config = resolve_provider(
        provider=provider,
        model=model,
        **kwargs,
    )

    # Remove provider-specific credential arguments before passing kwargs
    # into LangChain model constructors.
    kwargs.pop("api_key", None)
    kwargs.pop("openai_api_key", None)
    kwargs.pop("google_api_key", None)

    provider = config.provider

    print_llm_config_once(config)

    if provider == "openai":
        kwargs.setdefault(
            "max_retries",
            int(os.getenv("LLM_MAX_RETRIES", "2")),
        )
        kwargs["request_timeout"] = _resolve_timeout(provider, kwargs)

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

    if provider == "google":
        kwargs.setdefault(
            "max_retries",
            int(os.getenv("LLM_MAX_RETRIES", "2")),
        )
        kwargs["timeout"] = _resolve_timeout(provider, kwargs)

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

    if provider == "ollama":
        kwargs.setdefault(
            "temperature",
            float(os.getenv("OLLAMA_TEMPERATURE", "0.1")),
        )
        kwargs.setdefault(
            "num_ctx",
            int(os.getenv("OLLAMA_CONTEXT_LENGTH", "4096")),
        )
        kwargs.setdefault(
            "num_predict",
            int(os.getenv("OLLAMA_MAX_TOKENS", "1200")),
        )

        logger.debug(
            "[LLM PROVIDER] provider=%s model=%s execution=local",
            provider,
            config.model,
        )

        return ChatOllama(
            model=config.model,
            base_url=os.getenv(
                "OLLAMA_BASE_URL",
                "http://127.0.0.1:11434",
            ),
            **kwargs,
        )

    raise ValueError(
        f"Unsupported LLM provider: {provider}. "
        "Supported providers: openai, google, ollama"
    )
