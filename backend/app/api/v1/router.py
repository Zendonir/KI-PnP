"""Buendelt alle Endpunkte der API-Version 1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import games, settings_admin, turns, ws

api_router = APIRouter()
api_router.include_router(games.router)
api_router.include_router(turns.router)
api_router.include_router(settings_admin.router)

# WebSockets liegen ausserhalb des /api/v1-Praefix-Schemas fuer REST,
# werden aber gemeinsam registriert.
ws_router = APIRouter()
ws_router.include_router(ws.router)
