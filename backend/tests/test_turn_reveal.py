"""Tests fuer das gruppenweite Aufdecken von Wuerfelergebnissen.

Wuerfelergebnisse, Erzaehlung und Ton eines Zugs entstehen sofort im
Hintergrund, werden aber erst sichtbar, wenn alle erwarteten Spieler
bestaetigt haben (oder die Spielleitung vorzeitig aufdeckt). Ausserdem:
dice_rolls in /state duerfen keine Wuerfe eines unabhaengig laufenden,
anderen Ortes mehr zeigen.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient

from app.core.container import Container

from .conftest import auth
from .test_game_flow import (
    _character_id,
    _create_location,
    _move_character,
    started_game,
)

__all__ = ["started_game"]


class TestDiceRollOrtsfilter:
    async def test_own_location_rolls_do_not_leak_to_other_location(
        self, client: AsyncClient, started_game: dict[str, Any], container: Container
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]
        guest_character = _character_id(started_game["state"], guest["player"]["id"])

        cave = await _create_location(container, uuid.UUID(game_id), "Hoehle")
        await _move_character(container, guest_character, cave)

        # Der Gastgeber loest seinen (unabhaengigen) Zug alleine auf --
        # produziert einen Wuerfelwurf am Startort.
        response = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Ich untersuche den Brunnen.", "stat": "intelligence"},
            headers=auth(host["token"]),
        )
        assert response.status_code == 201, response.text

        # Der Gast an der Hoehle hat davon noch nichts eingereicht -- sein
        # eigener Zug ist unberuehrt. Trotzdem durfte der Wurf des
        # Gastgebers (anderer Ort) vorher in seinem dice_rolls auftauchen --
        # das war der eigentliche Fehler.
        guest_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(guest["token"]))
        ).json()
        assert guest_state["dice_rolls"] == [], (
            "Wuerfe eines unabhaengig laufenden, anderen Ortes duerfen nicht sichtbar sein"
        )

        host_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        assert len(host_state["dice_rolls"]) == 1


class TestAufdeckung:
    async def test_reveals_once_all_expected_players_ack(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        for session in (host, guest):
            response = await client.post(
                f"/api/v1/games/{game_id}/actions",
                json={"kind": "custom", "text": "Wir handeln.", "stat": "strength"},
                headers=auth(session["token"]),
            )
            assert response.status_code == 201, response.text

        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        pending = state["pending_reveal"]
        assert pending is not None
        assert pending["revealed"] is False
        assert len(pending["expected_player_ids"]) == 2
        assert pending["acknowledged_player_ids"] == []
        turn_id = pending["turn_id"]

        # Nur der Gastgeber bestaetigt -- noch nicht aufgedeckt.
        after_host_ack = (
            await client.post(
                f"/api/v1/games/{game_id}/turns/{turn_id}/ack", headers=auth(host["token"])
            )
        ).json()
        assert after_host_ack["pending_reveal"]["revealed"] is False
        assert len(after_host_ack["pending_reveal"]["acknowledged_player_ids"]) == 1

        # Bestaetigt auch der Gast, deckt es fuer beide auf.
        after_guest_ack = (
            await client.post(
                f"/api/v1/games/{game_id}/turns/{turn_id}/ack", headers=auth(guest["token"])
            )
        ).json()
        assert after_guest_ack["pending_reveal"]["revealed"] is True

    async def test_host_can_force_reveal(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        for session in (host, guest):
            await client.post(
                f"/api/v1/games/{game_id}/actions",
                json={"kind": "custom", "text": "Wir handeln.", "stat": "strength"},
                headers=auth(session["token"]),
            )

        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        turn_id = state["pending_reveal"]["turn_id"]

        response = await client.post(
            f"/api/v1/games/{game_id}/turns/{turn_id}/reveal", headers=auth(host["token"])
        )
        assert response.status_code == 200, response.text
        assert response.json()["pending_reveal"]["revealed"] is True

    async def test_guest_cannot_force_reveal(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        for session in (host, guest):
            await client.post(
                f"/api/v1/games/{game_id}/actions",
                json={"kind": "custom", "text": "Wir handeln.", "stat": "strength"},
                headers=auth(session["token"]),
            )

        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        turn_id = state["pending_reveal"]["turn_id"]

        response = await client.post(
            f"/api/v1/games/{game_id}/turns/{turn_id}/reveal", headers=auth(guest["token"])
        )
        assert response.status_code == 403

    async def test_ack_on_still_collecting_turn_is_rejected(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host = started_game["host"]
        turn_id = started_game["state"]["turn"]["id"]

        response = await client.post(
            f"/api/v1/games/{game_id}/turns/{turn_id}/ack", headers=auth(host["token"])
        )
        assert response.status_code == 409
