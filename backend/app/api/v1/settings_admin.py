"""Installationsweites, passwortgeschuetztes Einstellungen-Menue.

Unabhaengig von Spieler-/Spielleiter-Token: ein einzelnes, geteiltes
Kennwort (``SETTINGS_PASSWORD``) sichert den Zugang zu Werten, die fuer die
ganze Installation gelten (aktuell: TTS-Stimme und -Geschwindigkeit).
"""

from __future__ import annotations

import asyncio
import hmac
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request

from app.api.deps import OperatorDep, SessionDep, SettingsDep
from app.core.errors import AuthError, RateLimitedError
from app.core.security import OPERATOR_TOKEN_TTL_SECONDS, create_operator_token
from app.schemas.api import (
    RuntimeSettingsOut,
    RuntimeSettingsUpdateRequest,
    SettingsLoginOut,
    SettingsLoginRequest,
    SettingsStatusOut,
)
from app.services.runtime_settings import (
    get_effective_tts,
    get_runtime_settings,
    update_runtime_settings,
)
from app.tts.providers import KNOWN_OPENAI_VOICES, _is_openai_host

router = APIRouter(prefix="/settings", tags=["settings"])

_LOGIN_ATTEMPTS: dict[str, tuple[int, float]] = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300
_LOGIN_DELAY_SECONDS = 0.3


def _client_key(request: Request) -> str:
    # Setzt voraus, dass uvicorn mit --proxy-headers laeuft und der
    # vorgelagerte Reverse-Proxy X-Forwarded-For weiterreicht (bei diesem
    # Projekt der Fall) -- sonst spiegelt request.client.host nur den Proxy.
    return request.client.host if request.client else "unknown"


def _check_lockout(key: str) -> None:
    attempt = _LOGIN_ATTEMPTS.get(key)
    if attempt is None:
        return
    count, locked_until = attempt
    if count >= _MAX_ATTEMPTS and time.monotonic() < locked_until:
        raise RateLimitedError("Zu viele Fehlversuche. Bitte spaeter erneut versuchen.")


def _register_failure(key: str) -> None:
    count, _ = _LOGIN_ATTEMPTS.get(key, (0, 0.0))
    count += 1
    locked_until = time.monotonic() + _LOCKOUT_SECONDS if count >= _MAX_ATTEMPTS else 0.0
    _LOGIN_ATTEMPTS[key] = (count, locked_until)


def _register_success(key: str) -> None:
    _LOGIN_ATTEMPTS.pop(key, None)


@router.get("/status", response_model=SettingsStatusOut)
async def get_status(settings: SettingsDep) -> SettingsStatusOut:
    """Oeffentlich: sagt dem Frontend, ob ueberhaupt ein Zugang existiert."""
    return SettingsStatusOut(enabled=bool(settings.settings_password))


@router.post("/login", response_model=SettingsLoginOut)
async def login(
    body: SettingsLoginRequest, request: Request, settings: SettingsDep
) -> SettingsLoginOut:
    """Meldet sich mit dem installationsweiten Kennwort an."""
    key = _client_key(request)
    _check_lockout(key)
    await asyncio.sleep(_LOGIN_DELAY_SECONDS)

    if not settings.settings_password:
        raise AuthError("Der Einstellungsbereich ist auf diesem Server nicht aktiviert.")

    if not hmac.compare_digest(body.password.encode(), settings.settings_password.encode()):
        _register_failure(key)
        raise AuthError("Falsches Kennwort.")

    _register_success(key)
    token = create_operator_token(settings)
    expires_at = datetime.now(UTC) + timedelta(seconds=OPERATOR_TOKEN_TTL_SECONDS)
    return SettingsLoginOut(token=token, expires_at=expires_at)


@router.get("", response_model=RuntimeSettingsOut)
async def get_runtime(
    _operator: OperatorDep, session: SessionDep, settings: SettingsDep
) -> RuntimeSettingsOut:
    """Aktuell wirksame Werte."""
    effective = await get_effective_tts(session, settings)
    row = await get_runtime_settings(session)
    return RuntimeSettingsOut(
        tts_voice=effective.voice,
        tts_speed=effective.speed if effective.speed is not None else 1.0,
        tts_provider=settings.tts_provider,
        voice_source="openai" if _is_openai_host(settings.tts_base_url) else "custom",
        known_voices=list(KNOWN_OPENAI_VOICES),
        updated_at=row.updated_at if row else None,
    )


@router.put("", response_model=RuntimeSettingsOut)
async def update_runtime(
    body: RuntimeSettingsUpdateRequest,
    _operator: OperatorDep,
    session: SessionDep,
    settings: SettingsDep,
) -> RuntimeSettingsOut:
    """Setzt Stimme/Geschwindigkeit fuer die ganze Installation."""
    row = await update_runtime_settings(session, voice=body.tts_voice, speed=body.tts_speed)
    await session.commit()
    effective = await get_effective_tts(session, settings)
    return RuntimeSettingsOut(
        tts_voice=effective.voice,
        tts_speed=effective.speed if effective.speed is not None else 1.0,
        tts_provider=settings.tts_provider,
        voice_source="openai" if _is_openai_host(settings.tts_base_url) else "custom",
        known_voices=list(KNOWN_OPENAI_VOICES),
        updated_at=row.updated_at,
    )
