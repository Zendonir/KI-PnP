"""WebSocket fuer die Echtzeit-Synchronisation.

Alle Spieler einer Runde abonnieren denselben Kanal. Private Nachrichten
werden serverseitig gefiltert und erreichen nur den vorgesehenen Spieler.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.container import Container
from app.core.errors import AuthError, DomainError
from app.core.security import decode_token
from app.db.models import Player
from app.services.events import EventRecorder
from app.services.game_service import GameService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

_HEARTBEAT_SECONDS = 25.0


@router.websocket("/ws/games/{game_id}")
async def game_socket(
    websocket: WebSocket, game_id: uuid.UUID, token: str = Query(...)
) -> None:
    """Liefert Ereignisse, Narrationen und Statuswechsel in Echtzeit."""
    container: Container = websocket.app.state.container
    settings = container.settings

    try:
        payload = decode_token(settings, token)
        if payload.game_id != game_id:
            raise AuthError("Token gehoert zu einer anderen Runde.")
    except DomainError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    subscription = await container.hub.subscribe(game_id, payload.player_id)

    async with container.database.session() as session:
        games = GameService(session, settings, container.hub, EventRecorder(session))
        player: Player | None = None
        try:
            game = await games.get(game_id)
            player = await games.get_player(game, payload.player_id)
            await games.set_connection(player, True)
            await container.hub.publish(
                game_id, "presence", {"player_id": str(player.id), "connected": True}
            )
            await websocket.send_json({"type": "ready", "payload": {"game_id": str(game_id)}})
            await _pump(websocket, subscription)
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001 - Verbindung darf den Server nie stoppen
            logger.info("WebSocket beendet (game=%s): %s", game_id, exc)
        finally:
            await container.hub.unsubscribe(subscription)
            if player is not None:
                with contextlib.suppress(Exception):
                    await games.set_connection(player, False)
                    await container.hub.publish(
                        game_id,
                        "presence",
                        {"player_id": str(player.id), "connected": False},
                    )


async def _pump(websocket: WebSocket, subscription) -> None:
    """Sendet Nachrichten und haelt die Verbindung offen."""
    reader = asyncio.create_task(_drain_client(websocket))
    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    subscription.queue.get(), timeout=_HEARTBEAT_SECONDS
                )
            except TimeoutError:
                await websocket.send_json({"type": "ping", "payload": {}})
                continue
            if reader.done():
                break
            await websocket.send_json(message)
    finally:
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reader


async def _drain_client(websocket: WebSocket) -> None:
    """Liest eingehende Nachrichten (nur Keep-Alive) und erkennt Verbindungsabbruch."""
    while True:
        await websocket.receive_text()
