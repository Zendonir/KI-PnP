"""Installationsweite Laufzeit-Einstellungen (Settings-Menue).

Anders als die uebrige Konfiguration (app.core.config.Settings, einmal aus
Umgebungsvariablen gelesen und danach eingefroren) werden diese Werte bei
jedem Zugriff frisch aus der Datenbank gelesen -- das ist der einzige Weg,
auf dem eine Aenderung sowohl das Backend als auch den separaten
Medien-Worker erreicht, ohne einen Neustart zu verlangen.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import RuntimeSettings

_SINGLETON_ID = 1


@dataclass(frozen=True, slots=True)
class EffectiveTTS:
    """Die gerade wirksamen Werte fuer Stimme und Geschwindigkeit."""

    voice: str
    speed: float | None
    """None => im Sprachauftrag weglassen (Vorgabe des Anbieters, bei OpenAI 1.0)."""


async def get_runtime_settings(session: AsyncSession) -> RuntimeSettings | None:
    """Die eine Einstellungszeile, falls sie schon existiert."""
    return await session.get(RuntimeSettings, _SINGLETON_ID)


async def get_effective_tts(session: AsyncSession, settings: Settings) -> EffectiveTTS:
    """Stimme/Geschwindigkeit, wie sie fuer die naechste Sprachausgabe gelten.

    Ohne bestehende Zeile oder mit leerem Feld gilt die Umgebungsvariable
    bzw. die Anbieter-Vorgabe -- eine frische Installation verhaelt sich
    damit unveraendert gegenueber dem Stand vor dem Settings-Menue.
    """
    row = await get_runtime_settings(session)
    voice = (row.tts_voice if row and row.tts_voice else None) or settings.tts_voice
    speed = row.tts_speed if row and row.tts_speed is not None else None
    return EffectiveTTS(voice=voice, speed=speed)


async def update_runtime_settings(
    session: AsyncSession, *, voice: str | None, speed: float | None
) -> RuntimeSettings:
    """Setzt die installationsweiten Werte. Legt die Zeile beim ersten Mal an."""
    row = await get_runtime_settings(session)
    if row is None:
        row = RuntimeSettings(id=_SINGLETON_ID)
        session.add(row)
    row.tts_voice = voice
    row.tts_speed = speed
    await session.flush()
    return row
