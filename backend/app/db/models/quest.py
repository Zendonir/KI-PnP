"""Quests und deren Zustandsverlauf."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

QUEST_STATUSES = ("hidden", "open", "active", "completed", "failed")


class Quest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eine Aufgabe fuer die Gruppe."""

    __tablename__ = "quests"
    __table_args__ = (sa.UniqueConstraint("game_id", "title", name="uq_quests_game_title"),)

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str] = mapped_column(sa.Text, default="")
    giver_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("world_entities.id", ondelete="SET NULL"), nullable=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    is_main: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    reward: Mapped[dict[str, Any]] = mapped_column(default=dict)

    states: Mapped[list[QuestState]] = relationship(
        back_populates="quest",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="QuestState.created_at",
    )

    @property
    def current_state(self) -> QuestState | None:
        """Juengster Zustandseintrag."""
        return self.states[-1] if self.states else None


class QuestState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ein Zustandseintrag einer Quest (Historie bleibt erhalten)."""

    __tablename__ = "quest_states"

    quest_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("quests.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(sa.String(20), default="open")
    progress: Mapped[dict[str, Any]] = mapped_column(default=dict)
    visibility: Mapped[str] = mapped_column(sa.String(20), default="public")
    note: Mapped[str] = mapped_column(sa.Text, default="")
    turn_number: Mapped[int] = mapped_column(sa.Integer, default=0)

    quest: Mapped[Quest] = relationship(back_populates="states")
