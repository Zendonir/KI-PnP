"""Tests der Sprachausgabe.

Deckt ab: Synthese gegen eine nachgebildete OpenAI-Schnittstelle, das
Anlegen offener Auftraege, die Abarbeitung durch den Worker, das Ausliefern
der Aufnahme und die Zugangspruefung.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from app.ai.mock import MockLLMProvider
from app.core.config import Settings
from app.core.container import Container
from app.db.base import Base, utcnow
from app.db.models import AudioJob
from app.db.session import Database
from app.main import create_app
from app.realtime.hub import EventHub
from app.tts.providers import (
    BrowserTTSProvider,
    NullTTSProvider,
    OpenAISpeechProvider,
    SpeechRequest,
    SpeechResult,
    create_tts_provider,
)
from app.workers.media import process_once, prune_audio, recover_stale_jobs

from .conftest import auth

FAKE_MP3 = b"ID3\x03\x00\x00\x00" + b"\xff\xfb\x90\x00" * 40


class FakeServerTTS:
    """Serverseitiger Anbieter, der eine feste Aufnahme liefert."""

    name = "openai"

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[SpeechRequest] = []
        self._fail = fail

    @property
    def server_side(self) -> bool:
        return True

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        self.calls.append(request)
        if self._fail:
            return SpeechResult(status="failed", error="Dienst nicht erreichbar")
        return SpeechResult(
            status="ready",
            audio=FAKE_MP3,
            mime_type="audio/mpeg",
            meta={"model": "gpt-4o-mini-tts"},
        )

    async def aclose(self) -> None:
        return None


class TestProviderAuswahl:
    def test_browser_ist_nicht_serverseitig(self) -> None:
        assert BrowserTTSProvider().server_side is False
        assert NullTTSProvider().server_side is False

    def test_openai_ohne_schluessel_faellt_auf_browser_zurueck(self, tmp_path: Path) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///./x.db",
            tts_provider="openai",
            openai_api_key=None,
        )
        assert create_tts_provider(settings).name == "browser"

    def test_lokaler_dienst_braucht_keinen_schluessel(self) -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///./x.db",
            tts_provider="openai",
            tts_base_url="http://kokoro:8880/v1",
            openai_api_key=None,
        )
        provider = create_tts_provider(settings)
        assert provider.name == "openai"
        assert provider.server_side is True

    def test_unbekannter_anbieter_faellt_zurueck(self) -> None:
        settings = Settings(database_url="sqlite+aiosqlite:///./x.db")
        assert create_tts_provider(settings, "gibt-es-nicht").name == "browser"


class TestOpenAISynthese:
    def _provider(self, handler: Any, **kwargs: Any) -> OpenAISpeechProvider:
        provider = OpenAISpeechProvider(
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini-tts",
            voice="alloy",
            **kwargs,
        )
        provider._client = httpx.AsyncClient(  # noqa: SLF001 - Testdoppel
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handler)
        )
        return provider

    async def test_liefert_audiodaten(self) -> None:
        gesehen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            gesehen.update(json.loads(request.content))
            assert request.url.path.endswith("/audio/speech")
            return httpx.Response(200, content=FAKE_MP3, headers={"content-type": "audio/mpeg"})

        provider = self._provider(handler)
        result = await provider.synthesize(
            SpeechRequest(text="Der Brunnen ist trocken.", voice="nova", mood="angespannt")
        )
        await provider.aclose()

        assert result.status == "ready"
        assert result.audio == FAKE_MP3
        assert result.mime_type == "audio/mpeg"
        assert gesehen["voice"] == "nova"
        assert gesehen["model"] == "gpt-4o-mini-tts"
        assert gesehen["input"] == "Der Brunnen ist trocken."

    async def test_leerer_text_wird_uebersprungen(self) -> None:
        provider = self._provider(lambda request: httpx.Response(200, content=b""))
        result = await provider.synthesize(SpeechRequest(text="   "))
        await provider.aclose()
        assert result.status == "skipped"

    async def test_fehler_wird_gemeldet_nicht_geworfen(self) -> None:
        provider = self._provider(
            lambda request: httpx.Response(401, text='{"error":"invalid key"}')
        )
        result = await provider.synthesize(SpeechRequest(text="Hallo"))
        await provider.aclose()
        assert result.status == "failed"
        assert "401" in (result.error or "")

    async def test_netzwerkfehler_wird_gemeldet(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("keine Verbindung")

        provider = self._provider(handler)
        result = await provider.synthesize(SpeechRequest(text="Hallo"))
        await provider.aclose()
        assert result.status == "failed"
        assert "erreichbar" in (result.error or "")

    async def test_langer_text_wird_gekuerzt(self) -> None:
        laenge: dict[str, int] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            laenge["n"] = len(json.loads(request.content)["input"])
            return httpx.Response(200, content=FAKE_MP3)

        provider = self._provider(handler)
        await provider.synthesize(SpeechRequest(text="a" * 9000))
        await provider.aclose()
        assert laenge["n"] == 4000


# --- Ablauf mit serverseitiger Stimme ---------------------------------


@pytest.fixture
def audio_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'audio.db'}",
        ai_provider="mock",
        tts_provider="openai",
        jwt_secret="test-secret",
        environment="test",
        summary_every_n_events=1000,
        audio_keep_last=3,
    )


@pytest.fixture
async def audio_container(audio_settings: Settings) -> AsyncIterator[Container]:
    instance = Container(
        settings=audio_settings,
        database=Database(audio_settings),
        hub=EventHub(None),
        llm=MockLLMProvider(seed=7),
        tts=FakeServerTTS(),
    )
    async with instance.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield instance
    await instance.shutdown()


@pytest.fixture
async def audio_client(audio_container: Container) -> AsyncIterator[AsyncClient]:
    app = create_app(audio_container.settings, audio_container)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def _spiel_starten(client: AsyncClient) -> dict[str, Any]:
    created = await client.post(
        "/api/v1/games",
        json={"name": "Tonprobe", "host_name": "Sandra", "settings": {"world": "Aschenfurt"}},
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


class TestAuftragsablauf:
    async def test_auftrag_bleibt_offen_bis_der_worker_laeuft(
        self, audio_client: AsyncClient, audio_container: Container
    ) -> None:
        spiel = await _spiel_starten(audio_client)
        state = (
            await audio_client.get(
                f"/api/v1/games/{spiel['game_id']}/state", headers=auth(spiel["token"])
            )
        ).json()

        assert state["audio"] is not None
        assert state["audio"]["status"] == "pending", "Der Spieltisch darf nicht warten"
        assert state["audio"]["provider"] == "openai"

    async def test_worker_erzeugt_aufnahme_und_sie_ist_abrufbar(
        self, audio_client: AsyncClient, audio_container: Container
    ) -> None:
        spiel = await _spiel_starten(audio_client)

        bearbeitet = await process_once(audio_container, audio_container.settings)
        assert bearbeitet == 1
        assert len(audio_container.tts.calls) == 1  # type: ignore[attr-defined]

        state = (
            await audio_client.get(
                f"/api/v1/games/{spiel['game_id']}/state", headers=auth(spiel["token"])
            )
        ).json()
        assert state["audio"]["status"] == "ready"
        assert state["audio"]["url"].endswith(state["audio"]["id"])

        antwort = await audio_client.get(
            f"/api/v1/games/{spiel['game_id']}/audio/{state['audio']['id']}",
            headers=auth(spiel["token"]),
        )
        assert antwort.status_code == 200
        assert antwort.headers["content-type"].startswith("audio/")
        assert antwort.content == FAKE_MP3

    async def test_aufnahme_ohne_token_ist_nicht_erreichbar(
        self, audio_client: AsyncClient, audio_container: Container
    ) -> None:
        spiel = await _spiel_starten(audio_client)
        await process_once(audio_container, audio_container.settings)
        state = (
            await audio_client.get(
                f"/api/v1/games/{spiel['game_id']}/state", headers=auth(spiel["token"])
            )
        ).json()

        ohne = await audio_client.get(
            f"/api/v1/games/{spiel['game_id']}/audio/{state['audio']['id']}"
        )
        assert ohne.status_code == 401

    async def test_aufnahme_fremder_runde_wird_verweigert(
        self, audio_client: AsyncClient, audio_container: Container
    ) -> None:
        erste = await _spiel_starten(audio_client)
        await process_once(audio_container, audio_container.settings)
        state = (
            await audio_client.get(
                f"/api/v1/games/{erste['game_id']}/state", headers=auth(erste["token"])
            )
        ).json()
        audio_id = state["audio"]["id"]

        zweite = await _spiel_starten(audio_client)
        fremd = await audio_client.get(
            f"/api/v1/games/{zweite['game_id']}/audio/{audio_id}",
            headers=auth(zweite["token"]),
        )
        assert fremd.status_code == 404

    async def test_unbekannte_aufnahme_ergibt_404(
        self, audio_client: AsyncClient, audio_container: Container
    ) -> None:
        spiel = await _spiel_starten(audio_client)
        antwort = await audio_client.get(
            f"/api/v1/games/{spiel['game_id']}/audio/{uuid.uuid4()}",
            headers=auth(spiel["token"]),
        )
        assert antwort.status_code == 404

    async def test_fehlgeschlagene_synthese_blockiert_das_spiel_nicht(
        self, audio_client: AsyncClient, audio_container: Container
    ) -> None:
        spiel = await _spiel_starten(audio_client)
        audio_container.tts = FakeServerTTS(fail=True)  # type: ignore[assignment]

        await process_once(audio_container, audio_container.settings)

        state = (
            await audio_client.get(
                f"/api/v1/games/{spiel['game_id']}/state", headers=auth(spiel["token"])
            )
        ).json()
        assert state["audio"]["status"] == "failed"
        assert state["audio"]["error"]
        # Die Runde selbst laeuft weiter.
        assert state["game"]["status"] == "active"
        assert state["narrations"]

    async def test_leerlauf_wenn_nichts_offen_ist(self, audio_container: Container) -> None:
        assert await process_once(audio_container, audio_container.settings) == 0


class TestAufraeumen:
    async def test_haengende_auftraege_werden_zurueckgesetzt(
        self, audio_client: AsyncClient, audio_container: Container
    ) -> None:
        spiel = await _spiel_starten(audio_client)
        async with audio_container.database.session() as session:
            job = (
                await session.execute(
                    sa.select(AudioJob).where(AudioJob.game_id == uuid.UUID(spiel["game_id"]))
                )
            ).scalars().first()
            assert job is not None
            job.status = "running"
            # Bewusst mit derselben Hilfsfunktion wie der Worker, damit beide
            # Seiten des Vergleichs zeitzonenbewusst sind.
            job.updated_at = utcnow() - timedelta(days=1)
            await session.commit()

            assert await recover_stale_jobs(session) == 1
            # Der Bulk-Update laeuft als reines SQL, der Objektcache weiss
            # davon nichts -- daher bewusst neu laden (mit await, sonst
            # versucht SQLAlchemy die Abfrage synchron nachzuholen).
            await session.refresh(job)
            assert job.status == "pending"

    async def test_alte_aufnahmen_werden_freigegeben(
        self, audio_client: AsyncClient, audio_container: Container
    ) -> None:
        spiel = await _spiel_starten(audio_client)
        game_id = uuid.UUID(spiel["game_id"])

        # Fuenf fertige Aufnahmen anlegen, obwohl nur drei behalten werden.
        async with audio_container.database.session() as session:
            for index in range(5):
                session.add(
                    AudioJob(
                        game_id=game_id,
                        provider="openai",
                        status="ready",
                        text=f"Aufnahme {index}",
                        data=FAKE_MP3,
                        mime_type="audio/mpeg",
                        size_bytes=len(FAKE_MP3),
                    )
                )
            await session.commit()

            freigegeben = await prune_audio(session, game_id, keep_last=3)
            await session.commit()
            assert freigegeben >= 2

            verbleibend = (
                await session.execute(
                    sa.select(sa.func.count())
                    .select_from(AudioJob)
                    .where(AudioJob.game_id == game_id, AudioJob.data.isnot(None))
                )
            ).scalar_one()
            assert verbleibend == 3

    async def test_abspielziel_none_erzeugt_keinen_auftrag(
        self, audio_client: AsyncClient, audio_container: Container
    ) -> None:
        created = await audio_client.post(
            "/api/v1/games",
            json={
                "name": "Stille",
                "host_name": "Sandra",
                "settings": {"audio_playback": "none"},
            },
        )
        session_data = created.json()
        game_id = session_data["game"]["id"]
        await audio_client.post(
            f"/api/v1/games/{game_id}/characters",
            json={"name": "Kell", "class": "Krieger"},
            headers=auth(session_data["token"]),
        )
        await audio_client.post(
            f"/api/v1/games/{game_id}/start", headers=auth(session_data["token"])
        )

        state = (
            await audio_client.get(
                f"/api/v1/games/{game_id}/state", headers=auth(session_data["token"])
            )
        ).json()
        assert state["audio"] is None
        assert state["game"]["settings"]["audio_playback"] == "none"
