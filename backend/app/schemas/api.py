"""Datenvertraege der REST-API.

Alle Ein- und Ausgaben sind streng typisiert; daraus erzeugt FastAPI die
OpenAPI-Beschreibung automatisch.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Genre = Literal["fantasy", "scifi", "horror", "mystery", "cyberpunk", "postapocalyptic", "western"]
Difficulty = Literal["story", "easy", "normal", "hard", "deadly"]
Duration = Literal["oneshot", "short", "medium", "long", "campaign"]
Complexity = Literal["narrative", "light", "crunchy"]
PlayStyle = Literal["combat", "exploration", "roleplay", "balanced", "puzzle"]
CampaignType = Literal["free", "structured"]


class Schema(BaseModel):
    """Basis mit gemeinsamer Konfiguration."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# --- Einstellungen ------------------------------------------------------


AudioPlayback = Literal["host", "all", "none"]


class GameSettingsIn(Schema):
    genre: Genre = "fantasy"
    world: str = Field(default="", max_length=200)
    difficulty: Difficulty = "normal"
    duration: Duration = "medium"
    max_players: int = Field(default=6, ge=1, le=32)
    rule_complexity: Complexity = "light"
    play_style: PlayStyle = "balanced"
    tone: str = Field(default="heroic", max_length=30)
    campaign_type: CampaignType = "free"
    ruleset: str = "classic"
    language: str = Field(default="de", max_length=10)
    tts_enabled: bool = True
    audio_targets: list[str] = Field(default_factory=lambda: ["browser"])
    audio_playback: AudioPlayback = "host"
    """``host``: nur das Geraet der Spielleitung gibt Ton aus (Tischlautsprecher)."""
    ai_provider: str | None = None
    ai_model: str | None = None


class GameSettingsOut(GameSettingsIn):
    debug_mode: bool = False
    summary_every_n_events: int = 40


# --- Spiel und Spieler --------------------------------------------------


class PlayerOut(Schema):
    id: uuid.UUID
    name: str
    role: str
    is_active: bool
    is_connected: bool


class GameOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    status: str
    current_turn_number: int
    created_at: datetime
    settings: GameSettingsOut


class GameCreateRequest(Schema):
    name: str = Field(min_length=1, max_length=200)
    host_name: str = Field(min_length=1, max_length=80)
    settings: GameSettingsIn = Field(default_factory=GameSettingsIn)


class JoinRequest(Schema):
    player_name: str = Field(min_length=1, max_length=80)


class SessionOut(Schema):
    """Antwort nach Erstellen oder Beitreten."""

    game: GameOut
    player: PlayerOut
    token: str
    join_url: str
    qr_url: str


# --- Charaktere ---------------------------------------------------------


class StatOut(Schema):
    key: str
    value: int
    max_value: int | None = None


class InventoryEntryOut(Schema):
    id: uuid.UUID
    name: str
    description: str = ""
    kind: str = "misc"
    quantity: int = 1
    equipped: bool = False
    slot: str | None = None


class CharacterOut(Schema):
    id: uuid.UUID
    player_id: uuid.UUID | None
    name: str
    race: str
    char_class: str = Field(alias="class")
    background: str
    avatar: str
    level: int
    experience: int
    is_alive: bool
    conditions: list[str]
    location: str | None = None
    stats: list[StatOut] = Field(default_factory=list)
    abilities: list[str] = Field(default_factory=list)
    inventory: list[InventoryEntryOut] = Field(default_factory=list)


class CharacterCreateRequest(Schema):
    name: str = Field(default="", max_length=80)
    race: str = Field(default="", max_length=60)
    char_class: str = Field(default="", max_length=60, alias="class")
    background: str = Field(default="", max_length=2000)
    avatar: str = Field(default="", max_length=80)
    randomize: bool = False


class SkillAllocation(Schema):
    name: str = Field(min_length=1, max_length=60)
    points: int = Field(ge=0, le=100)


class CharacterSkillsUpdateRequest(Schema):
    """Frei benannte Zusatzfaehigkeiten, die neben den vier Grundattributen
    als Wuerfel-Attribut waehlbar sind. Ersetzt bei jedem Aufruf die
    komplette bisherige Liste (kein Zusammenfuehren)."""

    skills: list[SkillAllocation] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _check_budget(self) -> CharacterSkillsUpdateRequest:
        total = sum(entry.points for entry in self.skills)
        if total > 100:
            raise ValueError("Insgesamt duerfen nicht mehr als 100 Punkte vergeben werden.")
        return self


# --- Runden und Handlungen ---------------------------------------------


class SuggestionOut(Schema):
    kind: str
    label: str
    hint: str = ""


class ActionOut(Schema):
    id: uuid.UUID
    player_id: uuid.UUID
    character_id: uuid.UUID | None
    kind: str
    text: str
    status: str
    rejection_reason: str | None = None
    outcome: dict[str, Any] = Field(default_factory=dict)


class ActionSubmitRequest(Schema):
    kind: str = "custom"
    text: str = Field(min_length=1, max_length=1000)
    target_ref: str | None = Field(default=None, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    stat: str | None = Field(default=None, max_length=60)
    """Vom Spieler selbst gewaehltes Attribut oder frei benannter Skill,
    gegen den diese Handlung gewuerfelt werden soll."""
    group_event: bool = False
    """Markiert diese Handlung als Gruppenereignis -- andere aktive Spieler
    am selben Ort werden gefragt, ob sie mitmachen wollen (siehe
    GroupProposalOut)."""


class DiceRollOut(Schema):
    id: uuid.UUID
    turn_id: uuid.UUID | None = None
    character_id: uuid.UUID | None
    notation: str
    rolls: list[int]
    modifier: int
    total: int
    difficulty: int | None
    success: bool | None
    degree: str
    reason: str
    created_at: datetime


class NarrationOut(Schema):
    id: uuid.UUID
    turn_id: uuid.UUID | None = None
    kind: str
    scene_title: str
    text: str
    audience_player_id: uuid.UUID | None = None
    created_at: datetime


class TurnOut(Schema):
    id: uuid.UUID
    number: int
    status: str
    scene_title: str
    location_id: uuid.UUID | None = None
    location_name: str | None = None
    submitted_player_ids: list[uuid.UUID] = Field(default_factory=list)
    my_suggestions: list[SuggestionOut] = Field(default_factory=list)


class PendingRevealOut(Schema):
    """Aufdeckungs-Fortschritt des letzten abgeschlossenen Zugs am eigenen
    Ort. Solange revealed False ist, haelt das Frontend Wuerfelergebnisse,
    Erzaehlung und Ton dieses Zugs im Verlauf zurueck -- das Wuerfel-Popup
    selbst zeigt die eigenen Ergebnisse trotzdem sofort."""

    turn_id: uuid.UUID
    revealed: bool
    acknowledged_player_ids: list[uuid.UUID] = Field(default_factory=list)
    expected_player_ids: list[uuid.UUID] = Field(default_factory=list)


class GroupProposalOut(Schema):
    """Ein als Gruppenereignis markierter Vorschlag, auf den die aufrufende
    Person noch nicht geantwortet hat. Verschwindet aus dem eigenen Zustand,
    sobald sie geantwortet hat -- unabhaengig davon, ob sie zugestimmt hat."""

    id: uuid.UUID
    initiator_name: str
    kind: str
    text: str


class ActiveLocationTurnOut(Schema):
    """Ein gleichzeitig laufender Zug an einem Ort -- nur fuer die Spielleitung."""

    turn_id: uuid.UUID
    turn_number: int
    status: str
    location_id: uuid.UUID | None = None
    location_name: str | None = None
    character_names: list[str] = Field(default_factory=list)
    submitted_count: int = 0
    participant_count: int = 0


class EventOut(Schema):
    id: uuid.UUID
    seq: int
    type: str
    summary: str
    turn_number: int
    visibility: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class QuestOut(Schema):
    id: uuid.UUID
    title: str
    description: str
    status: str
    is_main: bool


class LocationOut(Schema):
    id: uuid.UUID
    name: str
    description: str
    is_discovered: bool


class EntityOut(Schema):
    id: uuid.UUID
    name: str
    kind: str
    description: str
    is_alive: bool


class FactOut(Schema):
    key: str
    statement: str
    visibility: str
    turn_number: int


class AudioOut(Schema):
    id: uuid.UUID
    status: str
    provider: str
    target: str
    url: str | None
    text: str
    voice: str
    mime_type: str | None = None
    narration_id: uuid.UUID | None = None
    error: str | None = None


class SummaryOut(Schema):
    id: uuid.UUID
    text: str
    highlights: list[str]
    turn_number: int
    created_at: datetime


class GameStateOut(Schema):
    """Vollstaendiger, spielerspezifisch gefilterter Zustand."""

    game: GameOut
    players: list[PlayerOut]
    characters: list[CharacterOut]
    me: PlayerOut
    my_character: CharacterOut | None
    turn: TurnOut | None
    pending_reveal: PendingRevealOut | None = None
    pending_group_proposal: GroupProposalOut | None = None
    narrations: list[NarrationOut]
    dice_rolls: list[DiceRollOut]
    quests: list[QuestOut]
    locations: list[LocationOut]
    entities: list[EntityOut]
    facts: list[FactOut]
    knowledge: list[str]
    events: list[EventOut]
    audio: AudioOut | None
    is_host: bool
    active_location_turns: list[ActiveLocationTurnOut] | None = None
    """Uebersicht ueber alle gleichzeitig laufenden Orte -- nur fuer die
    Spielleitung befuellt, sonst None."""


# --- Administration -----------------------------------------------------


class AdminKickRequest(Schema):
    player_id: uuid.UUID


class OkResponse(Schema):
    ok: bool = True
    message: str = ""


class InterventionRespondRequest(Schema):
    accepted: bool


class GroupProposalRespondRequest(Schema):
    accepted: bool


# --- Installationsweite Einstellungen ------------------------------------


class SettingsStatusOut(Schema):
    enabled: bool


class SettingsLoginRequest(Schema):
    password: str = Field(min_length=1, max_length=200)


class SettingsLoginOut(Schema):
    token: str
    expires_at: datetime


VoiceSource = Literal["openai", "custom"]


class RuntimeSettingsOut(Schema):
    tts_voice: str
    tts_speed: float
    tts_provider: str
    voice_source: VoiceSource
    known_voices: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class RuntimeSettingsUpdateRequest(Schema):
    tts_voice: str | None = Field(default=None, max_length=60)
    tts_speed: float | None = Field(default=None, ge=0.25, le=4.0)
