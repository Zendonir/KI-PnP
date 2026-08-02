"""Weltbild-Vorschau bei Rundenerstellung

Revision ID: 0008_game_premise
Revises: 0007_group_proposals
Create Date: 2026-08-01

Kurze, von der KI direkt bei der Rundenerstellung erzeugte Vorschau auf die
kommende Welt (2-4 Saetze) -- gibt Spielern vor der Charaktererstellung eine
grobe Orientierung. Die eigentliche Welterschaffung (Orte, NSC, Quests)
bleibt unveraendert beim Start der Runde (bootstrap_world).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_game_premise"
down_revision: str | None = "0007_group_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("games", sa.Column("premise", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("games", "premise")
