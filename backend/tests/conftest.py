"""Gemeinsame Testvorrichtungen.

Die Tests laufen gegen SQLite und den Offline-Spielleiter: kein externer
Dienst, keine API-Schluessel, deterministisch.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.mock import MockLLMProvider
from app.core.config import Settings
from app.core.container import Container
from app.db.base import Base
from app.db.session import Database
from app.main import create_app
from app.realtime.hub import EventHub
from app.tts.providers import BrowserTTSProvider


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        ai_provider="mock",
        jwt_secret="test-secret",
        environment="test",
        public_base_url="http://testserver",
        summary_every_n_events=1000,
    )


@pytest.fixture
async def container(settings: Settings) -> AsyncIterator[Container]:
    instance = Container(
        settings=settings,
        database=Database(settings),
        hub=EventHub(None),
        llm=MockLLMProvider(seed=42),
        tts=BrowserTTSProvider(),
    )
    async with instance.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield instance
    await instance.shutdown()


@pytest.fixture
async def client(container: Container) -> AsyncIterator[AsyncClient]:
    app = create_app(container.settings, container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


def auth(token: str) -> dict[str, str]:
    """Authorization-Header fuer einen Spieler."""
    return {"Authorization": f"Bearer {token}"}
