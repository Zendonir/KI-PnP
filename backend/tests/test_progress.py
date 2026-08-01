"""Tests fuer spuerbaren Fortschritt.

Deckt ab: Quest-Fortschrittsvermerke landen im KI-Kontext und in der
Spielsicht, der Stillstands-Zaehler laesst sich nicht mehr durch beliebige
Atmosphaere-Aenderungen zuruecksetzen, Erfahrung waechst bei gewoehnlichen
Proben und beim Quest-Abschluss, und der Spannungsbogen leitet sich aus der
gewaehlten Spieldauer ab.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.core.container import Container
from app.domain import dice
from app.domain.rules import XP_PER_DEGREE, experience_for_next_level
from app.services.context import EXPECTED_TURNS, arc_phase
from app.services.turn_service import _PROGRESS_OPS

from .conftest import auth
from .test_game_flow import started_game  # noqa: F401

__all__ = ["started_game"]


def _always_succeeds(
    notation: str, *, difficulty: int | None = None, bonus: int = 0, reason: str = ""
) -> dice.DiceResult:
    return dice.DiceResult(
        notation=notation,
        rolls=[20],
        modifier=bonus,
        total=99,
        difficulty=difficulty,
        success=True,
        degree="success",
        reason=reason,
    )


async def _act(
    client: AsyncClient, game_id: str, *sessions: dict[str, Any]
) -> None:
    for session in sessions:
        response = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Wir gehen der Sache nach.", "stat": "strength"},
            headers=auth(session["token"]),
        )
        assert response.status_code == 201, response.text


async def _state(client: AsyncClient, game_id: str, token: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/games/{game_id}/state", headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


class TestQuestFortschritt:
    async def test_vermerk_erscheint_in_der_spielsicht(
        self, client: AsyncClient, started_game: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ohne sichtbaren Vermerk sehen Spieler nur einen Status-Badge und
        koennen nicht erkennen, ob sich ueberhaupt etwas bewegt hat."""
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]
        monkeypatch.setattr("app.services.turn_service.dice.roll", _always_succeeds)

        await _act(client, game_id, host, guest)
        state = await _state(client, game_id, host["token"])

        noted = [quest for quest in state["quests"] if quest["note"]]
        assert noted, "Nach einem erfolgreichen Zug muss eine Quest einen Vermerk tragen"
        assert noted[0]["turn_number"] >= 1

    async def test_vermerk_geht_in_den_ki_kontext(
        self, client: AsyncClient, started_game: dict[str, Any], container: Container,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Der Vermerk ist im naechsten Zug die einzige Erinnerung der KI
        daran, wo die Gruppe in der Quest steht."""
        from app.db.models import Game
        from app.services.context import ContextBuilder

        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]
        monkeypatch.setattr("app.services.turn_service.dice.roll", _always_succeeds)
        await _act(client, game_id, host, guest)

        async with container.database.session() as session:
            import uuid as _uuid

            game = await session.get(Game, _uuid.UUID(game_id))
            assert game is not None
            builder = ContextBuilder(session, game, container.settings)
            context = await builder.build_turn_context(None)

        with_progress = [
            quest for quest in context["quests"] if quest.get("latest_progress")
        ]
        assert with_progress, "Der Fortschrittsvermerk fehlt im KI-Kontext"


class TestStillstandStrenger:
    def test_atmosphaere_zaehlt_nicht_als_fortschritt(self) -> None:
        """Sonst laesst sich der Zaehler mit einem beliebigen Fakt oder einem
        dahergelaufenen NSC zuruecksetzen, ohne dass sich etwas bewegt."""
        assert "fact.assert" not in _PROGRESS_OPS
        assert "entity.create" not in _PROGRESS_OPS
        assert "location.create" not in _PROGRESS_OPS

    def test_echter_fortschritt_zaehlt_weiterhin(self) -> None:
        assert "quest.update" in _PROGRESS_OPS
        assert "location.discover" in _PROGRESS_OPS
        assert "character.move" in _PROGRESS_OPS


class TestErfahrung:
    def test_auch_ein_fehlschlag_bringt_etwas(self) -> None:
        assert XP_PER_DEGREE["failure"] > 0
        assert XP_PER_DEGREE["success"] > XP_PER_DEGREE["partial"] > XP_PER_DEGREE["failure"]

    def test_erste_stufe_liegt_in_reichweite(self) -> None:
        """Die frueheren level*100 waren mit Erfahrung nur bei kritischen
        Erfolgen praktisch unerreichbar."""
        proben_bis_stufe_2 = experience_for_next_level(1) / XP_PER_DEGREE["success"]
        assert proben_bis_stufe_2 <= 12

    async def test_gewoehnlicher_erfolg_bringt_erfahrung(
        self, client: AsyncClient, started_game: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]
        vorher = (await _state(client, game_id, host["token"]))["my_character"]["experience"]

        monkeypatch.setattr("app.services.turn_service.dice.roll", _always_succeeds)
        await _act(client, game_id, host, guest)

        nachher = (await _state(client, game_id, host["token"]))["my_character"]
        assert nachher["experience"] > vorher or nachher["level"] > 1
        assert nachher["experience_to_next_level"] > 0

    async def test_quest_abschluss_belohnt_die_gruppe(
        self, client: AsyncClient, started_game: dict[str, Any], container: Container,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Der greifbarste Fortschrittsmoment einer Runde muss sich auch
        mechanisch niederschlagen."""
        import sqlalchemy as sa

        from app.db.models import Game, Turn
        from app.domain.rules import XP_MAIN_QUEST_COMPLETED

        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]
        monkeypatch.setattr("app.services.turn_service.dice.roll", _always_succeeds)

        # Den laufenden Zug in die Abschlussphase des Bogens schieben, damit
        # der Offline-Spielleiter die Hauptquest abschliesst. Der Bogen
        # richtet sich nach der Nummer *dieses* Zuges, nicht nach der
        # hoechsten je vergebenen -- bei getrennten Orten laufen die
        # auseinander.
        async with container.database.session() as session:
            import uuid as _uuid

            game = await session.get(Game, _uuid.UUID(game_id))
            assert game is not None
            game.current_turn_number = EXPECTED_TURNS["medium"]
            turn = (
                await session.execute(
                    sa.select(Turn).where(
                        Turn.game_id == game.id, Turn.status == "collecting"
                    )
                )
            ).scalars().first()
            assert turn is not None
            turn.number = EXPECTED_TURNS["medium"]
            await session.commit()

        await _act(client, game_id, host, guest)
        state = await _state(client, game_id, host["token"])

        erreicht = state["my_character"]["level"] > 1 or (
            state["my_character"]["experience"] >= XP_MAIN_QUEST_COMPLETED
        )
        assert erreicht, "Der Quest-Abschluss muss deutlich Erfahrung bringen"


class TestSpannungsbogen:
    def test_phasen_folgen_der_spieldauer(self) -> None:
        assert arc_phase(1, "oneshot")[0] == "setup"
        assert arc_phase(8, "oneshot")[0] == "rising"
        assert arc_phase(12, "oneshot")[0] == "climax"
        assert arc_phase(15, "oneshot")[0] == "resolution"

    def test_kampagne_bleibt_laenger_im_aufbau(self) -> None:
        """Dieselbe Zug-Nummer bedeutet je nach gewaehlter Dauer etwas
        voellig anderes."""
        assert arc_phase(20, "oneshot")[0] == "resolution"
        assert arc_phase(20, "campaign")[0] == "setup"

    def test_ueberschrittener_horizont_draengt_zum_abschluss(self) -> None:
        assert arc_phase(1000, "oneshot")[0] == "resolution"

    def test_unbekannte_dauer_faellt_auf_mittel_zurueck(self) -> None:
        assert arc_phase(10, "voellig-unbekannt") == arc_phase(10, "medium")
