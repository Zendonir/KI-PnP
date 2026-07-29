"""Audio- und Bildauftraege."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MEDIA_STATUSES = ("pending", "running", "ready", "failed", "skipped")


class AudioJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Sprachausgabe zu einer Narration."""

    __tablename__ = "audio_jobs"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    narration_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("narrations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(sa.String(30), default="browser")
    voice: Mapped[str] = mapped_column(sa.String(60), default="narrator")
    status: Mapped[str] = mapped_column(sa.String(20), default="pending", index=True)
    target: Mapped[str] = mapped_column(sa.String(30), default="browser")
    """browser, sonos, chromecast, home_assistant, airplay."""
    url: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    text: Mapped[str] = mapped_column(sa.Text, default="")
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Image(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Generiertes Bild zu einer Szene, einem NSC oder einem Gegenstand."""

    __tablename__ = "images"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    subject_type: Mapped[str] = mapped_column(sa.String(20), default="scene")
    subject_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)
    prompt: Mapped[str] = mapped_column(sa.Text, default="")
    provider: Mapped[str] = mapped_column(sa.String(30), default="none")
    status: Mapped[str] = mapped_column(sa.String(20), default="pending")
    url: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
