"""Aufbau des KI-Kontexts.

Der KI wird nie das vollstaendige Ereignisprotokoll uebergeben, sondern ein
kompaktes Abbild: aktuelle Szene, anwesende NSC, Charakterwerte, offene
Quests, relevante Fakten, die letzten Ereignisse und die verdichteten
Zusammenfassungen. Das haelt Kosten und Kontextlaenge stabil, auch nach
tausenden Spielzuegen.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import (
    Character,
    Fact,
    Game,
    Inventory,
    InventoryItem,
    Knowledge,
    Location,
    Quest,
    SceneSummary,
    Turn,
    WorldEntity,
)
from app.services.events import load_recent_events

EXPECTED_TURNS: dict[str, int] = {
    "oneshot": 15,
    "short": 40,
    "medium": 80,
    "long": 160,
    "campaign": 320,
}
"""Grober Zug-Horizont je gewaehlter Spieldauer. Kein hartes Limit -- die
Runde endet nicht automatisch --, sondern eine Orientierung, aus der sich
die Phase des Spannungsbogens ableitet. Ohne sie hat die KI keinerlei
Zielhorizont und keinen Grund, eine Geschichte je zum Hoehepunkt zu
fuehren."""

ARC_PHASES: tuple[tuple[float, str], ...] = (
    (0.25, "setup"),
    (0.60, "rising"),
    (0.85, "climax"),
    (1.01, "resolution"),
)
"""Anteil der erwarteten Spieldauer -> Phase. Der letzte Eintrag greift
auch, wenn der Horizont ueberschritten ist (Anteil > 1)."""


def arc_phase(turn_number: int, duration: str) -> tuple[str, float]:
    """Phase des Spannungsbogens und Fortschrittsanteil fuer einen Zug."""
    expected = EXPECTED_TURNS.get(duration, EXPECTED_TURNS["medium"])
    ratio = turn_number / expected if expected > 0 else 1.0
    for threshold, phase in ARC_PHASES:
        if ratio < threshold:
            return phase, ratio
    return ARC_PHASES[-1][1], ratio


class ContextBuilder:
    """Stellt die Kontextobjekte fuer die KI zusammen."""

    def __init__(self, session: AsyncSession, game: Game, settings: Settings) -> None:
        self._session = session
        self._game = game
        self._settings = settings

    async def build_world_context(self) -> dict[str, Any]:
        """Kontext fuer die Weltgenerierung zu Spielbeginn."""
        return {
            "settings": self._settings_payload(),
            "characters": await self._characters_payload(include_knowledge=False),
        }

    async def build_turn_context(
        self,
        turn: Turn | None,
        *,
        action_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Kontext fuer die Fortsetzung der Geschichte."""
        location = await self._current_location(turn)
        return {
            "settings": self._settings_payload(),
            # Nummer *dieses* Zugs, nicht der hoechsten je vergebenen im
            # Spiel -- sobald mehrere Orte gleichzeitig Zuege fuehren,
            # koennen die beiden auseinanderlaufen. Ohne Aufteilung sind sie
            # immer identisch.
            "turn_number": turn.number if turn else self._game.current_turn_number,
            "scene_title": turn.scene_title if turn else "",
            "location": self._location_payload(location),
            "characters": await self._characters_payload(
                include_knowledge=True,
                location_id=turn.location_id if turn else None,
            ),
            "npcs": await self._entities_payload(location),
            "quests": await self._quests_payload(),
            "facts": await self._facts_payload(),
            "summaries": await self._summaries_payload(),
            "recent_events": await self._recent_events_payload(),
            "action_results": action_results or [],
            "stall_streak": self._game.stall_streak,
            "arc": self._arc_payload(turn.number if turn else self._game.current_turn_number),
        }

    async def build_summary_context(self, *, from_seq: int) -> dict[str, Any]:
        """Kontext fuer die Verdichtung des Langzeitgedaechtnisses."""
        events = await load_recent_events(
            self._session, self._game.id, limit=200, since_seq=from_seq
        )
        return {
            "settings": self._settings_payload(),
            "previous_summaries": await self._summaries_payload(),
            "events": [
                {
                    "seq": event.seq,
                    "turn": event.turn_number,
                    "type": event.type,
                    "summary": event.summary,
                }
                for event in events
                if event.summary
            ],
        }

    async def build_character_context(self) -> dict[str, Any]:
        """Kontext fuer die Zufallsgenerierung eines Charakters."""
        return {
            "settings": self._settings_payload(),
            "existing_characters": [
                {"name": name, "class": char_class}
                for name, char_class in await self._character_names()
            ],
        }

    # -- Bausteine -------------------------------------------------------

    def _settings_payload(self) -> dict[str, Any]:
        settings = self._game.settings
        if settings is None:  # pragma: no cover - defensiv
            return {"genre": "fantasy"}
        return {
            "genre": settings.genre,
            "world": settings.world,
            "difficulty": settings.difficulty,
            "duration": settings.duration,
            "rule_complexity": settings.rule_complexity,
            "play_style": settings.play_style,
            "tone": settings.tone,
            "campaign_type": settings.campaign_type,
            "ruleset": settings.ruleset,
            "language": settings.language,
        }

    def _arc_payload(self, turn_number: int) -> dict[str, Any]:
        """Wo im Spannungsbogen die Runde gerade steht."""
        duration = self._game.settings.duration if self._game.settings else "medium"
        phase, ratio = arc_phase(turn_number, duration)
        return {
            "phase": phase,
            "turn_number": turn_number,
            "expected_turns": EXPECTED_TURNS.get(duration, EXPECTED_TURNS["medium"]),
            "elapsed_share": round(ratio, 2),
        }

    async def _current_location(self, turn: Turn | None) -> Location | None:
        # Der Ort gehoert eindeutig zum Zug -- jeder Zug bekommt seinen
        # Ort bereits bei seiner Entstehung zugewiesen (_sync_location_turns
        # in TurnService). Ein Fallback auf "irgendein Charakter im Spiel"
        # waere seit ortsbezogenen Zuegen falsch: er koennte den Ort einer
        # ganz anderen, unabhaengig laufenden Szene liefern.
        location_id = turn.location_id if turn else None
        if location_id is None:
            return None
        return await self._session.get(Location, location_id)

    def _location_payload(self, location: Location | None) -> dict[str, Any]:
        if location is None:
            return {}
        return {"name": location.name, "description": location.description}

    async def _character_names(self) -> list[tuple[str, str]]:
        stmt = sa.select(Character.name, Character.char_class).where(
            Character.game_id == self._game.id
        )
        return [(row[0], row[1]) for row in (await self._session.execute(stmt)).all()]

    async def _characters_payload(
        self, *, include_knowledge: bool, location_id: uuid.UUID | None = None
    ) -> list[dict[str, Any]]:
        stmt = sa.select(Character).where(Character.game_id == self._game.id)
        if location_id is not None:
            # Nur die Charaktere an genau diesem Ort: sonst saehe die KI
            # eines Ortes auch die Charaktere einer unabhaengig laufenden
            # Szene anderswo. Beim Weltaufbau (kein location_id) bleibt die
            # ganze Gruppe sichtbar, dort steht noch niemand irgendwo.
            stmt = stmt.where(Character.location_id == location_id)
        characters = list((await self._session.execute(stmt)).scalars().all())
        payload: list[dict[str, Any]] = []
        for character in characters:
            entry: dict[str, Any] = {
                "name": character.name,
                "class": character.char_class,
                "race": character.race,
                "level": character.level,
                "alive": character.is_alive,
                "conditions": list(character.conditions or []),
                "stats": {
                    stat.key: (
                        {"value": stat.value, "max": stat.max_value}
                        if stat.max_value is not None
                        else stat.value
                    )
                    for stat in character.stats
                },
                "abilities": [link.ability.name for link in character.abilities],
                "inventory": await self._inventory_names("character", character.id),
            }
            if include_knowledge:
                entry["knows"] = await self._knowledge_payload(character.id)
            payload.append(entry)
        return payload

    async def _inventory_names(self, owner_type: str, owner_id: uuid.UUID) -> list[str]:
        stmt = (
            sa.select(InventoryItem)
            .join(Inventory, Inventory.id == InventoryItem.inventory_id)
            .where(Inventory.owner_type == owner_type, Inventory.owner_id == owner_id)
        )
        entries = list((await self._session.execute(stmt)).scalars().all())
        return [
            f"{entry.item.name} x{entry.quantity}" if entry.quantity > 1 else entry.item.name
            for entry in entries
        ]

    async def _knowledge_payload(self, character_id: uuid.UUID) -> list[str]:
        stmt = (
            sa.select(Knowledge)
            .where(
                Knowledge.game_id == self._game.id,
                sa.or_(
                    Knowledge.subject_type == "public",
                    sa.and_(
                        Knowledge.subject_type == "character",
                        Knowledge.subject_id == character_id,
                    ),
                ),
            )
            .order_by(Knowledge.created_at_seq.desc())
            .limit(25)
        )
        entries = list((await self._session.execute(stmt)).scalars().all())
        return [
            entry.content if entry.certainty == "truth" else f"[{entry.certainty}] {entry.content}"
            for entry in reversed(entries)
        ]

    async def _entities_payload(self, location: Location | None) -> list[dict[str, Any]]:
        stmt = sa.select(WorldEntity).where(WorldEntity.game_id == self._game.id)
        if location is not None:
            stmt = stmt.where(
                sa.or_(
                    WorldEntity.location_id == location.id,
                    WorldEntity.location_id.is_(None),
                )
            )
        entities = list((await self._session.execute(stmt)).scalars().all())
        payload = []
        for entity in entities[:20]:
            knowledge_stmt = (
                sa.select(Knowledge.content)
                .where(
                    Knowledge.game_id == self._game.id,
                    Knowledge.subject_type == "entity",
                    Knowledge.subject_id == entity.id,
                )
                .order_by(Knowledge.created_at_seq.desc())
                .limit(5)
            )
            knows = [row for row in (await self._session.execute(knowledge_stmt)).scalars().all()]
            payload.append(
                {
                    "name": entity.name,
                    "kind": entity.kind,
                    "description": entity.description,
                    "alive": entity.is_alive,
                    "data": entity.data,
                    "knows": knows,
                }
            )
        return payload

    async def _quests_payload(self) -> list[dict[str, Any]]:
        stmt = sa.select(Quest).where(Quest.game_id == self._game.id)
        quests = list((await self._session.execute(stmt)).scalars().all())
        payload = []
        for quest in quests:
            state = quest.current_state
            if state is not None and state.status in ("completed", "failed"):
                continue
            entry: dict[str, Any] = {
                "title": quest.title,
                "description": quest.description,
                "status": state.status if state else "open",
                "is_main": quest.is_main,
            }
            # Ohne den letzten Fortschrittsvermerk saehe die KI nur
            # "offen" und wuesste nicht, wo innerhalb der Quest die Gruppe
            # steht -- sie koennte nicht auf Erreichtem aufbauen und
            # begaenne die Quest faktisch jede Runde von vorn.
            if state is not None and state.note:
                entry["latest_progress"] = state.note
            if state is not None and state.progress:
                entry["progress"] = state.progress
            payload.append(entry)
        return payload

    async def _facts_payload(self) -> list[dict[str, Any]]:
        stmt = (
            sa.select(Fact)
            .where(Fact.game_id == self._game.id, Fact.invalidated_at_seq.is_(None))
            .order_by(Fact.created_at_seq.desc())
            .limit(40)
        )
        facts = list((await self._session.execute(stmt)).scalars().all())
        return [
            {"key": fact.key, "statement": fact.statement, "visibility": fact.visibility}
            for fact in reversed(facts)
        ]

    async def _summaries_payload(self) -> list[str]:
        stmt = (
            sa.select(SceneSummary)
            .where(SceneSummary.game_id == self._game.id)
            .order_by(SceneSummary.to_seq.desc())
            .limit(self._settings.context_recent_summaries)
        )
        summaries = list((await self._session.execute(stmt)).scalars().all())
        return [summary.text for summary in reversed(summaries)]

    async def _recent_events_payload(self) -> list[dict[str, Any]]:
        events = await load_recent_events(
            self._session, self._game.id, limit=self._settings.context_recent_events
        )
        return [
            {"turn": event.turn_number, "type": event.type, "summary": event.summary}
            for event in events
            if event.summary
        ]
