"""Deklarative Basis und wiederverwendbare Spaltentypen."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSON-Spalten nutzen unter PostgreSQL JSONB und fallen sonst auf JSON zurueck
# (wichtig fuer SQLite-basierte Tests).
JSONType = sa.JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    """Aktueller Zeitpunkt in UTC."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Gemeinsame Basis aller ORM-Modelle."""

    type_annotation_map = {dict[str, Any]: JSONType, list[Any]: JSONType}


class UUIDPrimaryKeyMixin:
    """Primaerschluessel als UUID."""

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    """Erstell- und Aenderungszeitpunkt."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
