"""Runden, Aktionen, Ereignisse, Wuerfe, Narrationen und Zusammenfassungen."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

TURN_STATUSES = ("collecting", "resolving", "completed")
ACTION_STATUSES = ("pending", "accepted", "rejected", "resolved")
NARRATION_KINDS = ("public", "private")


class Turn(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eine Spielrunde (ein Zug aller Spieler)."""

    __tablename__ = "turns"
    __table_args__ = (
        sa.UniqueConstraint("game_id", "number", name="uq_turns_game_number"),
        # Hoechstens ein laufender Zug je Ort -- mehrere gleichzeitig
        # "collecting" Zuege pro Spiel sind erlaubt, aber nie zwei am
        # selben Ort (Split-Party). Partieller Index statt einer
        # gewoehnlichen Unique-Constraint, weil abgeschlossene Zuege am
        # selben Ort sich sonst gegenseitig blockieren wuerden.
        sa.Index(
            "uq_turns_one_collecting_per_location",
            "game_id",
            "location_id",
            unique=True,
            sqlite_where=sa.text("status = 'collecting'"),
            postgresql_where=sa.text("status = 'collecting'"),
        ),
    )

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(sa.Integer)
    status: Mapped[str] = mapped_column(sa.String(20), default="collecting", index=True)
    scene_title: Mapped[str] = mapped_column(sa.String(200), default="")
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    suggestions: Mapped[dict[str, Any]] = mapped_column(default=dict)
    """Handlungsvorschlaege je Charaktername fuer diese Runde."""

    actions: Mapped[list[Action]] = relationship(
        back_populates="turn", cascade="all, delete-orphan", lazy="selectin"
    )


class Action(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eine von einem Spieler eingereichte Handlung."""

    __tablename__ = "actions"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("turns.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(sa.String(30), default="custom")
    """z. B. attack, investigate, talk, sneak, cast, use_item, flee, custom."""
    text: Mapped[str] = mapped_column(sa.Text)
    target_ref: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(sa.String(20), default="pending", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    outcome: Mapped[dict[str, Any]] = mapped_column(default=dict)

    turn: Mapped[Turn] = relationship(back_populates="actions")


class Event(UUIDPrimaryKeyMixin, Base):
    """Unveraenderliches Ereignis im Event-Log.

    Das Log ist die revisionssichere Historie der Runde. Es wird nur
    angehaengt, nie veraendert oder geloescht.
    """

    __tablename__ = "events"
    __table_args__ = (sa.UniqueConstraint("game_id", "seq", name="uq_events_game_seq"),)

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(sa.BigInteger, index=True)
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("turns.id", ondelete="SET NULL"), nullable=True
    )
    turn_number: Mapped[int] = mapped_column(sa.Integer, default=0)
    type: Mapped[str] = mapped_column(sa.String(60), index=True)
    actor_type: Mapped[str] = mapped_column(sa.String(20), default="system")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)
    visibility: Mapped[str] = mapped_column(sa.String(20), default="public")
    audience_player_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), nullable=True
    )
    summary: Mapped[str] = mapped_column(sa.Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )


class DiceRoll(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ein vom Backend ausgefuehrter Wuerfelwurf."""

    __tablename__ = "dice_rolls"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("turns.id", ondelete="SET NULL"), nullable=True
    )
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("actions.id", ondelete="SET NULL"), nullable=True
    )
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    notation: Mapped[str] = mapped_column(sa.String(40))
    rolls: Mapped[list[Any]] = mapped_column(default=list)
    modifier: Mapped[int] = mapped_column(sa.Integer, default=0)
    total: Mapped[int] = mapped_column(sa.Integer, default=0)
    difficulty: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    success: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    degree: Mapped[str] = mapped_column(sa.String(20), default="")
    """critical_success, success, partial, failure, critical_failure."""
    reason: Mapped[str] = mapped_column(sa.String(200), default="")


class Narration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Erzaehltext der KI."""

    __tablename__ = "narrations"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("turns.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(sa.String(20), default="public")
    audience_player_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=True
    )
    text: Mapped[str] = mapped_column(sa.Text)
    scene_title: Mapped[str] = mapped_column(sa.String(200), default="")


class SceneSummary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Verdichtete Zusammenfassung als Langzeitgedaechtnis.

    Zusammenfassungen ersetzen niemals Ereignisse, sie ergaenzen sie.
    """

    __tablename__ = "scene_summaries"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    from_seq: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    to_seq: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    turn_number: Mapped[int] = mapped_column(sa.Integer, default=0)
    text: Mapped[str] = mapped_column(sa.Text)
    highlights: Mapped[list[Any]] = mapped_column(default=list)
