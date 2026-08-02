"""Fortschritts-Zaehler gegen erzaehlerischen Stillstand

Revision ID: 0005_stall_streak
Revises: 0004_runtime_settings
Create Date: 2026-07-30

games.stall_streak zaehlt aufeinanderfolgende Zuege ohne Erfolg bei einer
gewerteten Handlung. Bestehende Runden starten bei 0 (server_default), also
im "kein Stillstand"-Zustand -- keine rueckwirkende Auswertung alter Zuege
noetig.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_stall_streak"
down_revision: str | None = "0004_runtime_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("stall_streak", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("games", "stall_streak")
