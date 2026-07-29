"""Vertrag zwischen Backend und KI.

Die KI liefert ausschliesslich JSON in einer dieser Formen. Aenderungs-
vorschlaege werden bewusst als rohe Objekte entgegengenommen und erst im
Backend gegen ``app.domain.changes`` validiert -- ungueltige Vorschlaege
werden verworfen und protokolliert, statt die gesamte Antwort zu entwerten.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SuggestedAction(BaseModel):
    """Ein Handlungsvorschlag fuer einen bestimmten Charakter."""

    model_config = ConfigDict(extra="ignore")

    kind: str = "custom"
    label: str = Field(max_length=120)
    hint: str = Field(default="", max_length=300)


class PrivateMessage(BaseModel):
    """Information, die nur ein einzelner Charakter erhaelt."""

    model_config = ConfigDict(extra="ignore")

    character: str
    text: str


class NarrationResponse(BaseModel):
    """Standardantwort des KI-Spielleiters fuer eine Runde."""

    model_config = ConfigDict(extra="ignore")

    scene_title: str = Field(default="", max_length=200)
    narration: str = ""
    public_events: list[str] = Field(default_factory=list)
    private_messages: list[PrivateMessage] = Field(default_factory=list)
    suggestions: dict[str, list[SuggestedAction]] = Field(default_factory=dict)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    audio_hint: str = Field(default="", max_length=200)


class WorldResponse(NarrationResponse):
    """Antwort fuer die Weltgenerierung zu Spielbeginn."""

    world_summary: str = ""


class SummaryResponse(BaseModel):
    """Verdichtete Zusammenfassung als Langzeitgedaechtnis."""

    model_config = ConfigDict(extra="ignore")

    text: str = ""
    highlights: list[str] = Field(default_factory=list)


class CharacterDraft(BaseModel):
    """Von der KI generierter Charaktervorschlag."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(max_length=80)
    race: str = ""
    char_class: str = Field(default="", alias="class")
    background: str = ""
    avatar: str = ""
    abilities: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
