"""Registry der KI-Anbieter (Plugin-Punkt)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.ai.base import LLMProvider
from app.ai.mock import MockLLMProvider
from app.core.config import Settings

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[Settings], LLMProvider]


def _build_anthropic(settings: Settings) -> LLMProvider:
    from app.ai.anthropic_provider import AnthropicProvider

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY fehlt - nutze Offline-Spielleiter.")
        return MockLLMProvider()
    return AnthropicProvider(
        api_key=settings.anthropic_api_key,
        model=settings.ai_model,
        effort=settings.ai_effort,
        timeout=settings.ai_timeout_seconds,
    )


def _build_openai(settings: Settings) -> LLMProvider:
    from app.ai.openai_provider import OpenAICompatibleProvider

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY fehlt - nutze Offline-Spielleiter.")
        return MockLLMProvider()
    return OpenAICompatibleProvider(
        api_key=settings.openai_api_key,
        model=settings.ai_model,
        base_url=settings.openai_base_url,
        timeout=settings.ai_timeout_seconds,
    )


def _build_ollama(settings: Settings) -> LLMProvider:
    from app.ai.openai_provider import OllamaProvider

    return OllamaProvider(
        model=settings.ai_model,
        base_url=settings.ollama_base_url,
        timeout=settings.ai_timeout_seconds,
    )


PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "mock": lambda _settings: MockLLMProvider(),
    "anthropic": _build_anthropic,
    "openai": _build_openai,
    "ollama": _build_ollama,
}


def create_provider(settings: Settings, name: str | None = None) -> LLMProvider:
    """Erzeugt den konfigurierten Anbieter."""
    key = (name or settings.ai_provider).lower()
    factory = PROVIDER_FACTORIES.get(key)
    if factory is None:
        logger.warning("Unbekannter KI-Anbieter %r - nutze Offline-Spielleiter.", key)
        return MockLLMProvider()
    return factory(settings)
