"""Laufzeit-Einstellungen fuer die ganze Installation (Settings-Menue)

Revision ID: 0004_runtime_settings
Revises: 0003_split_party
Create Date: 2026-07-30

Neue Tabelle mit genau einer Zeile (id=1) fuer installationsweite
Einstellungen wie die aktive TTS-Stimme/-Geschwindigkeit -- Backend-API und
Medien-Worker sind getrennte Prozesse, nur die Datenbank kann eine
Aenderung beiden sichtbar machen. Kein Datensatz wird hier eingefuegt: eine
fehlende Zeile bedeutet "nutze die Umgebungsvariablen", der bestehende
Zustand bleibt also unveraendert.

audio_jobs.speed ist nullable und braucht deshalb keinen Server-Vorgabewert
fuer bestehende Zeilen.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_runtime_settings"
down_revision: str | None = "0003_split_party"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tts_voice", sa.String(length=60), nullable=True),
        sa.Column("tts_speed", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("id = 1", name="ck_runtime_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("audio_jobs", sa.Column("speed", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("audio_jobs", "speed")
    op.drop_table("runtime_settings")
