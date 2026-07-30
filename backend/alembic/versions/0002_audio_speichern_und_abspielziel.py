"""Sprachaufnahmen speichern und Abspielziel festlegen

Revision ID: 0002_audio
Revises: 0001_initial
Create Date: 2026-07-30

Die beiden nicht optionalen Spalten erhalten bewusst einen Vorgabewert auf
Datenbankebene: ohne ihn scheitert das Hinzufuegen an bereits vorhandenen
Zeilen einer laufenden Installation.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_audio"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Serverseitig erzeugte Aufnahme samt Zusatzangaben.
    op.add_column("audio_jobs", sa.Column("data", sa.LargeBinary(), nullable=True))
    op.add_column("audio_jobs", sa.Column("mime_type", sa.String(length=60), nullable=True))
    op.add_column(
        "audio_jobs",
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
    )

    # Wer die Erzaehlung hoerbar abspielt: host | all | none
    op.add_column(
        "game_settings",
        sa.Column("audio_playback", sa.String(length=20), nullable=False, server_default="host"),
    )


def downgrade() -> None:
    op.drop_column("game_settings", "audio_playback")
    op.drop_column("audio_jobs", "size_bytes")
    op.drop_column("audio_jobs", "mime_type")
    op.drop_column("audio_jobs", "data")
