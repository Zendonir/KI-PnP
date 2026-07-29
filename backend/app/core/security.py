"""JWT-basierte Authentifizierung.

Spieler authentifizieren sich nicht mit Passwoertern, sondern erhalten beim
Erstellen bzw. Beitreten einer Runde ein signiertes Token. Das Token bindet
Spieler-ID, Spiel-ID und Rolle aneinander.
"""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import Settings
from app.core.errors import AuthError

_JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """Entschluesselter Inhalt eines Spieler-Tokens."""

    player_id: UUID
    game_id: UUID
    role: str

    @property
    def is_host(self) -> bool:
        return self.role == "host"


def create_join_code(length: int = 6) -> str:
    """Erzeugt einen gut vorlesbaren Beitrittscode."""
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(length))


def create_token(settings: Settings, *, player_id: UUID, game_id: UUID, role: str) -> str:
    """Signiert ein Spieler-Token."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(player_id),
        "gid": str(game_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(settings: Settings, token: str) -> TokenPayload:
    """Prueft und entschluesselt ein Spieler-Token."""
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:  # pragma: no cover - defensiv
        raise AuthError("Token ungueltig oder abgelaufen") from exc
    try:
        return TokenPayload(
            player_id=UUID(raw["sub"]),
            game_id=UUID(raw["gid"]),
            role=str(raw["role"]),
        )
    except (KeyError, ValueError) as exc:
        raise AuthError("Token unvollstaendig") from exc


def random_id(length: int = 8) -> str:
    """Kurzer, zufaelliger technischer Bezeichner (z. B. fuer Slugs)."""
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
