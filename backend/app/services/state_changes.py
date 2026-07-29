"""Validierung und Anwendung von Zustandsaenderungen.

Dies ist die einzige Stelle, an der sich der Spielzustand aendert. Vorschlaege
-- egal ob vom Regelwerk oder von der KI -- durchlaufen hier drei Stufen:

1. Formatpruefung gegen ``app.domain.changes``
2. Fachliche Pruefung (existiert das Objekt? reicht das Mana? usw.)
3. Anwendung in der Datenbank inklusive Ereignisprotokoll

Abgelehnte Vorschlaege werden nicht stillschweigend verworfen, sondern als
Ereignis protokolliert.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pydantic
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Character,
    CharacterStat,
    Fact,
    Game,
    Inventory,
    InventoryItem,
    Item,
    Knowledge,
    Location,
    Quest,
    QuestState,
    Relationship,
    WorldEntity,
)
from app.domain import changes as ch
from app.services import events as ev
from app.services.events import EventRecorder

_ADAPTER: pydantic.TypeAdapter[ch.StateChange] = pydantic.TypeAdapter(ch.StateChange)

# Werte, die niemals unter null fallen duerfen.
_CLAMPED_STATS = ("hp", "mana", "stamina")


class ChangeRejected(Exception):
    """Ein Vorschlag ist fachlich nicht anwendbar."""


@dataclass(slots=True)
class ChangeApplication:
    """Ergebnis eines Anwendungslaufs."""

    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)


class StateChangeApplier:
    """Wendet geprueste Aenderungen auf eine Spielrunde an."""

    def __init__(
        self,
        session: AsyncSession,
        game: Game,
        recorder: EventRecorder,
        *,
        turn_id: uuid.UUID | None = None,
    ) -> None:
        self._session = session
        self._game = game
        self._recorder = recorder
        self._turn_id = turn_id

    # -- oeffentliche API ------------------------------------------------

    async def apply_raw(
        self, raw_changes: list[dict[str, Any]], *, source: str = "ai"
    ) -> ChangeApplication:
        """Validiert rohe Vorschlaege (z. B. von der KI) und wendet sie an."""
        parsed: list[ch.StateChange] = []
        application = ChangeApplication()
        for raw in raw_changes:
            if not isinstance(raw, dict):
                application.rejected.append({"change": raw, "reason": "Kein Objekt"})
                continue
            try:
                parsed.append(_ADAPTER.validate_python(raw))
            except pydantic.ValidationError as exc:
                application.rejected.append(
                    {"change": raw, "reason": _first_error(exc)}
                )
        applied = await self.apply(parsed, source=source)
        application.accepted.extend(applied.accepted)
        application.rejected.extend(applied.rejected)
        await self._record_rejections(application.rejected, source)
        return application

    async def apply(
        self, proposals: list[ch.StateChange], *, source: str = "rules"
    ) -> ChangeApplication:
        """Wendet bereits typisierte Aenderungen an."""
        application = ChangeApplication()
        for change in proposals:
            handler = self._handlers().get(change.op)
            if handler is None:  # pragma: no cover - durch Union ausgeschlossen
                application.rejected.append(
                    {"change": change.model_dump(), "reason": f"Unbekannte Operation {change.op}"}
                )
                continue
            try:
                summary = await handler(change)
            except ChangeRejected as exc:
                application.rejected.append({"change": change.model_dump(), "reason": str(exc)})
                continue
            await self._session.flush()
            payload = change.model_dump()
            payload["source"] = source
            await self._recorder.record(
                self._game,
                type=ev.STATE_CHANGED,
                summary=summary,
                payload=payload,
                turn_id=self._turn_id,
            )
            application.accepted.append(payload)
        return application

    async def _record_rejections(self, rejected: list[dict[str, Any]], source: str) -> None:
        for entry in rejected:
            await self._recorder.record(
                self._game,
                type=ev.CHANGE_REJECTED,
                summary=f"Vorschlag abgelehnt: {entry['reason']}",
                payload={"source": source, **entry},
                turn_id=self._turn_id,
                visibility="party",
                counts_towards_summary=False,
            )

    # -- Zuordnung -------------------------------------------------------

    def _handlers(self) -> dict[str, Any]:
        return {
            "character.adjust_stat": self._adjust_stat,
            "character.set_condition": self._set_condition,
            "character.move": self._move_character,
            "character.grant_experience": self._grant_experience,
            "item.define": self._define_item,
            "inventory.add_item": self._add_item,
            "inventory.remove_item": self._remove_item,
            "inventory.equip_item": self._equip_item,
            "entity.create": self._create_entity,
            "entity.update": self._update_entity,
            "location.create": self._create_location,
            "location.discover": self._discover_location,
            "quest.create": self._create_quest,
            "quest.update": self._update_quest,
            "relationship.set": self._set_relationship,
            "fact.assert": self._assert_fact,
            "fact.invalidate": self._invalidate_fact,
            "knowledge.grant": self._grant_knowledge,
        }

    # -- Aufloesung von Referenzen ---------------------------------------

    async def _find_character(self, name: str) -> Character:
        stmt = sa.select(Character).where(
            Character.game_id == self._game.id,
            sa.func.lower(Character.name) == name.strip().lower(),
        )
        character = (await self._session.execute(stmt)).scalars().first()
        if character is None:
            raise ChangeRejected(f"Unbekannter Charakter: {name!r}")
        return character

    async def _find_entity(self, name: str) -> WorldEntity:
        stmt = sa.select(WorldEntity).where(
            WorldEntity.game_id == self._game.id,
            sa.func.lower(WorldEntity.name) == name.strip().lower(),
        )
        entity = (await self._session.execute(stmt)).scalars().first()
        if entity is None:
            raise ChangeRejected(f"Unbekannte Entitaet: {name!r}")
        return entity

    async def _find_location(self, name: str) -> Location:
        stmt = sa.select(Location).where(
            Location.game_id == self._game.id,
            sa.func.lower(Location.name) == name.strip().lower(),
        )
        location = (await self._session.execute(stmt)).scalars().first()
        if location is None:
            raise ChangeRejected(f"Unbekannter Ort: {name!r}")
        return location

    async def _find_quest(self, title: str) -> Quest:
        stmt = sa.select(Quest).where(
            Quest.game_id == self._game.id,
            sa.func.lower(Quest.title) == title.strip().lower(),
        )
        quest = (await self._session.execute(stmt)).scalars().first()
        if quest is None:
            raise ChangeRejected(f"Unbekannte Quest: {title!r}")
        return quest

    async def _find_item(self, name: str) -> Item | None:
        stmt = sa.select(Item).where(
            Item.game_id == self._game.id,
            sa.func.lower(Item.name) == name.strip().lower(),
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def _inventory_for(self, owner_type: str, owner_id: uuid.UUID) -> Inventory:
        stmt = sa.select(Inventory).where(
            Inventory.owner_type == owner_type, Inventory.owner_id == owner_id
        )
        inventory = (await self._session.execute(stmt)).scalars().first()
        if inventory is None:
            inventory = Inventory(
                game_id=self._game.id, owner_type=owner_type, owner_id=owner_id
            )
            self._session.add(inventory)
            await self._session.flush()
        return inventory

    async def _resolve_owner(self, name: str, owner_type: str) -> tuple[str, uuid.UUID]:
        if owner_type == "character":
            return "character", (await self._find_character(name)).id
        if owner_type == "entity":
            return "entity", (await self._find_entity(name)).id
        return "location", (await self._find_location(name)).id

    async def _resolve_actor(self, name: str) -> tuple[str, uuid.UUID, str]:
        """Loest einen Namen als Charakter oder Entitaet auf."""
        try:
            character = await self._find_character(name)
        except ChangeRejected:
            entity = await self._find_entity(name)
            return "entity", entity.id, entity.name
        return "character", character.id, character.name

    # -- Handler ---------------------------------------------------------

    async def _adjust_stat(self, change: ch.AdjustStat) -> str:
        character = await self._find_character(change.character)
        stmt = sa.select(CharacterStat).where(
            CharacterStat.character_id == character.id, CharacterStat.key == change.stat
        )
        stat = (await self._session.execute(stmt)).scalars().first()
        if stat is None:
            raise ChangeRejected(
                f"{character.name} besitzt keinen Wert {change.stat!r}"
            )
        new_value = stat.value + change.delta
        if change.stat in _CLAMPED_STATS:
            new_value = max(0, new_value)
        if stat.max_value is not None:
            new_value = min(new_value, stat.max_value)
        stat.value = new_value

        note = ""
        if change.stat == "hp" and new_value <= 0 and character.is_alive:
            character.is_alive = False
            conditions = list(character.conditions or [])
            if "bewusstlos" not in conditions:
                conditions.append("bewusstlos")
            character.conditions = conditions
            note = " Der Charakter geht zu Boden."
        return f"{character.name}: {change.stat} {change.delta:+d} -> {new_value}.{note}"

    async def _set_condition(self, change: ch.SetCondition) -> str:
        character = await self._find_character(change.character)
        conditions = list(character.conditions or [])
        normalized = change.condition.strip()
        exists = any(entry.casefold() == normalized.casefold() for entry in conditions)
        if change.active and not exists:
            conditions.append(normalized)
        elif not change.active and exists:
            conditions = [
                entry for entry in conditions if entry.casefold() != normalized.casefold()
            ]
        character.conditions = conditions
        verb = "erhaelt" if change.active else "verliert"
        return f"{character.name} {verb} den Zustand {normalized!r}."

    async def _move_character(self, change: ch.MoveCharacter) -> str:
        character = await self._find_character(change.character)
        location = await self._find_location(change.location)
        character.location_id = location.id
        location.is_discovered = True
        return f"{character.name} befindet sich nun in {location.name}."

    async def _grant_experience(self, change: ch.GrantExperience) -> str:
        character = await self._find_character(change.character)
        character.experience += change.amount
        levelled = ""
        while character.experience >= character.level * 100:
            character.experience -= character.level * 100
            character.level += 1
            levelled = f" Stufenaufstieg auf {character.level}!"
        return f"{character.name} erhaelt {change.amount} Erfahrung.{levelled}"

    async def _define_item(self, change: ch.DefineItem) -> str:
        existing = await self._find_item(change.name)
        if existing is not None:
            raise ChangeRejected(f"Gegenstand {change.name!r} existiert bereits")
        self._session.add(
            Item(
                game_id=self._game.id,
                name=change.name.strip(),
                description=change.description,
                kind=change.kind,
                weight=change.weight,
                value=change.value,
                properties=dict(change.properties),
            )
        )
        return f"Neuer Gegenstand definiert: {change.name}."

    async def _ensure_item(self, name: str) -> Item:
        item = await self._find_item(name)
        if item is not None:
            return item
        item = Item(game_id=self._game.id, name=name.strip(), description="", kind="misc")
        self._session.add(item)
        await self._session.flush()
        return item

    async def _add_item(self, change: ch.AddItem) -> str:
        owner_type, owner_id = await self._resolve_owner(change.owner, change.owner_type)
        inventory = await self._inventory_for(owner_type, owner_id)
        item = await self._ensure_item(change.item)
        stmt = sa.select(InventoryItem).where(
            InventoryItem.inventory_id == inventory.id, InventoryItem.item_id == item.id
        )
        entry = (await self._session.execute(stmt)).scalars().first()
        if entry is not None and item.stackable:
            entry.quantity += change.quantity
        else:
            self._session.add(
                InventoryItem(
                    inventory_id=inventory.id, item_id=item.id, quantity=change.quantity
                )
            )
        return f"{change.owner} erhaelt {change.quantity}x {item.name}."

    async def _remove_item(self, change: ch.RemoveItem) -> str:
        owner_type, owner_id = await self._resolve_owner(change.owner, change.owner_type)
        inventory = await self._inventory_for(owner_type, owner_id)
        item = await self._find_item(change.item)
        if item is None:
            raise ChangeRejected(f"Unbekannter Gegenstand: {change.item!r}")
        stmt = sa.select(InventoryItem).where(
            InventoryItem.inventory_id == inventory.id, InventoryItem.item_id == item.id
        )
        entry = (await self._session.execute(stmt)).scalars().first()
        if entry is None or entry.quantity < change.quantity:
            raise ChangeRejected(
                f"{change.owner} besitzt nicht {change.quantity}x {item.name}"
            )
        entry.quantity -= change.quantity
        if entry.quantity <= 0:
            await self._session.delete(entry)
        return f"{change.owner} verliert {change.quantity}x {item.name}."

    async def _equip_item(self, change: ch.EquipItem) -> str:
        character = await self._find_character(change.character)
        inventory = await self._inventory_for("character", character.id)
        item = await self._find_item(change.item)
        if item is None:
            raise ChangeRejected(f"Unbekannter Gegenstand: {change.item!r}")
        stmt = sa.select(InventoryItem).where(
            InventoryItem.inventory_id == inventory.id, InventoryItem.item_id == item.id
        )
        entry = (await self._session.execute(stmt)).scalars().first()
        if entry is None:
            raise ChangeRejected(f"{character.name} besitzt {item.name} nicht")
        entry.equipped = change.equipped
        entry.slot = change.slot
        verb = "ruestet" if change.equipped else "legt ab"
        return f"{character.name} {verb} {item.name}."

    async def _create_entity(self, change: ch.CreateEntity) -> str:
        stmt = sa.select(WorldEntity).where(
            WorldEntity.game_id == self._game.id,
            sa.func.lower(WorldEntity.name) == change.name.strip().lower(),
        )
        if (await self._session.execute(stmt)).scalars().first() is not None:
            raise ChangeRejected(f"Entitaet {change.name!r} existiert bereits")
        location_id = None
        if change.location:
            location_id = (await self._find_location(change.location)).id
        self._session.add(
            WorldEntity(
                game_id=self._game.id,
                kind=change.kind,
                name=change.name.strip(),
                description=change.description,
                location_id=location_id,
                data=dict(change.data),
            )
        )
        return f"Neu in der Welt: {change.name} ({change.kind})."

    async def _update_entity(self, change: ch.UpdateEntity) -> str:
        entity = await self._find_entity(change.entity)
        if change.description is not None:
            entity.description = change.description
        if change.is_alive is not None:
            entity.is_alive = change.is_alive
        if change.location:
            entity.location_id = (await self._find_location(change.location)).id
        if change.states:
            merged = dict(entity.data or {})
            merged.update(change.states)
            entity.data = merged
        return f"{entity.name} wurde aktualisiert."

    async def _create_location(self, change: ch.CreateLocation) -> str:
        stmt = sa.select(Location).where(
            Location.game_id == self._game.id,
            sa.func.lower(Location.name) == change.name.strip().lower(),
        )
        if (await self._session.execute(stmt)).scalars().first() is not None:
            raise ChangeRejected(f"Ort {change.name!r} existiert bereits")
        parent_id = (await self._find_location(change.parent)).id if change.parent else None
        self._session.add(
            Location(
                game_id=self._game.id,
                name=change.name.strip(),
                description=change.description,
                parent_id=parent_id,
                is_discovered=change.discovered,
            )
        )
        return f"Neuer Ort: {change.name}."

    async def _discover_location(self, change: ch.DiscoverLocation) -> str:
        location = await self._find_location(change.location)
        location.is_discovered = True
        return f"{location.name} wurde entdeckt."

    async def _create_quest(self, change: ch.CreateQuest) -> str:
        stmt = sa.select(Quest).where(
            Quest.game_id == self._game.id,
            sa.func.lower(Quest.title) == change.title.strip().lower(),
        )
        if (await self._session.execute(stmt)).scalars().first() is not None:
            raise ChangeRejected(f"Quest {change.title!r} existiert bereits")
        giver_id = (await self._find_entity(change.giver)).id if change.giver else None
        quest = Quest(
            game_id=self._game.id,
            title=change.title.strip(),
            description=change.description,
            giver_entity_id=giver_id,
            is_main=change.is_main,
        )
        self._session.add(quest)
        await self._session.flush()
        self._session.add(
            QuestState(
                quest_id=quest.id,
                status="open",
                visibility=change.visibility,
                turn_number=self._game.current_turn_number,
            )
        )
        return f"Neue Quest: {change.title}."

    async def _update_quest(self, change: ch.UpdateQuest) -> str:
        quest = await self._find_quest(change.quest)
        current = quest.current_state
        self._session.add(
            QuestState(
                quest_id=quest.id,
                status=change.status,
                note=change.note,
                progress=dict(change.progress),
                visibility=current.visibility if current else "public",
                turn_number=self._game.current_turn_number,
            )
        )
        return f"Quest {quest.title!r} ist jetzt {change.status}."

    async def _set_relationship(self, change: ch.SetRelationship) -> str:
        source_type, source_id, source_name = await self._resolve_actor(change.source)
        target_type, target_id, target_name = await self._resolve_actor(change.target)
        stmt = sa.select(Relationship).where(
            Relationship.game_id == self._game.id,
            Relationship.source_type == source_type,
            Relationship.source_id == source_id,
            Relationship.target_type == target_type,
            Relationship.target_id == target_id,
            Relationship.kind == change.kind,
        )
        relationship = (await self._session.execute(stmt)).scalars().first()
        if relationship is None:
            relationship = Relationship(
                game_id=self._game.id,
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                target_id=target_id,
                kind=change.kind,
            )
            self._session.add(relationship)
        relationship.value = change.value
        relationship.notes = change.notes
        return f"Beziehung {source_name} -> {target_name} ({change.kind}): {change.value}."

    async def _assert_fact(self, change: ch.AssertFact) -> str:
        stmt = sa.select(Fact).where(
            Fact.game_id == self._game.id,
            Fact.key == change.key,
            Fact.invalidated_at_seq.is_(None),
        )
        for previous in (await self._session.execute(stmt)).scalars().all():
            previous.invalidated_at_seq = self._game.event_seq + 1
        self._session.add(
            Fact(
                game_id=self._game.id,
                key=change.key,
                statement=change.statement,
                source="ai",
                visibility=change.visibility,
                confidence=change.confidence,
                created_at_seq=self._game.event_seq + 1,
                turn_number=self._game.current_turn_number,
            )
        )
        if change.visibility == "public":
            self._session.add(
                Knowledge(
                    game_id=self._game.id,
                    subject_type="public",
                    subject_id=None,
                    content=change.statement,
                    certainty="truth",
                    source="fact",
                    turn_number=self._game.current_turn_number,
                    created_at_seq=self._game.event_seq + 1,
                )
            )
        return f"Fakt gesetzt [{change.key}]: {change.statement}"

    async def _invalidate_fact(self, change: ch.InvalidateFact) -> str:
        stmt = sa.select(Fact).where(
            Fact.game_id == self._game.id,
            Fact.key == change.key,
            Fact.invalidated_at_seq.is_(None),
        )
        facts = list((await self._session.execute(stmt)).scalars().all())
        if not facts:
            raise ChangeRejected(f"Kein gueltiger Fakt mit Schluessel {change.key!r}")
        for fact in facts:
            fact.invalidated_at_seq = self._game.event_seq + 1
        return f"Fakt [{change.key}] gilt nicht mehr."

    async def _grant_knowledge(self, change: ch.GrantKnowledge) -> str:
        subject_id: uuid.UUID | None = None
        subject_type = change.subject_type
        label = "Alle"
        if subject_type == "character":
            character = await self._find_character(change.subject)
            subject_id, label = character.id, character.name
        elif subject_type == "entity":
            entity = await self._find_entity(change.subject)
            subject_id, label = entity.id, entity.name
        self._session.add(
            Knowledge(
                game_id=self._game.id,
                subject_type=subject_type,
                subject_id=subject_id,
                content=change.content,
                certainty=change.certainty,
                source="ai",
                turn_number=self._game.current_turn_number,
                created_at_seq=self._game.event_seq + 1,
            )
        )
        return f"{label} weiss nun: {change.content}"


def _first_error(exc: pydantic.ValidationError) -> str:
    """Formatiert den ersten Validierungsfehler lesbar."""
    errors = exc.errors()
    if not errors:  # pragma: no cover - defensiv
        return "Ungueltiger Vorschlag"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()) if part != "function-after")
    return f"{location or 'op'}: {first.get('msg', 'ungueltig')}"
