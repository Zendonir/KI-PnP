"""Zentrale Konfiguration.

Alle Einstellungen kommen aus Umgebungsvariablen und werden typisiert
validiert. Es gibt genau eine Quelle fuer Konfiguration im gesamten Backend.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Laufzeitkonfiguration der Anwendung."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # --- Allgemein -----------------------------------------------------
    app_name: str = "KI-PnP"
    environment: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    public_base_url: str = "http://localhost:8080"
    """Basis-URL, unter der das Frontend erreichbar ist (fuer Beitrittslinks)."""

    # --- Datenbank -----------------------------------------------------
    database_url: str = "postgresql+asyncpg://kipnp:kipnp@db:5432/kipnp"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Realtime ------------------------------------------------------
    redis_url: str | None = None
    """Optional. Ohne Redis laeuft die Synchronisation prozesslokal."""

    # --- Auth ----------------------------------------------------------
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 60 * 60 * 24 * 30

    # --- KI ------------------------------------------------------------
    ai_provider: Literal["mock", "anthropic", "openai", "ollama"] = "mock"
    ai_model: str = "claude-opus-5"
    ai_max_tokens: int = 8000
    ai_timeout_seconds: float = 120.0
    ai_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_base_url: str = "http://ollama:11434"

    # --- TTS -----------------------------------------------------------
    tts_provider: Literal["none", "browser", "openai"] = "browser"
    """``browser`` spricht im Endgeraet, ``openai`` erzeugt Audio serverseitig."""

    tts_base_url: str = "https://api.openai.com/v1"
    """Auch fuer lokale, OpenAI-kompatible Dienste (Kokoro, openedai-speech ...)."""

    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "alloy"
    tts_format: Literal["mp3", "opus", "aac", "flac", "wav"] = "mp3"
    tts_api_key: str | None = None
    """Faellt auf ``openai_api_key`` zurueck. Lokale Dienste brauchen keinen."""

    tts_timeout_seconds: float = 120.0
    audio_keep_last: int = Field(default=200, ge=1)
    """So viele Sprachaufnahmen bleiben je Runde gespeichert, aeltere werden
    freigegeben. Das Ereignisprotokoll bleibt davon unberuehrt."""

    def resolved_tts_api_key(self) -> str | None:
        """Schluessel fuer die Sprachausgabe."""
        return self.tts_api_key or self.openai_api_key

    # --- Spielregeln ---------------------------------------------------
    default_ruleset: str = "classic"
    summary_every_n_events: int = Field(default=40, ge=5)
    context_recent_events: int = Field(default=25, ge=5)
    context_recent_summaries: int = Field(default=5, ge=1)
    max_players_per_game: int = Field(default=8, ge=1, le=32)

    # --- CORS ----------------------------------------------------------
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    """Liefert die (gecachte) Konfiguration."""
    return Settings()
