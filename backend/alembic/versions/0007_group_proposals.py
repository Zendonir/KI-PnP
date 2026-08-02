"""Gruppenereignisse: gemeinsam beschlossene Handlungen mit Bonus

Revision ID: 0007_group_proposals
Revises: 0006_turn_reveal
Create Date: 2026-07-30

Markiert jemand eine Handlung als Gruppenereignis, werden andere aktive
Spieler am selben Ort gefragt, ob sie mitmachen wollen. Wer zustimmt,
teilt sich dieselbe Handlung (kind/text/stat), wuerfelt aber mit eigenem
Charakterwert und bekommt einen Bonus. Genau ein Vorschlag je Zug
(turn_id unique).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_group_proposals"
down_revision: str | None = "0006_turn_reveal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "group_proposals",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("turn_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("initiator_player_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("initiator_character_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("stat", sa.String(length=60), nullable=True),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiator_player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiator_character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id"),
    )
    op.create_table(
        "group_proposal_responses",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("proposal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("player_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["group_proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", "player_id", name="uq_group_proposal_response"),
    )
    op.create_index(
        op.f("ix_group_proposal_responses_proposal_id"),
        "group_proposal_responses",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_group_proposal_responses_player_id"),
        "group_proposal_responses",
        ["player_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_group_proposal_responses_player_id"), table_name="group_proposal_responses"
    )
    op.drop_index(
        op.f("ix_group_proposal_responses_proposal_id"), table_name="group_proposal_responses"
    )
    op.drop_table("group_proposal_responses")
    op.drop_table("group_proposals")
