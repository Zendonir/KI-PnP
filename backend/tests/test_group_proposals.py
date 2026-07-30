"""Tests fuer Gruppenereignisse.

Jemand markiert eine Handlung als Gruppenereignis; andere aktive Spieler
am selben Ort werden gefragt, ob sie mitmachen. Wer zustimmt, teilt sich
dieselbe Handlung (kind/text/stat), wuerfelt aber mit eigenem Charakterwert
und bekommt einen Bonus. Der Zug loest erst auf, wenn jede erwartete
Person entweder ihre eigene Handlung eingereicht oder auf den Vorschlag
reagiert hat.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient

from app.core.container import Container

from .conftest import auth
from .test_game_flow import _character_id, _create_character, _join, _move_character, started_game

__all__ = ["started_game"]


class TestGruppenereignisAnbieten:
    async def test_other_player_receives_the_proposal(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        response = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={
                "kind": "custom",
                "text": "Wir gehen zur Hoehle.",
                "stat": "strength",
                "group_event": True,
            },
            headers=auth(host["token"]),
        )
        assert response.status_code == 201, response.text

        guest_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(guest["token"]))
        ).json()
        proposal = guest_state["pending_group_proposal"]
        assert proposal is not None
        assert proposal["text"] == "Wir gehen zur Hoehle."
        assert proposal["kind"] == "custom"
        assert proposal["initiator_name"] == "Kell"

        # Der Initiator bekommt sein eigenes Angebot nicht zu sehen.
        host_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        assert host_state["pending_group_proposal"] is None

    async def test_second_proposal_in_same_turn_is_ignored(
        self, client: AsyncClient, started_game: dict[str, Any], container: Container
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        # Ein dritter Spieler am selben Ort haelt den Zug offen, damit nach
        # der zweiten (eigenen) Handlung des Gastes noch nicht automatisch
        # aufgeloest wird. Frisch angelegte Charaktere starten ohne Ort
        # (location_id None), deshalb explizit an den Startort versetzen.
        ben = await _join(client, started_game["host"]["game"]["code"], "Ben")
        await _create_character(client, game_id, ben["token"], "Rill", "Schurke")
        ben_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(ben["token"]))
        ).json()
        ben_character = _character_id(ben_state, ben["player"]["id"])
        start_location = uuid.UUID(started_game["state"]["turn"]["location_id"])
        await _move_character(container, ben_character, start_location)

        first = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Erster Vorschlag.", "group_event": True},
            headers=auth(host["token"]),
        )
        assert first.status_code == 201, first.text

        second = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Zweiter Vorschlag.", "group_event": True},
            headers=auth(guest["token"]),
        )
        assert second.status_code == 201, second.text

        # Ben (noch nicht eingereicht) sieht weiterhin nur den ersten
        # Vorschlag -- der zweite Versuch wurde stillschweigend ignoriert.
        ben_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(ben["token"]))
        ).json()
        assert ben_state["pending_group_proposal"]["text"] == "Erster Vorschlag."

    async def test_declining_still_requires_own_action(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={
                "kind": "custom",
                "text": "Wir gehen zur Hoehle.",
                "stat": "strength",
                "group_event": True,
            },
            headers=auth(host["token"]),
        )
        guest_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(guest["token"]))
        ).json()
        proposal_id = guest_state["pending_group_proposal"]["id"]
        collecting_turn_id = guest_state["turn"]["id"]

        respond = await client.post(
            f"/api/v1/games/{game_id}/group-proposals/{proposal_id}/respond",
            json={"accepted": False},
            headers=auth(guest["token"]),
        )
        assert respond.status_code == 200, respond.text
        assert respond.json()["pending_group_proposal"] is None
        # Der Zug ist noch nicht aufgeloest -- der Gast schuldet noch die
        # eigene Handlung.
        assert respond.json()["turn"]["id"] == collecting_turn_id
        assert respond.json()["turn"]["status"] == "collecting"

        follow_up = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Ich bleibe lieber hier.", "stat": "intelligence"},
            headers=auth(guest["token"]),
        )
        assert follow_up.status_code == 201, follow_up.text


class TestGruppenereignisAnnehmen:
    async def test_accepting_creates_action_with_bonus_and_resolves_turn(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={
                "kind": "custom",
                "text": "Wir gehen zur Hoehle.",
                "stat": "strength",
                "group_event": True,
            },
            headers=auth(host["token"]),
        )
        guest_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(guest["token"]))
        ).json()
        proposal_id = guest_state["pending_group_proposal"]["id"]
        collecting_turn_id = guest_state["turn"]["id"]

        respond = await client.post(
            f"/api/v1/games/{game_id}/group-proposals/{proposal_id}/respond",
            json={"accepted": True},
            headers=auth(guest["token"]),
        )
        assert respond.status_code == 200, respond.text
        # Beide erwarteten Spieler haben jetzt eine Handlung -- der Zug hat
        # sich weiterbewegt.
        assert respond.json()["turn"]["id"] != collecting_turn_id

        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        rolls_by_char = {roll["character_id"]: roll for roll in state["dice_rolls"]}
        guest_character_id = next(
            c["id"] for c in state["characters"] if c["player_id"] == guest["player"]["id"]
        )
        host_character_id = next(
            c["id"] for c in state["characters"] if c["player_id"] == host["player"]["id"]
        )
        # Maren (Magierin): Staerke bleibt bei 10 -> ability_modifier 0,
        # plus Gruppenbonus 2 -> modifier 2.
        assert rolls_by_char[guest_character_id]["modifier"] == 2
        # Kell (Krieger, Initiator, kein Bonus): Staerke 14 -> modifier 2.
        assert rolls_by_char[host_character_id]["modifier"] == 2

    async def test_initiator_cannot_respond_to_own_proposal(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Wir gehen zur Hoehle.", "group_event": True},
            headers=auth(host["token"]),
        )
        guest_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(guest["token"]))
        ).json()
        proposal_id = guest_state["pending_group_proposal"]["id"]

        response = await client.post(
            f"/api/v1/games/{game_id}/group-proposals/{proposal_id}/respond",
            json={"accepted": True},
            headers=auth(host["token"]),
        )
        assert response.status_code == 409

    async def test_double_response_is_rejected(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Wir gehen zur Hoehle.", "group_event": True},
            headers=auth(host["token"]),
        )
        guest_state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(guest["token"]))
        ).json()
        proposal_id = guest_state["pending_group_proposal"]["id"]

        first = await client.post(
            f"/api/v1/games/{game_id}/group-proposals/{proposal_id}/respond",
            json={"accepted": False},
            headers=auth(guest["token"]),
        )
        assert first.status_code == 200, first.text

        second = await client.post(
            f"/api/v1/games/{game_id}/group-proposals/{proposal_id}/respond",
            json={"accepted": True},
            headers=auth(guest["token"]),
        )
        assert second.status_code == 409
