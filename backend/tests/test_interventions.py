"""Tests der kurzfristigen Eingriffsangebote (Quick-Time-Event)."""

from __future__ import annotations

import uuid

from app.services import interventions


class TestInterventions:
    async def test_accepted_response_before_timeout(self) -> None:
        player_id = uuid.uuid4()
        intervention_id = interventions.create_waiter(player_id)

        assert interventions.respond(intervention_id, player_id, accepted=True) is True
        accepted = await interventions.wait_for_response(intervention_id, timeout=1.0)
        assert accepted is True

    async def test_declined_response_before_timeout(self) -> None:
        player_id = uuid.uuid4()
        intervention_id = interventions.create_waiter(player_id)

        assert interventions.respond(intervention_id, player_id, accepted=False) is True
        accepted = await interventions.wait_for_response(intervention_id, timeout=1.0)
        assert accepted is False

    async def test_timeout_without_response_counts_as_declined(self) -> None:
        player_id = uuid.uuid4()
        intervention_id = interventions.create_waiter(player_id)

        accepted = await interventions.wait_for_response(intervention_id, timeout=0.05)
        assert accepted is False

    async def test_wrong_player_cannot_respond(self) -> None:
        player_id = uuid.uuid4()
        stranger_id = uuid.uuid4()
        intervention_id = interventions.create_waiter(player_id)

        assert interventions.respond(intervention_id, stranger_id, accepted=True) is False
        accepted = await interventions.wait_for_response(intervention_id, timeout=0.05)
        assert accepted is False

    async def test_unknown_intervention_is_ignored(self) -> None:
        assert interventions.respond(uuid.uuid4(), uuid.uuid4(), accepted=True) is False
        accepted = await interventions.wait_for_response(uuid.uuid4(), timeout=0.05)
        assert accepted is False

    async def test_waiter_is_removed_after_resolution(self) -> None:
        player_id = uuid.uuid4()
        intervention_id = interventions.create_waiter(player_id)
        assert intervention_id in interventions._WAITERS  # noqa: SLF001 - Testeinsicht

        await interventions.wait_for_response(intervention_id, timeout=0.05)
        assert intervention_id not in interventions._WAITERS  # noqa: SLF001 - Testeinsicht
