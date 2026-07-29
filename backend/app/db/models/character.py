"""Charaktere, Werte, Faehigkeiten, Gegenstaende und Inventare."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.game import Player

# Besitzer eines Inventars koennen Charaktere, Weltobjekte oder Orte sein.
INVENTORY_OWNER_TYPES = ("character", "entity", "location")


class Character(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Spielercharakter."""

    __tablename__ = "characters"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("players.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    name: Mapped[str] = mapped_column(sa.String(80))
    race: Mapped[str] = mapped_column(sa.String(60), default="")
    char_class: Mapped[str] = mapped_column("class", sa.String(60), default="")
    background: Mapped[str] = mapped_column(sa.Text, default="")
    avatar: Mapped[str] = mapped_column(sa.String(80), default="")
    level: Mapped[int] = mapped_column(sa.Integer, default=1)
    experience: Mapped[int] = mapped_column(sa.Integer, default=0)
    is_alive: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    conditions: Mapped[list[Any]] = mapped_column(default=list)
    """Aktive Zustaende, z. B. ["vergiftet", "gesegnet"]."""

    player: Mapped[Player | None] = relationship(back_populates="character")
    stats: Mapped[list[CharacterStat]] = relationship(
        back_populates="character", cascade="all, delete-orphan", lazy="selectin"
    )
    abilities: Mapped[list[CharacterAbility]] = relationship(
        back_populates="character", cascade="all, delete-orphan", lazy="selectin"
    )


class CharacterStat(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ein einzelner Charakterwert (regelwerkunabhaengig als Key/Value)."""

    __tablename__ = "character_stats"
    __table_args__ = (sa.UniqueConstraint("character_id", "key", name="uq_character_stat_key"),)

    character_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(sa.String(40))
    value: Mapped[int] = mapped_column(sa.Integer, default=0)
    max_value: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    character: Mapped[Character] = relationship(back_populates="stats")


class Ability(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Definition einer Faehigkeit innerhalb einer Runde."""

    __tablename__ = "abilities"
    __table_args__ = (sa.UniqueConstraint("game_id", "name", name="uq_abilities_game_name"),)

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(80))
    description: Mapped[str] = mapped_column(sa.Text, default="")
    cost_stat: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    cost_value: Mapped[int] = mapped_column(sa.Integer, default=0)
    requirements: Mapped[dict[str, Any]] = mapped_column(default=dict)
    effects: Mapped[dict[str, Any]] = mapped_column(default=dict)


class CharacterAbility(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Zuordnung einer Faehigkeit zu einem Charakter."""

    __tablename__ = "character_abilities"
    __table_args__ = (
        sa.UniqueConstraint("character_id", "ability_id", name="uq_character_ability"),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    ability_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("abilities.id", ondelete="CASCADE"), index=True
    )
    uses_left: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    character: Mapped[Character] = relationship(back_populates="abilities")
    ability: Mapped[Ability] = relationship(lazy="selectin")


class Item(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Gegenstandsdefinition."""

    __tablename__ = "items"
    __table_args__ = (sa.UniqueConstraint("game_id", "name", name="uq_items_game_name"),)

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(120))
    description: Mapped[str] = mapped_column(sa.Text, default="")
    kind: Mapped[str] = mapped_column(sa.String(40), default="misc")
    weight: Mapped[int] = mapped_column(sa.Integer, default=0)
    value: Mapped[int] = mapped_column(sa.Integer, default=0)
    stackable: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    properties: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Inventory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Inventar eines Charakters, Weltobjekts oder Ortes."""

    __tablename__ = "inventories"
    __table_args__ = (
        sa.UniqueConstraint("owner_type", "owner_id", name="uq_inventory_owner"),
    )

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    owner_type: Mapped[str] = mapped_column(sa.String(20))
    owner_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), index=True)
    capacity: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    entries: Mapped[list[InventoryItem]] = relationship(
        back_populates="inventory", cascade="all, delete-orphan", lazy="selectin"
    )


class InventoryItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Konkreter Gegenstand in einem Inventar."""

    __tablename__ = "inventory_items"

    inventory_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("inventories.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    quantity: Mapped[int] = mapped_column(sa.Integer, default=1)
    equipped: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    slot: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    state: Mapped[dict[str, Any]] = mapped_column(default=dict)

    inventory: Mapped[Inventory] = relationship(back_populates="entries")
    item: Mapped[Item] = relationship(lazy="selectin")
