"""Kurzfristige Eingriffsangebote (Quick-Time-Event) fuer Mitspieler.

Im Prozessspeicher, nicht in der Datenbank -- wie die Anmeldesperre im
Settings-Menue (app/api/v1/settings_admin.py) reicht das fuer einen
einzelnen Backend-Container; eine verteilte Loesung waere hier
ueberdimensioniert. Ein Angebot lebt hoechstens ein paar Sekunden, danach
wird der Eintrag ohnehin entfernt.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

_WAITERS: dict[uuid.UUID, _Waiter] = {}


@dataclass(slots=True)
class _Waiter:
    player_id: uuid.UUID
    event: asyncio.Event = field(default_factory=asyncio.Event)
    accepted: bool = False


def create_waiter(player_id: uuid.UUID) -> uuid.UUID:
    """Legt ein neues Angebot an und liefert dessen Kennung."""
    intervention_id = uuid.uuid4()
    _WAITERS[intervention_id] = _Waiter(player_id=player_id)
    return intervention_id


def respond(intervention_id: uuid.UUID, player_id: uuid.UUID, *, accepted: bool) -> bool:
    """Traegt die Antwort ein. False, wenn das Angebot unbekannt/fremd ist."""
    waiter = _WAITERS.get(intervention_id)
    if waiter is None or waiter.player_id != player_id:
        return False
    waiter.accepted = accepted
    waiter.event.set()
    return True


async def wait_for_response(intervention_id: uuid.UUID, *, timeout: float) -> bool:
    """Wartet bis zur Antwort oder zum Ablauf des Zeitfensters.

    Liefert True nur, wenn rechtzeitig mit ``accepted=True`` geantwortet
    wurde. Entfernt den Eintrag in jedem Fall -- ein abgelaufenes oder
    beantwortetes Angebot gilt danach als erledigt.
    """
    waiter = _WAITERS.get(intervention_id)
    if waiter is None:
        return False
    try:
        await asyncio.wait_for(waiter.event.wait(), timeout=timeout)
    except TimeoutError:
        pass
    finally:
        _WAITERS.pop(intervention_id, None)
    return waiter.accepted
