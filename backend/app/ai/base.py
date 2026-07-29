"""Provider-Abstraktion fuer Sprachmodelle.

Neue Anbieter (lokale Modelle, andere Clouds) werden durch Implementieren von
``LLMProvider`` und Registrieren in ``app.ai.registry`` ergaenzt.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from app.core.errors import AIError

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Eine Anfrage an das Sprachmodell."""

    system: str
    prompt: str
    max_tokens: int = 8000
    purpose: str = "narration"


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Rohantwort des Sprachmodells."""

    text: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    """Vertrag eines Sprachmodell-Anbieters."""

    name: str

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Erzeugt eine Antwort. Muss JSON-Text liefern."""

    async def aclose(self) -> None:
        """Gibt Ressourcen frei."""


def extract_json(text: str) -> dict[str, object]:
    """Extrahiert das erste JSON-Objekt aus einer Modellantwort.

    Sprachmodelle umschliessen JSON gelegentlich mit Code-Fences oder
    einleitendem Text. Diese Funktion ist bewusst tolerant, damit ein
    einzelnes Formatierungsdetail keine Spielrunde blockiert.
    """
    candidate = text.strip()
    if not candidate:
        raise AIError("Leere Antwort der KI")

    fenced = _JSON_BLOCK.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            raise AIError("Antwort der KI enthaelt kein JSON-Objekt")
        candidate = candidate[start : end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise AIError(f"Antwort der KI ist kein gueltiges JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise AIError("Antwort der KI ist kein JSON-Objekt")
    return parsed
