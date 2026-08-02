"""Tests fuer die frei benannten Zusatzfaehigkeiten (Skill-Punkte-Verteilung).

Spieler verteilen nach dem Erstellen bis zu 100 Punkte auf frei benannte
Skills (z. B. "Schloesser knacken"). Diese sind danach als Wuerfel-Attribut
waehlbar, genau wie die vier Grundattribute -- siehe test_action_resolution.py
fuer die Passungspruefung dazu.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from .conftest import auth
from .test_game_flow import _create_character, _create_game


class TestSkillVerteilung:
    async def test_valid_skills_appear_in_state(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        game_id = session["game"]["id"]
        await _create_character(client, game_id, session["token"], "Kell", "Krieger")

        response = await client.put(
            f"/api/v1/games/{game_id}/characters/me/skills",
            json={
                "skills": [
                    {"name": "Schloesser knacken", "points": 40},
                    {"name": "Klettern", "points": 20},
                ]
            },
            headers=auth(session["token"]),
        )
        assert response.status_code == 200, response.text
        stats = {entry["key"]: entry["value"] for entry in response.json()["stats"]}
        assert stats["Schloesser knacken"] == 40
        assert stats["Klettern"] == 20
        # Grundattribute und Ressourcen-Pools bleiben unangetastet.
        assert stats["strength"] == 14  # Krieger-Bonus

    async def test_replacing_skills_drops_the_old_list(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        game_id = session["game"]["id"]
        await _create_character(client, game_id, session["token"], "Kell", "Krieger")

        await client.put(
            f"/api/v1/games/{game_id}/characters/me/skills",
            json={"skills": [{"name": "Schloesser knacken", "points": 40}]},
            headers=auth(session["token"]),
        )
        response = await client.put(
            f"/api/v1/games/{game_id}/characters/me/skills",
            json={"skills": [{"name": "Klettern", "points": 30}]},
            headers=auth(session["token"]),
        )
        assert response.status_code == 200, response.text
        keys = {entry["key"] for entry in response.json()["stats"]}
        assert "Klettern" in keys
        assert "Schloesser knacken" not in keys

    async def test_total_above_100_is_rejected(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        game_id = session["game"]["id"]
        await _create_character(client, game_id, session["token"], "Kell", "Krieger")

        response = await client.put(
            f"/api/v1/games/{game_id}/characters/me/skills",
            json={
                "skills": [
                    {"name": "Klettern", "points": 60},
                    {"name": "Schwimmen", "points": 50},
                ]
            },
            headers=auth(session["token"]),
        )
        assert response.status_code == 422, response.text

    async def test_reserved_name_is_rejected(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        game_id = session["game"]["id"]
        await _create_character(client, game_id, session["token"], "Kell", "Krieger")

        response = await client.put(
            f"/api/v1/games/{game_id}/characters/me/skills",
            json={"skills": [{"name": "strength", "points": 20}]},
            headers=auth(session["token"]),
        )
        assert response.status_code == 422, response.text

    async def test_duplicate_name_is_rejected(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        game_id = session["game"]["id"]
        await _create_character(client, game_id, session["token"], "Kell", "Krieger")

        response = await client.put(
            f"/api/v1/games/{game_id}/characters/me/skills",
            json={
                "skills": [
                    {"name": "Klettern", "points": 10},
                    {"name": "klettern", "points": 10},
                ]
            },
            headers=auth(session["token"]),
        )
        assert response.status_code == 422, response.text

    async def test_without_character_returns_not_found(self, client: AsyncClient) -> None:
        session = await _create_game(client)
        game_id = session["game"]["id"]

        response = await client.put(
            f"/api/v1/games/{game_id}/characters/me/skills",
            json={"skills": [{"name": "Klettern", "points": 10}]},
            headers=auth(session["token"]),
        )
        assert response.status_code == 404, response.text

    async def test_custom_skill_is_honored_as_stat_hint(self, client: AsyncClient) -> None:
        """End-zu-Ende: ein selbst benannter Skill wird beim Wuerfeln
        tatsaechlich als Attribut verwendet (skill_modifier statt
        ability_modifier)."""
        session = await _create_game(client)
        game_id = session["game"]["id"]
        await _create_character(client, game_id, session["token"], "Kell", "Krieger")
        await client.put(
            f"/api/v1/games/{game_id}/characters/me/skills",
            json={"skills": [{"name": "Schloesser knacken", "points": 40}]},
            headers=auth(session["token"]),
        )
        await client.post(f"/api/v1/games/{game_id}/start", headers=auth(session["token"]))

        response = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={
                "kind": "custom",
                "text": "Ich knacke das Schloss.",
                "stat": "Schloesser knacken",
            },
            headers=auth(session["token"]),
        )
        assert response.status_code == 201, response.text
        state: dict[str, Any] = (
            await client.get(f"/api/v1/games/{game_id}/state", headers=auth(session["token"]))
        ).json()
        # skill_modifier(40) = min(8, 40 // 10) = 4.
        assert state["dice_rolls"][0]["modifier"] == 4
