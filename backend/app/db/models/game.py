"""Spielrunden, Einstellungen und Spieler."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.character import Character

# Spielstatus: lobby -> active -> (paused) -> finished
GAME_STATUSES = ("lobby", "active", "paused", "finished")
PLAYER_ROLES = ("host", "player")


class Game(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eine Spielrunde."""

    __tablename__ = "games"

    code: Mapped[str] = mapped_column(sa.String(12), unique=True, index=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    status: Mapped[str] = mapped_column(sa.String(20), default="lobby", index=True)
    host_player_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)
    current_turn_number: Mapped[int] = mapped_column(sa.Integer, default=0)
    event_seq: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    """Fortlaufende Ereignisnummer. Wird ausschliesslich vom Backend erhoeht."""
    events_since_summary: Mapped[int] = mapped_column(sa.Integer, default=0)
    stall_streak: Mapped[int] = mapped_column(sa.Integer, default=0)
    """Anzahl aufeinanderfolgender Zuege ohne Erfolg bei einer gewerteten
    Handlung. Steigt bei einem erfolglosen Zug, faellt bei einem Erfolg
    auf 0 zurueck; ein reiner "wait"-Zug aendert nichts. Signalisiert der
    KI, wann sie statt weiterer Atmosphaere eine konkrete Wendung liefern
    muss (siehe app.ai.prompts.build_turn_prompt)."""
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    settings: Mapped[GameSettings] = relationship(
        back_populates="game", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    players: Mapped[list[Player]] = relationship(
        back_populates="game", cascade="all, delete-orphan", lazy="selectin"
    )


class GameSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Bei der Spielerstellung gewaehlte Optionen."""

    __tablename__ = "game_settings"

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), unique=True, index=True
    )
    genre: Mapped[str] = mapped_column(sa.String(50), default="fantasy")
    world: Mapped[str] = mapped_column(sa.String(200), default="")
    difficulty: Mapped[str] = mapped_column(sa.String(20), default="normal")
    duration: Mapped[str] = mapped_column(sa.String(20), default="medium")
    max_players: Mapped[int] = mapped_column(sa.Integer, default=6)
    rule_complexity: Mapped[str] = mapped_column(sa.String(20), default="light")
    play_style: Mapped[str] = mapped_column(sa.String(20), default="balanced")
    tone: Mapped[str] = mapped_column(sa.String(30), default="heroic")
    campaign_type: Mapped[str] = mapped_column(sa.String(20), default="free")
    ruleset: Mapped[str] = mapped_column(sa.String(50), default="classic")
    language: Mapped[str] = mapped_column(sa.String(10), default="de")

    ai_provider: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    tts_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    tts_provider: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    audio_targets: Mapped[list[Any]] = mapped_column(default=list)
    """Ausgabeziele fuer Audio, z. B. ["browser", "sonos"]."""
    audio_playback: Mapped[str] = mapped_column(sa.String(20), default="host")
    """Wer die Erzaehlung hoerbar abspielt: ``host`` (nur das Geraet der
    Spielleitung, also der Tischlautsprecher), ``all`` (jedes Geraet) oder
    ``none``. Ein einzelnes Geraet kann die Rolle lokal uebernehmen."""
    summary_every_n_events: Mapped[int] = mapped_column(sa.Integer, default=40)
    debug_mode: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)

    game: Mapped[Game] = relationship(back_populates="settings")


class Player(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ein menschlicher Teilnehmer einer Runde."""

    __tablename__ = "players"
    __table_args__ = (sa.UniqueConstraint("game_id", "name", name="uq_players_game_name"),)

    game_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(80))
    role: Mapped[str] = mapped_column(sa.String(20), default="player")
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    is_connected: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    game: Mapped[Game] = relationship(back_populates="players")
    character: Mapped[Character | None] = relationship(
        back_populates="player", uselist=False, lazy="selectin"
    )
