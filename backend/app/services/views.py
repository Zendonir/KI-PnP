"""Umwandlung von ORM-Objekten in API-Schemata."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Character, Inventory, InventoryItem, Location
from app.domain.rules import CharacterView, StatView, experience_for_next_level
from app.schemas.api import CharacterOut, InventoryEntryOut, StatOut


async def load_inventory_entries(
    session: AsyncSession, owner_type: str, owner_id: uuid.UUID
) -> list[InventoryItem]:
    """Laedt alle Inventareintraege eines Besitzers."""
    stmt = (
        sa.select(InventoryItem)
        .join(Inventory, Inventory.id == InventoryItem.inventory_id)
        .where(Inventory.owner_type == owner_type, Inventory.owner_id == owner_id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def character_to_out(session: AsyncSession, character: Character) -> CharacterOut:
    """Baut die API-Sicht eines Charakters."""
    entries = await load_inventory_entries(session, "character", character.id)
    location_name: str | None = None
    if character.location_id is not None:
        location = await session.get(Location, character.location_id)
        location_name = location.name if location else None

    return CharacterOut(
        id=character.id,
        player_id=character.player_id,
        name=character.name,
        race=character.race,
        **{"class": character.char_class},
        background=character.background,
        avatar=character.avatar,
        level=character.level,
        experience=character.experience,
        experience_to_next_level=experience_for_next_level(character.level),
        is_alive=character.is_alive,
        conditions=list(character.conditions or []),
        location=location_name,
        stats=[
            StatOut(key=stat.key, value=stat.value, max_value=stat.max_value)
            for stat in sorted(character.stats, key=lambda item: item.key)
        ],
        abilities=[link.ability.name for link in character.abilities],
        inventory=[
            InventoryEntryOut(
                id=entry.id,
                name=entry.item.name,
                description=entry.item.description,
                kind=entry.item.kind,
                quantity=entry.quantity,
                equipped=entry.equipped,
                slot=entry.slot,
            )
            for entry in entries
        ],
    )


async def character_to_domain(session: AsyncSession, character: Character) -> CharacterView:
    """Baut die Sicht, mit der das Regelwerk arbeitet."""
    entries = await load_inventory_entries(session, "character", character.id)
    return CharacterView(
        id=character.id,
        name=character.name,
        level=character.level,
        is_alive=character.is_alive,
        stats={
            stat.key: StatView(value=stat.value, max_value=stat.max_value)
            for stat in character.stats
        },
        conditions=list(character.conditions or []),
        items=[entry.item.name for entry in entries],
        abilities=[link.ability.name for link in character.abilities],
    )
