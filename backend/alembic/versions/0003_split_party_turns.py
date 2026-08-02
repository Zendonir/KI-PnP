"""Split-Party: hoechstens ein laufender Zug je Ort

Revision ID: 0003_split_party
Revises: 0002_audio
Create Date: 2026-07-30

Reine Absicherung, keine Datenaenderung: von jetzt an kann es mehrere
gleichzeitig "collecting" Zuege je Runde geben, aber nie zwei am selben Ort.
Jede laufende Installation hat aktuell genau einen "collecting"-Zug mit
bereits gesetztem location_id -- die neue Invariante ist damit fuer jeden
bestehenden Datensatz automatisch erfuellt, ein Backfill ist nicht noetig.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_split_party"
down_revision: str | None = "0002_audio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLLECTING = sa.text("status = 'collecting'")


def upgrade() -> None:
    op.create_index(
        "uq_turns_one_collecting_per_location",
        "turns",
        ["game_id", "location_id"],
        unique=True,
        postgresql_where=_COLLECTING,
        sqlite_where=_COLLECTING,
    )


def downgrade() -> None:
    op.drop_index("uq_turns_one_collecting_per_location", table_name="turns")
