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
            "turn_number": self._game.current_turn_number,
            "scene_title": turn.scene_title if turn else "",
            "location": self._location_payload(location),
            "characters": await self._characters_payload(include_knowledge=True),
            "npcs": await self._entities_payload(location),
            "quests": await self._quests_payload(),
            "facts": await self._facts_payload(),
            "summaries": await self._summaries_payload(),
            "recent_events": await self._recent_events_payload(),
            "action_results": action_results or [],
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

    async def _current_location(self, turn: Turn | None) -> Location | None:
        location_id: uuid.UUID | None = turn.location_id if turn else None
        if location_id is None:
            stmt = (
                sa.select(Character.location_id)
                .where(Character.game_id == self._game.id, Character.location_id.isnot(None))
                .limit(1)
            )
            location_id = (await self._session.execute(stmt)).scalars().first()
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

    async def _characters_payload(self, *, include_knowledge: bool) -> list[dict[str, Any]]:
        stmt = sa.select(Character).where(Character.game_id == self._game.id)
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
            payload.append(
                {
                    "title": quest.title,
                    "description": quest.description,
                    "status": state.status if state else "open",
                    "is_main": quest.is_main,
                }
            )
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
