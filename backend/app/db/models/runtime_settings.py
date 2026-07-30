"""Laufzeit-Einstellungen fuer die gesamte Installation.

Anders als GameSettings (pro Runde) gilt das hier fuer den ganzen Betrieb --
zum Beispiel die aktive TTS-Stimme. Backend-API und Medien-Worker sind
getrennte Prozesse; nur die Datenbank kann eine Aenderung beiden sichtbar
machen, ohne dass ein Container neu gestartet werden muss.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class RuntimeSettings(Base):
    """Genau eine Zeile (id=1), die installationsweite Einstellungen haelt.

    Ein fehlender Wert (NULL) bedeutet "wie in der Umgebungsvariable
    vorgegeben", nicht "leer" -- so bleibt eine frische Installation ohne
    jede Aenderung im Settings-Menue unveraendert gegenueber heute.
    """

    __tablename__ = "runtime_settings"
    __table_args__ = (sa.CheckConstraint("id = 1", name="ck_runtime_settings_singleton"),)

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, default=1)
    tts_voice: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    tts_speed: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
