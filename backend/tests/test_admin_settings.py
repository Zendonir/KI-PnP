"""Tests des passwortgeschuetzten, installationsweiten Settings-Menues.

Deckt ab: Anmeldung, die fail-closed-Deaktivierung ohne ``SETTINGS_PASSWORD``,
die saubere Trennung von Spieler- und Settings-Token in beide Richtungen,
das Lesen/Schreiben der Laufzeit-Werte und die Auswirkung einer Aenderung
auf die naechste tatsaechlich gesendete Sprachausgabe.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.mock import MockLLMProvider
from app.api.v1 import settings_admin
from app.core.config import Settings
from app.core.container import Container
from app.core.security import decode_operator_token
from app.db.base import Base
from app.db.session import Database
from app.main import create_app
from app.realtime.hub import EventHub
from app.workers.media import process_once

from .conftest import auth
from .test_audio import FakeServerTTS


@pytest.fixture(autouse=True)
def _reset_login_attempts() -> None:
    """Die Sperrliste ist Modulzustand -- ohne Reset wuerde ein Test die
    Adresse fuer alle folgenden im selben Prozess sperren."""
    settings_admin._LOGIN_ATTEMPTS.clear()


@pytest.fixture
def admin_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'admin.db'}",
        ai_provider="mock",
        tts_provider="openai",
        jwt_secret="test-secret",
        environment="test",
        summary_every_n_events=1000,
        settings_password="test-settings-pw",
    )


@pytest.fixture
async def admin_container(admin_settings: Settings) -> AsyncIterator[Container]:
    instance = Container(
        settings=admin_settings,
        database=Database(admin_settings),
        hub=EventHub(None),
        llm=MockLLMProvider(seed=7),
        tts=FakeServerTTS(),
    )
    async with instance.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield instance
    await instance.shutdown()


@pytest.fixture
async def admin_client(admin_container: Container) -> AsyncIterator[AsyncClient]:
    app = create_app(admin_container.settings, admin_container)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def _spiel_starten(client: AsyncClient) -> dict[str, Any]:
    created = await client.post(
        "/api/v1/games",
        json={"name": "Einstellungen", "host_name": "Sandra", "settings": {"world": "Aschenfurt"}},
    )
    session = created.json()
    game_id = session["game"]["id"]
    await client.post(
        f"/api/v1/games/{game_id}/characters",
        json={"name": "Kell", "class": "Krieger"},
        headers=auth(session["token"]),
    )
    await client.post(f"/api/v1/games/{game_id}/start", headers=auth(session["token"]))
    return {"game_id": game_id, "token": session["token"]}


async def _login(client: AsyncClient, password: str = "test-settings-pw") -> str:
    response = await client.post("/api/v1/settings/login", json={"password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]  # type: ignore[no-any-return]


class TestAnmeldung:
    async def test_falsches_kennwort_scheitert(self, admin_client: AsyncClient) -> None:
        response = await admin_client.post(
            "/api/v1/settings/login", json={"password": "falsch"}
        )
        assert response.status_code == 401

    async def test_richtiges_kennwort_liefert_gueltiges_token(
        self, admin_client: AsyncClient, admin_settings: Settings
    ) -> None:
        token = await _login(admin_client)
        payload = decode_operator_token(admin_settings, token)
        assert payload.issued_at is not None

    async def test_ohne_gesetztes_kennwort_ist_der_bereich_deaktiviert(
        self, client: AsyncClient
    ) -> None:
        status = await client.get("/api/v1/settings/status")
        assert status.json() == {"enabled": False}

        login = await client.post("/api/v1/settings/login", json={"password": "irgendwas"})
        assert login.status_code == 401

    async def test_status_meldet_aktiviert(self, admin_client: AsyncClient) -> None:
        status = await admin_client.get("/api/v1/settings/status")
        assert status.json() == {"enabled": True}

    async def test_nach_fuenf_fehlversuchen_wird_gesperrt(
        self, admin_client: AsyncClient
    ) -> None:
        for _ in range(5):
            response = await admin_client.post(
                "/api/v1/settings/login", json={"password": "falsch"}
            )
            assert response.status_code == 401
        gesperrt = await admin_client.post(
            "/api/v1/settings/login", json={"password": "test-settings-pw"}
        )
        assert gesperrt.status_code == 429


class TestTokentrennung:
    async def test_spieler_token_wird_am_settings_endpunkt_abgelehnt(
        self, admin_client: AsyncClient
    ) -> None:
        spiel = await _spiel_starten(admin_client)
        response = await admin_client.get(
            "/api/v1/settings", headers=auth(spiel["token"])
        )
        assert response.status_code == 401

    async def test_settings_token_wird_am_spiel_endpunkt_abgelehnt(
        self, admin_client: AsyncClient
    ) -> None:
        spiel = await _spiel_starten(admin_client)
        token = await _login(admin_client)
        response = await admin_client.get(
            f"/api/v1/games/{spiel['game_id']}/state", headers=auth(token)
        )
        assert response.status_code == 401


class TestLaufzeitWerte:
    async def test_ohne_bestehende_zeile_gelten_die_umgebungsvariablen(
        self, admin_client: AsyncClient, admin_settings: Settings
    ) -> None:
        token = await _login(admin_client)
        response = await admin_client.get("/api/v1/settings", headers=auth(token))
        assert response.status_code == 200
        body = response.json()
        assert body["tts_voice"] == admin_settings.tts_voice
        assert body["tts_speed"] == 1.0
        assert body["voice_source"] == "openai"
        assert "alloy" in body["known_voices"]

    async def test_geaenderte_werte_erreichen_die_naechste_sprachausgabe(
        self, admin_client: AsyncClient, admin_container: Container
    ) -> None:
        token = await _login(admin_client)
        update = await admin_client.put(
            "/api/v1/settings",
            json={"tts_voice": "verse", "tts_speed": 1.5},
            headers=auth(token),
        )
        assert update.status_code == 200
        assert update.json()["tts_voice"] == "verse"
        assert update.json()["tts_speed"] == 1.5

        await _spiel_starten(admin_client)
        await process_once(admin_container, admin_container.settings)

        calls = admin_container.tts.calls  # type: ignore[attr-defined]
        assert calls[-1].voice == "verse"
        assert calls[-1].speed == 1.5

    async def test_voice_source_ist_custom_bei_abweichender_basis_url(
        self, tmp_path: Path
    ) -> None:
        settings = Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'custom.db'}",
            ai_provider="mock",
            tts_provider="openai",
            tts_base_url="http://kokoro:8880/v1",
            jwt_secret="test-secret",
            environment="test",
            settings_password="test-settings-pw",
        )
        instance = Container(
            settings=settings,
            database=Database(settings),
            hub=EventHub(None),
            llm=MockLLMProvider(seed=7),
            tts=FakeServerTTS(),
        )
        async with instance.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        app = create_app(settings, instance)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            token = await _login(client)
            response = await client.get("/api/v1/settings", headers=auth(token))
            assert response.json()["voice_source"] == "custom"
        await instance.shutdown()
