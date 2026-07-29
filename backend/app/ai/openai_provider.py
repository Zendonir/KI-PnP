"""Anbieter fuer OpenAI-kompatible Endpunkte und lokale Ollama-Modelle.

Beide sprechen HTTP-APIs mit sehr aehnlicher Form; die Antwort wird in beiden
Faellen als JSON-Text erwartet.
"""

from __future__ import annotations

import httpx

from app.ai.base import LLMRequest, LLMResponse
from app.core.errors import AIError


class OpenAICompatibleProvider:
    """Chat-Completions-API (OpenAI, vLLM, LM Studio, LiteLLM ...)."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ) -> None:
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
        }
        response = await self._client.post("/chat/completions", json=payload)
        if response.status_code >= 400:
            raise AIError(
                f"KI-Anbieter antwortete mit {response.status_code}: "
                f"{response.text[:300]}"
            )
        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError("Unerwartete Antwortstruktur des KI-Anbieters") from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text or "",
            model=data.get("model", self._model),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class OllamaProvider:
    """Lokales Modell ueber die Ollama-API."""

    name = "ollama"

    def __init__(self, *, model: str, base_url: str, timeout: float = 300.0) -> None:
        self._model = model
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "system": request.system,
            "prompt": request.prompt,
            "options": {"num_predict": request.max_tokens},
        }
        response = await self._client.post("/api/generate", json=payload)
        if response.status_code >= 400:
            raise AIError(f"Ollama antwortete mit {response.status_code}: {response.text[:300]}")
        data = response.json()
        return LLMResponse(text=str(data.get("response", "")), model=self._model)

    async def aclose(self) -> None:
        await self._client.aclose()
