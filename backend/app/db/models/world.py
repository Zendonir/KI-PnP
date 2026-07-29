"""Welt: Orte, Entitaeten, Beziehungen, Fakten und Wissen."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ENTITY_KINDS = ("npc", "monster", "object", "faction", "riddle")
VISIBILITIES = ("public", "party", "private", "secret")
CERTAINTIES = ("truth", "rumor", "belief", "lie")


class Location(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ein Ort in der Spielwelt."""

    __tablename__ = "locations"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(120))
    description: Mapped[str] = mapped_column(sa.Text, default="")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    is_discovered: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    coordinates: Mapped[dict[str, Any]] = mapped_column(default=dict)
    tags: Mapped[list[Any]] = mapped_column(default=list)


class WorldEntity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """NSC, Monster, Weltobjekt, Fraktion oder Raetsel."""

    __tablename__ = "world_entities"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(sa.String(20), index=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    description: Mapped[str] = mapped_column(sa.Text, default="")
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    is_alive: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    is_known_to_party: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    """Freie Zusatzdaten, z. B. Kampfwerte oder Loesung eines Raetsels."""

    states: Mapped[list[EntityState]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", lazy="selectin"
    )


class EntityState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Veraenderlicher Zustand einer Weltentitaet."""

    __tablename__ = "entity_states"
    __table_args__ = (sa.UniqueConstraint("entity_id", "key", name="uq_entity_state_key"),)

    entity_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("world_entities.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(sa.String(40))
    value: Mapped[str] = mapped_column(sa.String(200), default="")
    numeric_value: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    entity: Mapped[WorldEntity] = relationship(back_populates="states")


class Relationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Beziehung zwischen zwei Akteuren (Charakter oder Entitaet)."""

    __tablename__ = "relationships"
    __table_args__ = (
        sa.UniqueConstraint(
            "game_id", "source_type", "source_id", "target_type", "target_id", "kind",
            name="uq_relationship_pair",
        ),
    )

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(sa.String(20))
    source_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), index=True)
    target_type: Mapped[str] = mapped_column(sa.String(20))
    target_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(sa.String(40), default="attitude")
    value: Mapped[int] = mapped_column(sa.Integer, default=0)
    """-100 (feindlich) bis +100 (verbuendet)."""
    notes: Mapped[str] = mapped_column(sa.Text, default="")


class Fact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ein dauerhafter Weltfakt.

    Fakten sind die maszgebliche Wahrheit ueber die Welt. Sie werden nie
    geloescht, sondern durch Setzen von ``invalidated_at_seq`` entwertet.
    """

    __tablename__ = "facts"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(sa.String(120), index=True)
    """Stabiler Bezeichner, z. B. ``gate.destroyed`` oder ``king.dead``."""
    statement: Mapped[str] = mapped_column(sa.Text)
    subject_type: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(sa.String(20), default="system")
    """``system``, ``rules``, ``ai`` oder ``player``."""
    visibility: Mapped[str] = mapped_column(sa.String(20), default="public")
    confidence: Mapped[int] = mapped_column(sa.Integer, default=100)
    created_at_seq: Mapped[int] = mapped_column(sa.BigInteger, default=0, index=True)
    invalidated_at_seq: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True, index=True)
    turn_number: Mapped[int] = mapped_column(sa.Integer, default=0)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)

    @property
    def is_valid(self) -> bool:
        return self.invalidated_at_seq is None


class Knowledge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Wer weisz was?

    Trennt Wahrheit (``facts``) von dem, was einzelne Charaktere oder NSC
    glauben. Die KI erhaelt nur Wissen, das dem jeweiligen Empfaenger
    tatsaechlich bekannt ist.
    """

    __tablename__ = "knowledge"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    subject_type: Mapped[str] = mapped_column(sa.String(20), index=True)
    """``public``, ``character`` oder ``entity``."""
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), nullable=True, index=True
    )
    fact_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("facts.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(sa.Text)
    certainty: Mapped[str] = mapped_column(sa.String(20), default="truth")
    source: Mapped[str] = mapped_column(sa.String(40), default="system")
    turn_number: Mapped[int] = mapped_column(sa.Integer, default=0)
    created_at_seq: Mapped[int] = mapped_column(sa.BigInteger, default=0, index=True)

    fact: Mapped[Fact | None] = relationship(lazy="selectin")
