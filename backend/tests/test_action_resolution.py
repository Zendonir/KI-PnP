"""Tests der drei neuen Zugmechaniken.

Deckt ab: KI-gestuetzte Attributwahl fuer frei formulierte Handlungen, die
Trennung von Wuerfelmechanik und Erzaehlung (Wuerfel-Popup mit /continue),
und das seltene Quick-Time-Event (Vorteil durch rechtzeitige Hilfe).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.base import LLMRequest, LLMResponse
from app.ai.mock import MockLLMProvider
from app.core.config import Settings
from app.core.container import Container
from app.db.base import Base
from app.db.session import Database
from app.domain import dice
from app.main import create_app
from app.realtime.hub import EventHub
from app.services import interventions
from app.tts.providers import BrowserTTSProvider

from .conftest import auth
from .test_game_flow import _create_character, _create_game, _join, started_game  # noqa: F401

__all__ = ["started_game"]  # re-exportiert fuer die Fixture-Aufloesung von pytest


class FakeStatLLM:
    """Liefert eine feste Attributwahl, delegiert alles andere an den Mock."""

    name = "mock"

    def __init__(self, stat: str) -> None:
        self._stat = stat
        self._delegate = MockLLMProvider(seed=3)
        self.stat_calls: list[str] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if request.purpose == "stat_classify":
            self.stat_calls.append(request.prompt)
            return LLMResponse(text=json.dumps({"stat": self._stat}), model="fake")
        return await self._delegate.complete(request)

    async def aclose(self) -> None:
        await self._delegate.aclose()


@pytest.fixture
def stat_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'stat.db'}",
        ai_provider="mock",
        jwt_secret="test-secret",
        environment="test",
        summary_every_n_events=1000,
    )


@pytest.fixture
async def stat_container(stat_settings: Settings) -> AsyncIterator[Container]:
    instance = Container(
        settings=stat_settings,
        database=Database(stat_settings),
        hub=EventHub(None),
        llm=FakeStatLLM("strength"),
        tts=BrowserTTSProvider(),
    )
    async with instance.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield instance
    await instance.shutdown()


@pytest.fixture
async def stat_client(stat_container: Container) -> AsyncIterator[AsyncClient]:
    app = create_app(stat_container.settings, stat_container)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


class TestAttributKlassifikation:
    async def test_custom_action_uses_ai_chosen_stat(
        self, stat_client: AsyncClient, stat_container: Container
    ) -> None:
        """Eine frei formulierte Handlung ("Angreifen") soll auf das von der
        KI vorgeschlagene Attribut wuerfeln (hier: Staerke), nicht mehr immer
        auf Intelligenz."""
        session = await _create_game(stat_client)
        game_id = session["game"]["id"]
        await _create_character(stat_client, game_id, session["token"], "Kell", "Krieger")
        await stat_client.post(f"/api/v1/games/{game_id}/start", headers=auth(session["token"]))

        response = await stat_client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Ich greife an."},
            headers=auth(session["token"]),
        )
        assert response.status_code == 201, response.text

        state = (
            await stat_client.get(f"/api/v1/games/{game_id}/state", headers=auth(session["token"]))
        ).json()
        # Krieger: Staerke 14 (Bonus +2), Intelligenz bleibt bei 10 (Bonus 0).
        assert state["dice_rolls"][0]["modifier"] == 2, "Muss auf Staerke gewuerfelt haben"
        # Beweist, dass die Klassifikation tatsaechlich aufgerufen wurde.
        assert stat_container.llm.stat_calls  # type: ignore[attr-defined]

    async def test_classification_failure_falls_back_to_intelligence(
        self, client: AsyncClient
    ) -> None:
        """Der normale Mock-Spielleiter kennt "stat_classify" nicht und liefert
        kein "stat"-Feld -- das darf die Handlung nicht blockieren."""
        session = await _create_game(client)
        game_id = session["game"]["id"]
        await _create_character(client, game_id, session["token"], "Kell", "Krieger")
        await client.post(f"/api/v1/games/{game_id}/start", headers=auth(session["token"]))

        response = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Ich greife an."},
            headers=auth(session["token"]),
        )
        assert response.status_code == 201, response.text
        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(session["token"]))
        ).json()
        # Intelligenz bleibt bei 10 -> Bonus 0, wie vor dieser Funktion.
        assert state["dice_rolls"][0]["modifier"] == 0


class TestQuickTimeEvent:
    async def test_accepted_intervention_grants_advantage(
        self, client: AsyncClient, started_game: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        game_id = started_game["game_id"]
        host = started_game["host"]

        monkeypatch.setattr("app.services.turn_service.random.random", lambda: 0.0)

        async def always_accept(intervention_id: Any, *, timeout: float) -> bool:
            return True

        monkeypatch.setattr(interventions, "wait_for_response", always_accept)

        calls = {"n": 0}

        def fake_roll(
            notation: str, *, difficulty: int | None = None, bonus: int = 0, reason: str = ""
        ) -> dice.DiceResult:
            calls["n"] += 1
            total = 5 if calls["n"] == 1 else 25
            return dice.DiceResult(
                notation=notation,
                rolls=[total - bonus],
                modifier=bonus,
                total=total,
                difficulty=difficulty,
                success=difficulty is not None and total >= difficulty,
                degree="success",
                reason=reason,
            )

        monkeypatch.setattr("app.services.turn_service.dice.roll", fake_roll)

        # Nur der Gastgeber handelt -- die Spielleitung erzwingt trotzdem die
        # Aufloesung, damit genau eine Handlung im Spiel ist.
        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "attack", "text": "Ich greife an."},
            headers=auth(host["token"]),
        )
        await client.post(f"/api/v1/games/{game_id}/resolve", headers=auth(host["token"]))

        assert calls["n"] == 2, "Bei Vorteil muss zweimal gewuerfelt werden"
        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        assert state["dice_rolls"][0]["total"] == 25, "Der bessere der beiden Wuerfe muss zaehlen"
        helped = [e for e in state["events"] if e["type"] == "intervention.helped"]
        assert helped, "Der Eingriff muss im Ereignisprotokoll stehen"

    async def test_no_eligible_helper_skips_intervention(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ohne einen zweiten Spieler am selben Ort darf nichts angeboten
        werden, selbst wenn die Wahrscheinlichkeit erzwungen wird."""
        session = await _create_game(client)
        game_id = session["game"]["id"]
        await _create_character(client, game_id, session["token"], "Kell", "Krieger")
        await client.post(f"/api/v1/games/{game_id}/start", headers=auth(session["token"]))

        monkeypatch.setattr("app.services.turn_service.random.random", lambda: 0.0)

        calls = {"n": 0}
        original_roll = dice.roll

        def counting_roll(*args: Any, **kwargs: Any) -> dice.DiceResult:
            calls["n"] += 1
            return original_roll(*args, **kwargs)

        monkeypatch.setattr("app.services.turn_service.dice.roll", counting_roll)

        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "attack", "text": "Ich greife an."},
            headers=auth(session["token"]),
        )

        assert calls["n"] == 1, "Ohne moeglichen Helfer darf kein Vorteil entstehen"
        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(session["token"]))
        ).json()
        assert not [e for e in state["events"] if e["type"] == "intervention.helped"]
