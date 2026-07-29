"""Anbieter fuer die Claude-API (Anthropic).

Nutzt das offizielle Anthropic-SDK. Standardmodell ist Claude Opus 5 mit
adaptivem Denken; die Denktiefe wird ueber ``output_config.effort``
gesteuert. Serverseitige Fallbacks sind aktiviert, damit eine abgelehnte
Anfrage nicht die ganze Spielrunde blockiert.
"""

from __future__ import annotations

import logging

from app.ai.base import LLMRequest, LLMResponse
from app.core.errors import AIError

logger = logging.getLogger(__name__)

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    """Spielleiter auf Basis der Claude Messages API."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-opus-5",
        effort: str = "high",
        timeout: float = 120.0,
        use_server_side_fallback: bool = True,
    ) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - Abhaengigkeit fehlt
            raise AIError("Das Paket 'anthropic' ist nicht installiert") from exc

        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout)
        self._model = model
        self._effort = effort
        self._use_fallback = use_server_side_fallback

    async def complete(self, request: LLMRequest) -> LLMResponse:
        params: dict[str, object] = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self._effort},
            "messages": [{"role": "user", "content": request.prompt}],
        }

        message = await self._create(params)
        if getattr(message, "stop_reason", None) == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise AIError(
                "Die KI hat die Anfrage abgelehnt.",
                details={"category": category or "unbekannt"},
            )

        text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )
        if not text.strip():
            raise AIError("Die KI hat keinen Text geliefert.")

        usage = getattr(message, "usage", None)
        return LLMResponse(
            text=text,
            model=getattr(message, "model", self._model),
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
        )

    async def _create(self, params: dict[str, object]):
        """Ruft die API auf; faellt bei abgelehntem Beta-Flag sauber zurueck."""
        if self._use_fallback:
            try:
                return await self._client.beta.messages.create(
                    **params, betas=[_FALLBACK_BETA], fallbacks="default"
                )
            except Exception as exc:  # noqa: BLE001 - Beta kann abgelehnt werden
                if not _is_bad_request(exc):
                    raise
                logger.warning(
                    "Serverseitiger Fallback nicht verfuegbar, nutze Standardaufruf: %s", exc
                )
                self._use_fallback = False
        return await self._client.messages.create(**params)

    async def aclose(self) -> None:
        await self._client.close()


def _is_bad_request(exc: Exception) -> bool:
    """Erkennt eine 400er-Antwort ohne harte SDK-Abhaengigkeit im Import."""
    status = getattr(exc, "status_code", None)
    return status == 400
