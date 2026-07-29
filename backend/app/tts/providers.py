"""Sprachausgabe (Text-to-Speech).

Die Anbieter sind austauschbar. Standard ist ``browser``: das Backend legt
lediglich einen Auftrag an, gesprochen wird im Browser des Spielers ueber die
Web-Speech-API. Damit funktioniert Audio ohne externe Dienste, und Ziele wie
Sonos, Chromecast oder Home Assistant lassen sich spaeter ergaenzen, ohne die
Aufrufer zu aendern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings

# Vorbereitete Ausgabeziele. ``browser`` ist implementiert, die uebrigen
# werden als Auftrag gespeichert und von einem Worker abgeholt.
AUDIO_TARGETS = ("browser", "sonos", "chromecast", "home_assistant", "airplay")


@dataclass(frozen=True, slots=True)
class SpeechRequest:
    text: str
    voice: str = "narrator"
    mood: str = ""


@dataclass(frozen=True, slots=True)
class SpeechResult:
    status: str
    """``ready``, ``pending``, ``skipped`` oder ``failed``."""

    url: str | None = None
    error: str | None = None
    meta: dict[str, str] | None = None


class TTSProvider(Protocol):
    """Vertrag eines Sprachausgabe-Anbieters."""

    name: str

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        """Erzeugt Audio oder markiert den Auftrag fuer eine andere Instanz."""


class NullTTSProvider:
    """Keine Sprachausgabe."""

    name = "none"

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        return SpeechResult(status="skipped")


class BrowserTTSProvider:
    """Client-seitige Ausgabe ueber die Web-Speech-API des Browsers."""

    name = "browser"

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        return SpeechResult(
            status="ready",
            url=None,
            meta={"engine": "web-speech", "voice": request.voice, "mood": request.mood},
        )


class OpenAITTSProvider:
    """Serverseitige Sprachsynthese ueber eine OpenAI-kompatible API.

    Bewusst als Auftrag modelliert: die eigentliche Erzeugung uebernimmt ein
    Worker, damit der Spielfluss nicht auf die Audiodatei wartet.
    """

    name = "openai"

    def __init__(self, *, api_key: str | None, voice: str) -> None:
        self._api_key = api_key
        self._voice = voice

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        if not self._api_key:
            return SpeechResult(status="failed", error="Kein API-Schluessel fuer TTS konfiguriert")
        return SpeechResult(status="pending", meta={"voice": request.voice or self._voice})


TTS_FACTORIES = {
    "none": lambda settings: NullTTSProvider(),
    "browser": lambda settings: BrowserTTSProvider(),
    "openai": lambda settings: OpenAITTSProvider(
        api_key=settings.openai_api_key, voice=settings.tts_voice
    ),
}


def create_tts_provider(settings: Settings, name: str | None = None) -> TTSProvider:
    """Erzeugt den konfigurierten TTS-Anbieter."""
    factory = TTS_FACTORIES.get((name or settings.tts_provider).lower())
    if factory is None:
        return BrowserTTSProvider()
    return factory(settings)
