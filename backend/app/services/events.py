"""Event Sourcing: das unveraenderliche Protokoll einer Spielrunde.

Jede Zustandsaenderung erzeugt genau ein Ereignis. Ereignisse werden nur
angehaengt; sie werden weder veraendert noch geloescht.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, Game
from app.realtime.hub import EventHub

# Ereignistypen (Auszug, erweiterbar)
ACTION_SUBMITTED = "action.submitted"
ACTION_REJECTED = "action.rejected"
ACTION_RESOLVED = "action.resolved"
DICE_ROLLED = "dice.rolled"
STATE_CHANGED = "state.changed"
CHANGE_REJECTED = "change.rejected"
NARRATION_CREATED = "narration.created"
TURN_STARTED = "turn.started"
TURN_COMPLETED = "turn.completed"
GAME_CREATED = "game.created"
GAME_STARTED = "game.started"
GAME_STATUS_CHANGED = "game.status_changed"
PLAYER_JOINED = "player.joined"
PLAYER_LEFT = "player.left"
CHARACTER_CREATED = "character.created"
SUMMARY_CREATED = "summary.created"
AUDIO_READY = "audio.ready"


async def increment_game_counter(
    session: AsyncSession, game: Game, column: sa.orm.attributes.InstrumentedAttribute[int]
) -> int:
    """Erhoeht eine Zaehlspalte auf der Spielzeile atomar und gibt sie zurueck.

    Ein SQL-UPDATE mit RETURNING statt eines Python-seitigen ``+= 1``: sicher
    auch unter echter Nebenlaeufigkeit, weil zwischen Lesen und Schreiben
    keine Luecke entsteht, in die eine zweite, gleichzeitige Transaktion
    greifen koennte -- auf jeder Datenbank, nicht nur mit Zeilensperren
    (die SQLite ohnehin nicht kennt). Noetig, seit mehrere Zuege desselben
    Spiels gleichzeitig aufloesen koennen: event_seq und current_turn_number
    duerfen dabei nie kollidieren.
    """
    result = await session.execute(
        sa.update(Game)
        .where(Game.id == game.id)
        .values(**{column.key: column + 1})
        .returning(column)
    )
    value = result.scalar_one()
    setattr(game, column.key, value)
    return value


@dataclass(slots=True)
class RecordedEvent:
    """Ein geschriebenes Ereignis inklusive Sequenznummer."""

    id: UUID
    seq: int
    type: str
    summary: str
    payload: dict[str, Any]
    visibility: str
    audience_player_id: UUID | None
    turn_number: int

    def as_message(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "seq": self.seq,
            "type": self.type,
            "summary": self.summary,
            "payload": self.payload,
            "visibility": self.visibility,
            "turn_number": self.turn_number,
        }


class EventRecorder:
    """Schreibt Ereignisse und verteilt sie in Echtzeit."""

    def __init__(self, session: AsyncSession, hub: EventHub | None = None) -> None:
        self._session = session
        self._hub = hub
        self._pending: list[RecordedEvent] = []

    async def record(
        self,
        game: Game,
        *,
        type: str,
        summary: str = "",
        payload: dict[str, Any] | None = None,
        turn_id: UUID | None = None,
        turn_number: int | None = None,
        actor_type: str = "system",
        actor_id: UUID | None = None,
        visibility: str = "public",
        audience_player_id: UUID | None = None,
        counts_towards_summary: bool = True,
    ) -> RecordedEvent:
        """Haengt ein Ereignis an das Protokoll an."""
        seq = await increment_game_counter(self._session, game, Game.event_seq)
        if counts_towards_summary:
            game.events_since_summary += 1

        event = Event(
            game_id=game.id,
            seq=seq,
            turn_id=turn_id,
            turn_number=turn_number if turn_number is not None else game.current_turn_number,
            type=type,
            actor_type=actor_type,
            actor_id=actor_id,
            visibility=visibility,
            audience_player_id=audience_player_id,
            summary=summary,
            payload=payload or {},
        )
        self._session.add(event)
        await self._session.flush()

        recorded = RecordedEvent(
            id=event.id,
            seq=seq,
            type=type,
            summary=summary,
            payload=event.payload,
            visibility=visibility,
            audience_player_id=audience_player_id,
            turn_number=event.turn_number,
        )
        self._pending.append(recorded)
        return recorded

    async def flush_to_clients(self, game_id: UUID) -> None:
        """Verteilt alle seit dem letzten Aufruf geschriebenen Ereignisse."""
        if self._hub is None:
            self._pending.clear()
            return
        for event in self._pending:
            await self._hub.publish(
                game_id,
                "event",
                event.as_message(),
                audience_player_id=event.audience_player_id,
            )
        self._pending.clear()


async def load_recent_events(
    session: AsyncSession, game_id: UUID, *, limit: int = 25, since_seq: int | None = None
) -> list[Event]:
    """Laedt die juengsten Ereignisse (aufsteigend sortiert)."""
    stmt = sa.select(Event).where(Event.game_id == game_id)
    if since_seq is not None:
        stmt = stmt.where(Event.seq > since_seq).order_by(Event.seq.asc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())
    stmt = stmt.order_by(Event.seq.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(reversed(result.scalars().all()))
