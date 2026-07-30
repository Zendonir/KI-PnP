"""Tests fuer den Fortschritts-Zaehler gegen erzaehlerischen Stillstand.

games.stall_streak zaehlt aufeinanderfolgende Zuege ohne Erfolg. Ab einem
Schwellwert muss die KI (bzw. im Test der Offline-Spielleiter) eine
konkrete Wendung liefern statt nur weiterer vager Atmosphaere.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.ai.mock import _PROGRESS_BEATS
from app.domain import dice

from .conftest import auth
from .test_game_flow import started_game  # noqa: F401

__all__ = ["started_game"]


def _always_fails(
    notation: str, *, difficulty: int | None = None, bonus: int = 0, reason: str = ""
) -> dice.DiceResult:
    return dice.DiceResult(
        notation=notation,
        rolls=[1],
        modifier=bonus,
        total=1,
        difficulty=difficulty,
        success=False,
        degree="failure",
        reason=reason,
    )


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
    client: AsyncClient, game_id: str, host: dict[str, Any], guest: dict[str, Any]
) -> None:
    for session in (host, guest):
        response = await client.post(
            f"/api/v1/games/{game_id}/actions",
            json={"kind": "custom", "text": "Wir versuchen es erneut.", "stat": "strength"},
            headers=auth(session["token"]),
        )
        assert response.status_code == 201, response.text


async def _state(client: AsyncClient, game_id: str, token: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/games/{game_id}/state", headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


class TestStallStreak:
    async def test_escalation_beat_appears_after_two_failed_turns(
        self, client: AsyncClient, started_game: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]
        monkeypatch.setattr("app.services.turn_service.dice.roll", _always_fails)

        await _act(client, game_id, host, guest)
        first = await _state(client, game_id, host["token"])
        assert not any(fact["key"].startswith("progress.turn.") for fact in first["facts"])

        await _act(client, game_id, host, guest)
        second = await _state(client, game_id, host["token"])
        assert any(fact["key"].startswith("progress.turn.") for fact in second["facts"])
        latest = second["narrations"][-1]["text"]
        assert any(beat in latest for beat in _PROGRESS_BEATS)

    async def test_success_resets_the_streak(
        self, client: AsyncClient, started_game: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        game_id = started_game["game_id"]
        host, guest = started_game["host"], started_game["guest"]
        monkeypatch.setattr("app.services.turn_service.dice.roll", _always_fails)

        await _act(client, game_id, host, guest)
        await _act(client, game_id, host, guest)
        escalated = await _state(client, game_id, host["token"])
        assert any(fact["key"].startswith("progress.turn.") for fact in escalated["facts"])

        monkeypatch.setattr("app.services.turn_service.dice.roll", _always_succeeds)
        await _act(client, game_id, host, guest)

        # Zurueck auf 0: ein einzelner erneuter Fehlschlag direkt danach
        # darf noch nicht wieder eskalieren (Schwellwert ist 2).
        monkeypatch.setattr("app.services.turn_service.dice.roll", _always_fails)
        await _act(client, game_id, host, guest)
        after_reset = await _state(client, game_id, host["token"])
        progress_facts = [f for f in after_reset["facts"] if f["key"].startswith("progress.turn.")]
        assert len(progress_facts) == 1, "Kein zweiter Eskalations-Fakt direkt nach dem Reset"
