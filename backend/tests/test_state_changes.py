"""Tests fuer die Aenderungsanwendung (StateChangeApplier)."""

from __future__ import annotations

from app.core.container import Container
from app.db.models import Game
from app.realtime.hub import EventHub
from app.services.events import EventRecorder
from app.services.state_changes import StateChangeApplier


class TestForwaertsReferenzen:
    async def test_quest_referencing_not_yet_created_giver_succeeds_on_retry(
        self, container: Container
    ) -> None:
        """Die KI liefert 'changes' nicht zuverlaessig in
        abhaengigkeitsgerechter Reihenfolge -- eine Quest, deren
        Auftraggeber im selben Vorschlag erst danach per entity.create
        entsteht, darf trotzdem nicht endgueltig scheitern."""
        async with container.database.session() as session:
            game = Game(code="TEST01", name="Testrunde", status="lobby")
            session.add(game)
            await session.flush()
            recorder = EventRecorder(session, EventHub(None))
            applier = StateChangeApplier(session, game, recorder, turn_id=None)

            changes = [
                {
                    "op": "quest.create",
                    "title": "Das versiegte Wasser",
                    "description": "Findet heraus, warum der Brunnen trocken liegt.",
                    "giver": "Hedda Vorn",
                    "is_main": True,
                },
                {
                    "op": "entity.create",
                    "name": "Hedda Vorn",
                    "kind": "npc",
                    "description": "Brunnenmeisterin.",
                },
            ]
            application = await applier.apply_raw(changes, source="ai")
            await session.commit()

            assert application.rejected == [], application.rejected
            assert application.accepted_count == 2

    async def test_genuinely_invalid_change_is_still_rejected(
        self, container: Container
    ) -> None:
        """Der Retry-Durchlauf darf keine wirklich ungueltigen Vorschlaege
        durchwinken -- nur an einer Referenz gescheiterte."""
        async with container.database.session() as session:
            game = Game(code="TEST02", name="Testrunde", status="lobby")
            session.add(game)
            await session.flush()
            recorder = EventRecorder(session, EventHub(None))
            applier = StateChangeApplier(session, game, recorder, turn_id=None)

            changes = [
                {
                    "op": "quest.create",
                    "title": "Verwaiste Quest",
                    "description": "Ohne Auftraggeber, der je entsteht.",
                    "giver": "Niemand Existierendes",
                },
            ]
            application = await applier.apply_raw(changes, source="ai")
            await session.commit()

            assert application.accepted_count == 0
            assert application.rejected_count == 1
