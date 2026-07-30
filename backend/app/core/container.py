"""Zusammenbau der Anwendung (Dependency Injection).

Der Container haelt die langlebigen Bausteine: Datenbank, Realtime-Hub,
KI-Anbieter und Sprachausgabe. Er wird beim Start einmal erzeugt und ueber
den FastAPI-Anwendungszustand bereitgestellt -- so laesst sich jeder
Baustein in Tests einzeln ersetzen.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.base import LLMProvider
from app.ai.registry import create_provider
from app.core.config import Settings, get_settings
from app.db.session import Database
from app.realtime.hub import EventHub
from app.tts.providers import TTSProvider, create_tts_provider


@dataclass(slots=True)
class Container:
    """Alle geteilten Abhaengigkeiten der Anwendung."""

    settings: Settings
    database: Database
    hub: EventHub
    llm: LLMProvider
    tts: TTSProvider

    @classmethod
    def create(cls, settings: Settings | None = None) -> Container:
        resolved = settings or get_settings()
        return cls(
            settings=resolved,
            database=Database(resolved),
            hub=EventHub(resolved.redis_url),
            llm=create_provider(resolved),
            tts=create_tts_provider(resolved),
        )

    async def startup(self) -> None:
        await self.hub.start()

    async def shutdown(self) -> None:
        await self.hub.stop()
        await self.llm.aclose()
        await self.tts.aclose()
        await self.database.dispose()
