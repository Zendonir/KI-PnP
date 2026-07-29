"""Integrationstest des vollstaendigen Spielablaufs.

Deckt ab: Runde erstellen, beitreten, Charaktere anlegen, Welt generieren,
Handlungen einreichen, Zug aufloesen, Ereignisprotokoll und Sichtbarkeit.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from app.core.container import Container
from app.db.models import Event, Fact, Game

from .conftest import auth


async def _create_game(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    payload = {
        "name": "Die trockene Stadt",
        "host_name": "Sandra",
        "settings": {
            "genre": "fantasy",
            "world": "Aschenfurt",
            "difficulty": "normal",
            "max_players": 4,
            **overrides,
        },
    }
    response = await client.post("/api/v1/games", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _join(client: AsyncClient, code: str, name: str) -> dict[str, Any]:
    response = await client.post(f"/api/v1/games/code/{code}/join", json={"player_name": name})
    assert response.status_code == 200, response.text
    return response.json()


async def _create_character(
    client: AsyncClient, game_id: str, token: str, name: str, char_class: str
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/games/{game_id}/characters",
        json={"name": name, "class": char_class, "race": "Mensch"},
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestLobby:
    async def test_create_returns_join_link_and_token(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        assert session["game"]["status"] == "lobby"
        assert len(session["game"]["code"]) == 6
        assert session["join_url"].endswith(session["game"]["code"])
        assert session["player"]["role"] == "host"
        assert session["token"]

    async def test_qr_code_is_svg(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        response = await client.get(f"/api/v1/games/code/{session['game']['code']}/qr.svg")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert b"<svg" in response.content

    async def test_join_by_code(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        joined = await _join(client, session["game"]["code"], "Tom")
        assert joined["player"]["role"] == "player"
        assert joined["game"]["id"] == session["game"]["id"]

    async def test_join_with_unknown_code_fails(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/games/code/ZZZZZZ/join", json={"player_name": "Niemand"}
        )
        assert response.status_code == 404

    async def test_rejoin_keeps_same_player(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        first = await _join(client, session["game"]["code"], "Tom")
        second = await _join(client, session["game"]["code"], "tom")
        assert first["player"]["id"] == second["player"]["id"]

    async def test_full_game_is_rejected(self, client: AsyncClient) -> None:
        session = await _create_game(client, max_players=2)
        await _join(client, session["game"]["code"], "Tom")
        response = await client.post(
            f"/api/v1/games/code/{session['game']['code']}/join",
            json={"player_name": "Uwe"},
        )
        assert response.status_code == 409

    async def test_token_of_other_game_is_rejected(self, client: AsyncClient) -> None:
        first = await _create_game(client)
        second = await _create_game(client)
        response = await client.get(
            f"/api/v1/games/{second['game']['id']}/state", headers=auth(first["token"])
        )
        assert response.status_code == 403

    async def test_missing_token_is_rejected(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        response = await client.get(f"/api/v1/games/{session['game']['id']}/state")
        assert response.status_code == 401


class TestCharacters:
    async def test_create_character_gets_stats_and_inventory(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        character = await _create_character(
            client, session["game"]["id"], session["token"], "Kell", "Krieger"
        )
        stats = {entry["key"]: entry for entry in character["stats"]}
        assert stats["hp"]["value"] > 0
        assert stats["hp"]["max_value"] == stats["hp"]["value"]
        assert character["inventory"]
        assert character["class"] == "Krieger"

    async def test_randomized_character_is_generated(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        response = await client.post(
            f"/api/v1/games/{session['game']['id']}/characters",
            json={"randomize": True},
            headers=auth(session["token"]),
        )
        assert response.status_code == 201, response.text
        assert response.json()["name"]

    async def test_second_character_is_rejected(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        await _create_character(client, session["game"]["id"], session["token"], "Kell", "Krieger")
        response = await client.post(
            f"/api/v1/games/{session['game']['id']}/characters",
            json={"name": "Zweiter", "class": "Magier"},
            headers=auth(session["token"]),
        )
        assert response.status_code == 409

    async def test_duplicate_name_is_rejected(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        joined = await _join(client, session["game"]["code"], "Tom")
        await _create_character(client, session["game"]["id"], session["token"], "Kell", "Krieger")
        response = await client.post(
            f"/api/v1/games/{session['game']['id']}/characters",
            json={"name": "kell", "class": "Magier"},
            headers=auth(joined["token"]),
        )
        assert response.status_code == 409


@pytest.fixture
async def started_game(client: AsyncClient) -> dict[str, Any]:
    """Eine gestartete Runde mit zwei Spielern und Charakteren."""
    session = await _create_game(client)
    game_id = session["game"]["id"]
    guest = await _join(client, session["game"]["code"], "Tom")
    await _create_character(client, game_id, session["token"], "Kell", "Krieger")
    await _create_character(client, game_id, guest["token"], "Maren", "Magier")

    response = await client.post(f"/api/v1/games/{game_id}/start", headers=auth(session["token"]))
    assert response.status_code == 200, response.text
    return {"game_id": game_id, "host": session, "guest": guest, "state": response.json()}


class TestGameStart:
    async def test_start_requires_host(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        guest = await _join(client, session["game"]["code"], "Tom")
        await _create_character(client, session["game"]["id"], session["token"], "Kell", "Krieger")
        await _create_character(client, session["game"]["id"], guest["token"], "Maren", "Magier")
        response = await client.post(
            f"/api/v1/games/{session['game']['id']}/start", headers=auth(guest["token"])
        )
        assert response.status_code == 403

    async def test_start_requires_character(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        response = await client.post(
            f"/api/v1/games/{session['game']['id']}/start", headers=auth(session["token"])
        )
        assert response.status_code == 409

    async def test_world_is_generated(self, started_game: dict[str, Any]) -> None:
        state = started_game["state"]
        assert state["game"]["status"] == "active"
        assert state["turn"]["number"] == 1
        assert state["narrations"], "Es muss eine Eroeffnungsnarration geben"
        assert state["locations"], "Die Welt braucht mindestens einen entdeckten Ort"
        assert state["quests"], "Es muss eine Startquest geben"
        assert state["turn"]["my_suggestions"], "Jeder Charakter braucht Handlungsvorschlaege"

    async def test_characters_are_placed(self, started_game: dict[str, Any]) -> None:
        for character in started_game["state"]["characters"]:
            assert character["location"], f"{character['name']} hat keinen Ort"

    async def test_second_start_is_rejected(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"/api/v1/games/{started_game['game_id']}/start",
            headers=auth(started_game["host"]["token"]),
        )
        assert response.status_code == 409


class TestTurnLoop:
    async def test_turn_resolves_when_all_submitted(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]

        first = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "investigate", "text": "Ich untersuche den Brunnen."},
            headers=auth(host["token"]),
        )
        assert first.status_code == 201, first.text

        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        assert state["turn"]["number"] == 1, "Der Zug darf noch nicht aufgeloest sein"

        second = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "talk", "text": "Ich spreche die Brunnenmeisterin an."},
            headers=auth(guest["token"]),
        )
        assert second.status_code == 201, second.text

        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        assert state["turn"]["number"] == 2, "Nach allen Einreichungen startet Zug 2"
        assert state["dice_rolls"], "Es muss gewuerfelt worden sein"
        assert len(state["narrations"]) >= 2

    async def test_dice_rolls_are_recorded_with_difficulty(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host = started_game["host"]
        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "attack", "text": "Ich schlage zu."},
            headers=auth(host["token"]),
        )
        await client.post(f"/api/v1/games/{game_id}/resolve", headers=auth(host["token"]))
        state = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()
        roll = state["dice_rolls"][-1]
        assert roll["notation"] == "1d20"
        assert roll["difficulty"] is not None
        assert roll["degree"]
        assert roll["total"] == sum(roll["rolls"]) + roll["modifier"]

    async def test_impossible_action_is_rejected_by_rules(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host = started_game["host"]
        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={
                "kind": "use_item",
                "text": "Ich trinke den Trank des Sieges.",
                "payload": {"item": "Trank des Sieges"},
            },
            headers=auth(host["token"]),
        )
        await client.post(f"/api/v1/games/{game_id}/resolve", headers=auth(host["token"]))
        events = (
            await client.get(
                f"/api/v1/games/{game_id}/events", headers=auth(host["token"])
            )
        ).json()
        rejections = [event for event in events if event["type"] == "action.rejected"]
        assert rejections, "Eine unmoegliche Handlung muss abgelehnt werden"
        assert "Inventar" in rejections[-1]["summary"]

    async def test_stamina_is_deducted(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host = started_game["host"]
        before = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()["my_character"]
        stamina_before = next(s["value"] for s in before["stats"] if s["key"] == "stamina")

        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "attack", "text": "Angriff!"},
            headers=auth(host["token"]),
        )
        await client.post(f"/api/v1/games/{game_id}/resolve", headers=auth(host["token"]))

        after = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(host["token"]))
        ).json()["my_character"]
        stamina_after = next(s["value"] for s in after["stats"] if s["key"] == "stamina")
        assert stamina_after == stamina_before - 1

    async def test_action_of_other_game_state_is_isolated(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        other = await _create_game(client)
        response = await client.post(
            f"/api/v1/games/{started_game['game_id']}/actions",
            json={"kind": "talk", "text": "Hallo?"},
            headers=auth(other["token"]),
        )
        assert response.status_code == 403


class TestEventLog:
    async def test_events_are_append_only_and_sequential(
        self, client: AsyncClient, started_game: dict[str, Any], container: Container
    ) -> None:
        game_id = started_game["game_id"]
        host = started_game["host"]
        await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "investigate", "text": "Ich sehe mich um."},
            headers=auth(host["token"]),
        )
        await client.post(f"/api/v1/games/{game_id}/resolve", headers=auth(host["token"]))

        async with container.database.session() as session:
            events = list(
                (
                    await session.execute(
                        sa.select(Event)
                        .where(Event.game_id == uuid.UUID(game_id))
                        .order_by(Event.seq)
                    )
                )
                .scalars()
                .all()
            )
        assert [event.seq for event in events] == list(range(1, len(events) + 1))
        assert {"game.created", "game.started", "dice.rolled", "turn.completed"} <= {
            event.type for event in events
        }

    async def test_events_endpoint_supports_since(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        host = started_game["host"]
        first = (
            await client.get(f"/api/v1/games/{game_id}/events", headers=auth(host["token"]))
        ).json()
        last_seq = first[-1]["seq"]
        rest = (
            await client.get(
                f"/api/v1/games/{game_id}/events?since={last_seq}", headers=auth(host["token"])
            )
        ).json()
        assert all(event["seq"] > last_seq for event in rest)


class TestVisibility:
    async def test_secret_facts_are_hidden_from_players(
        self, client: AsyncClient, started_game: dict[str, Any], container: Container
    ) -> None:
        game_id = started_game["game_id"]
        async with container.database.session() as session:
            secrets = list(
                (
                    await session.execute(
                        sa.select(Fact).where(
                            Fact.game_id == uuid.UUID(game_id), Fact.visibility == "secret"
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert secrets, "Der Mock-Spielleiter legt ein Geheimnis an"

        state = (
            await client.get(
                f"/api/v1/games/{game_id}/state",
                headers=auth(started_game["host"]["token"]),
            )
        ).json()
        visible_keys = {fact["key"] for fact in state["facts"]}
        assert not visible_keys & {fact.key for fact in secrets}

    async def test_public_knowledge_is_shared(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        state = (
            await client.get(
                f"/api/v1/games/{started_game['game_id']}/state",
                headers=auth(started_game["guest"]["token"]),
            )
        ).json()
        assert state["knowledge"], "Oeffentliches Wissen muss allen zugaenglich sein"


class TestAdmin:
    async def test_pause_and_resume(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        token = started_game["host"]["token"]
        paused = await client.post(f"/api/v1/games/{game_id}/pause", headers=auth(token))
        assert paused.json()["status"] == "paused"

        blocked = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "talk", "text": "Geht das noch?"},
            headers=auth(token),
        )
        assert blocked.status_code == 409

        resumed = await client.post(f"/api/v1/games/{game_id}/resume", headers=auth(token))
        assert resumed.json()["status"] == "active"

    async def test_kick_player_blocks_access(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        guest_id = started_game["guest"]["player"]["id"]
        response = await client.delete(
            f"/api/v1/games/{game_id}/players/{guest_id}",
            headers=auth(started_game["host"]["token"]),
        )
        assert response.status_code == 200

        after = await client.get(
            f"/api/v1/games/{game_id}/state",
            headers=auth(started_game["guest"]["token"]),
        )
        assert after.status_code == 403

    async def test_players_cannot_moderate(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"/api/v1/games/{started_game['game_id']}/pause",
            headers=auth(started_game["guest"]["token"]),
        )
        assert response.status_code == 403

    async def test_summary_can_be_requested(
        self, client: AsyncClient, started_game: dict[str, Any]
    ) -> None:
        game_id = started_game["game_id"]
        token = started_game["host"]["token"]
        response = await client.post(f"/api/v1/games/{game_id}/summary", headers=auth(token))
        assert response.status_code == 200
        assert response.json()["text"]

        listed = await client.get(f"/api/v1/games/{game_id}/summaries", headers=auth(token))
        assert len(listed.json()) == 1

    async def test_finished_game_keeps_history(
        self, client: AsyncClient, started_game: dict[str, Any], container: Container
    ) -> None:
        game_id = started_game["game_id"]
        token = started_game["host"]["token"]
        await client.post(f"/api/v1/games/{game_id}/finish", headers=auth(token))
        async with container.database.session() as session:
            game = await session.get(Game, uuid.UUID(game_id))
            count = (
                await session.execute(
                    sa.select(sa.func.count())
                    .select_from(Event)
                    .where(Event.game_id == uuid.UUID(game_id))
                )
            ).scalar_one()
        assert game is not None and game.status == "finished"
        assert count > 0
