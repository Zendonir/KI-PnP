"""Sprachausgabe (Text-to-Speech).

Zwei Betriebsarten:

* ``browser`` -- das Endgeraet spricht selbst ueber die Web-Speech-API. Kein
  Dienst, keine Kosten, aber Stimmqualitaet und Verfuegbarkeit haengen vom
  Geraet ab.
* ``openai`` -- der Server erzeugt eine Audiodatei und legt sie in der
  Datenbank ab. Weil die Schnittstelle ``POST /v1/audio/speech`` inzwischen
  von vielen Diensten nachgebildet wird, deckt derselbe Anbieter auch lokale
  Modelle ab: es genuegt, ``TTS_BASE_URL`` auf den eigenen Dienst zu richten
  (Kokoro-FastAPI, openedai-speech, speaches, LocalAI ...).

Erzeugt wird die Aufnahme nicht im Anfragepfad, sondern vom Medien-Worker --
so wartet niemand am Spieltisch auf die Tonspur.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Vorbereitete Ausgabeziele. ``browser`` ist implementiert, die uebrigen
# werden als Auftrag gespeichert und von einem Worker abgeholt.
AUDIO_TARGETS = ("browser", "sonos", "chromecast", "home_assistant", "airplay")

_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
}

# Laengere Erzaehltexte werden von manchen Diensten abgelehnt.
_MAX_INPUT_CHARS = 4000

# Aktuell dokumentierte OpenAI-Stimmen (platform.openai.com/docs/guides/
# text-to-speech). OpenAI ergaenzt gelegentlich neue -- eine spaetere
# Aktualisierung bleibt dank dieser einen Konstante eine Ein-Zeilen-Aenderung.
KNOWN_OPENAI_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "cedar",
    "coral",
    "echo",
    "fable",
    "marin",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
)


@dataclass(frozen=True, slots=True)
class SpeechRequest:
    text: str
    voice: str = ""
    speed: float | None = None
    mood: str = ""


@dataclass(frozen=True, slots=True)
class SpeechResult:
    """Ergebnis eines Synthesevorgangs."""

    status: str
    """``ready``, ``pending``, ``skipped`` oder ``failed``."""

    audio: bytes | None = None
    """Fertige Aufnahme. Nur bei ``ready`` und serverseitiger Erzeugung gesetzt."""

    mime_type: str | None = None
    url: str | None = None
    error: str | None = None
    meta: dict[str, str] = field(default_factory=dict)


class TTSProvider(Protocol):
    """Vertrag eines Sprachausgabe-Anbieters."""

    name: str

    @property
    def server_side(self) -> bool:
        """True, wenn der Server die Aufnahme erzeugt (Worker noetig)."""

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        """Erzeugt Audio oder markiert den Auftrag fuer eine andere Instanz."""

    async def aclose(self) -> None:
        """Gibt Ressourcen frei."""


class NullTTSProvider:
    """Keine Sprachausgabe."""

    name = "none"

    @property
    def server_side(self) -> bool:
        return False

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        return SpeechResult(status="skipped")

    async def aclose(self) -> None:
        return None


class BrowserTTSProvider:
    """Client-seitige Ausgabe ueber die Web-Speech-API des Browsers."""

    name = "browser"

    @property
    def server_side(self) -> bool:
        return False

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        return SpeechResult(
            status="ready",
            meta={"engine": "web-speech", "voice": request.voice, "mood": request.mood},
        )

    async def aclose(self) -> None:
        return None


class OpenAISpeechProvider:
    """Sprachsynthese ueber ``POST /v1/audio/speech``.

    Deckt die OpenAI-API und jeden dazu kompatiblen Dienst ab -- auch einen
    lokal betriebenen. Bei lokalen Diensten ist der Schluessel entbehrlich.
    """

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        voice: str,
        audio_format: str = "mp3",
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._voice = voice
        self._format = audio_format
        self._is_local = not _is_openai_host(self._base_url)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, headers=headers
        )

    @property
    def server_side(self) -> bool:
        return True

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        text = request.text.strip()
        if not text:
            return SpeechResult(status="skipped")
        if not self._api_key and not self._is_local:
            return SpeechResult(
                status="failed",
                error="Kein Schluessel fuer die Sprachausgabe konfiguriert.",
            )

        payload: dict[str, object] = {
            "model": self._model,
            "voice": request.voice or self._voice,
            "input": text[:_MAX_INPUT_CHARS],
            "response_format": self._format,
        }
        # Die Stimmung wird als Regieanweisung mitgegeben. Modelle, die das
        # nicht kennen, ignorieren das Feld; lokale Dienste lehnen es aber
        # gelegentlich ab, deshalb nur bei Bedarf.
        if request.mood and not self._is_local:
            payload["instructions"] = f"Sprich als Spielleiter, Stimmung: {request.mood}."
        if request.speed is not None:
            payload["speed"] = request.speed

        try:
            response = await self._client.post("/audio/speech", json=payload)
        except httpx.HTTPError as exc:
            return SpeechResult(status="failed", error=f"Dienst nicht erreichbar: {exc}")

        if response.status_code >= 400:
            detail = response.text[:300]
            # Ein unbekanntes optionales Feld soll den Auftrag nicht kosten --
            # manche lokalen Dienste kennen "instructions" oder "speed" nicht.
            unknown_fields = [
                field for field in ("instructions", "speed") if field in payload and field in detail
            ]
            if unknown_fields:
                for field in unknown_fields:
                    payload.pop(field, None)
                try:
                    response = await self._client.post("/audio/speech", json=payload)
                except httpx.HTTPError as exc:
                    return SpeechResult(status="failed", error=f"Dienst nicht erreichbar: {exc}")
            if response.status_code >= 400:
                return SpeechResult(
                    status="failed",
                    error=f"Sprachausgabe antwortete mit {response.status_code}: {detail}",
                )

        audio = response.content
        if not audio:
            return SpeechResult(status="failed", error="Der Dienst lieferte keine Audiodaten.")

        return SpeechResult(
            status="ready",
            audio=audio,
            mime_type=response.headers.get("content-type")
            or _MIME_TYPES.get(self._format, "audio/mpeg"),
            meta={
                "model": self._model,
                "voice": str(payload["voice"]),
                "bytes": str(len(audio)),
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _is_openai_host(base_url: str) -> bool:
    return "api.openai.com" in base_url


def create_tts_provider(settings: Settings, name: str | None = None) -> TTSProvider:
    """Erzeugt den konfigurierten TTS-Anbieter."""
    key = (name or settings.tts_provider).lower()
    if key == "none":
        return NullTTSProvider()
    if key == "browser":
        return BrowserTTSProvider()
    if key == "openai":
        api_key = settings.resolved_tts_api_key()
        if not api_key and _is_openai_host(settings.tts_base_url):
            logger.warning(
                "Sprachausgabe 'openai' ohne Schluessel - es wird im Browser gesprochen."
            )
            return BrowserTTSProvider()
        return OpenAISpeechProvider(
            api_key=api_key,
            base_url=settings.tts_base_url,
            model=settings.tts_model,
            voice=settings.tts_voice,
            audio_format=settings.tts_format,
            timeout=settings.tts_timeout_seconds,
        )
    logger.warning("Unbekannter TTS-Anbieter %r - es wird im Browser gesprochen.", key)
    return BrowserTTSProvider()
