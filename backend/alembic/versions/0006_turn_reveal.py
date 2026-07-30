"""Gruppenweites Aufdecken von Wuerfelergebnissen, Erzaehlung und Ton

Revision ID: 0006_turn_reveal
Revises: 0005_stall_streak
Create Date: 2026-07-30

turns.revealed_at bleibt NULL, bis alle erwarteten Spieler eines Zugs
bestaetigt haben (TurnAck) oder die Spielleitung vorzeitig aufdeckt.
Bestehende, laengst abgeschlossene Zuege bleiben NULL -- fuer sie zeigt das
Frontend ohnehin keinen Wuerfel-Popup mehr an, das waere nur fuer den
jeweils letzten Zug pro Ort relevant.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_turn_reveal"
down_revision: str | None = "0005_stall_streak"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("turns", sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "turn_acks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("turn_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("player_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id", "player_id", name="uq_turn_ack"),
    )
    op.create_index(op.f("ix_turn_acks_turn_id"), "turn_acks", ["turn_id"], unique=False)
    op.create_index(op.f("ix_turn_acks_player_id"), "turn_acks", ["player_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_turn_acks_player_id"), table_name="turn_acks")
    op.drop_index(op.f("ix_turn_acks_turn_id"), table_name="turn_acks")
    op.drop_table("turn_acks")
    op.drop_column("turns", "revealed_at")
