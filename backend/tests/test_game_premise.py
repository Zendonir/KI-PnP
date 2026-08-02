"""Weltvorschau bei der Rundenerstellung.

Deckt ab: die kurze, von der KI erzeugte Vorschau landet in GameOut.premise,
und ein fehlschlagender KI-Aufruf darf die Rundenerstellung selbst nie
blockieren (siehe GameService._generate_premise).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.base import LLMRequest, LLMResponse
from app.ai.mock import MockLLMProvider
from app.core.config import Settings
from app.core.container import Container
from app.db.base import Base
from app.db.session import Database
from app.main import create_app
from app.realtime.hub import EventHub
from app.tts.providers import BrowserTTSProvider


class _FailingPremiseProvider:
    """Wirft bei purpose="premise", verhaelt sich sonst wie der Mock."""

    name = "failing-premise"

    def __init__(self) -> None:
        self._delegate = MockLLMProvider(seed=1)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if request.purpose == "premise":
            raise RuntimeError("KI nicht erreichbar")
        return await self._delegate.complete(request)

    async def aclose(self) -> None:
        return None


@pytest.fixture
def failing_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        ai_provider="mock",
        jwt_secret="test-secret",
        environment="test",
        public_base_url="http://testserver",
        summary_every_n_events=1000,
    )


@pytest.fixture
async def failing_container(failing_settings: Settings) -> AsyncIterator[Container]:
    instance = Container(
        settings=failing_settings,
        database=Database(failing_settings),
        hub=EventHub(None),
        llm=_FailingPremiseProvider(),
        tts=BrowserTTSProvider(),
    )
    async with instance.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield instance
    await instance.shutdown()


@pytest.fixture
async def failing_client(failing_container: Container) -> AsyncIterator[AsyncClient]:
    app = create_app(failing_container.settings, failing_container)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


class TestVorschauFehlschlag:
    async def test_rundenerstellung_blockiert_nicht_bei_ki_fehler(
        self, failing_client: AsyncClient
    ) -> None:
        response = await failing_client.post(
            "/api/v1/games",
            json={"name": "Ohne Vorschau", "host_name": "Sandra", "settings": {}},
        )
        assert response.status_code == 201, response.text
        assert response.json()["game"]["premise"] is None
