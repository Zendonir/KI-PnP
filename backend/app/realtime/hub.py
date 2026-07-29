"""Echtzeit-Verteilung von Spielereignissen.

Standardmaessig prozesslokal. Ist Redis konfiguriert, werden Nachrichten
zusaetzlich ueber Pub/Sub verteilt, sodass mehrere Backend-Instanzen
dieselbe Runde bedienen koennen.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from contextlib import suppress
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

_CHANNEL = "kipnp:game:{game_id}"


class Subscription:
    """Eine Warteschlange fuer genau einen verbundenen Client."""

    def __init__(self, game_id: UUID, player_id: UUID | None, maxsize: int = 200) -> None:
        self.game_id = game_id
        self.player_id = player_id
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)

    def offer(self, message: dict[str, Any]) -> None:
        """Legt eine Nachricht ab; verwirft sie, wenn der Client nicht folgt."""
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:  # pragma: no cover - langsamer Client
            logger.warning("Client-Queue voll, Nachricht verworfen (game=%s)", self.game_id)


class EventHub:
    """Verteilt Nachrichten an alle Abonnenten einer Runde."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._subscribers: dict[UUID, set[Subscription]] = defaultdict(set)
        self._redis_url = redis_url
        self._redis: Any = None
        self._pubsub_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Startet die Redis-Anbindung, falls konfiguriert."""
        if not self._redis_url:
            return
        try:
            import redis.asyncio as redis_async

            self._redis = redis_async.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            self._pubsub_task = asyncio.create_task(self._consume())
            logger.info("Realtime-Hub nutzt Redis unter %s", self._redis_url)
        except Exception as exc:  # noqa: BLE001 - Redis ist optional
            logger.warning("Redis nicht verfuegbar (%s), nutze lokale Verteilung.", exc)
            self._redis = None

    async def stop(self) -> None:
        if self._pubsub_task is not None:
            self._pubsub_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._pubsub_task
        if self._redis is not None:
            await self._redis.aclose()

    async def subscribe(self, game_id: UUID, player_id: UUID | None) -> Subscription:
        subscription = Subscription(game_id, player_id)
        async with self._lock:
            self._subscribers[game_id].add(subscription)
        return subscription

    async def unsubscribe(self, subscription: Subscription) -> None:
        async with self._lock:
            self._subscribers[subscription.game_id].discard(subscription)
            if not self._subscribers[subscription.game_id]:
                self._subscribers.pop(subscription.game_id, None)

    async def publish(
        self,
        game_id: UUID,
        message_type: str,
        payload: dict[str, Any],
        *,
        audience_player_id: UUID | None = None,
    ) -> None:
        """Verteilt eine Nachricht.

        ``audience_player_id`` beschraenkt die Zustellung auf einen Spieler --
        so bleiben private Informationen privat.
        """
        message = {
            "type": message_type,
            "game_id": str(game_id),
            "audience_player_id": str(audience_player_id) if audience_player_id else None,
            "payload": payload,
        }
        # Mit Redis erfolgt die lokale Zustellung ueber den Pub/Sub-Konsumenten,
        # damit Nachrichten nicht doppelt ankommen.
        if self._redis is not None:
            try:
                await self._redis.publish(
                    _CHANNEL.format(game_id=game_id), json.dumps(message, default=str)
                )
                return
            except Exception as exc:  # noqa: BLE001 - Redis darf ausfallen
                logger.warning("Redis-Publish fehlgeschlagen (%s), liefere lokal aus.", exc)
        self._deliver_local(game_id, message)

    def _deliver_local(self, game_id: UUID, message: dict[str, Any]) -> None:
        audience = message.get("audience_player_id")
        for subscription in tuple(self._subscribers.get(game_id, ())):
            if audience and str(subscription.player_id) != audience:
                continue
            subscription.offer(message)

    async def _consume(self) -> None:  # pragma: no cover - benoetigt Redis
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(_CHANNEL.format(game_id="*"))
        async for raw in pubsub.listen():
            if raw.get("type") != "pmessage":
                continue
            try:
                message = json.loads(raw["data"])
                game_id = UUID(message["game_id"])
            except (KeyError, ValueError, TypeError):
                continue
            self._deliver_local(game_id, message)
