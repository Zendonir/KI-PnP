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

OPERATOR_TOKEN_TTL_SECONDS = 60 * 60 * 12
"""Kuerzer als die 30 Tage eines Spieler-Tokens -- ein hoeher privilegiertes,
installationsweites Zugangsmittel. Deckt einen Abend samt Anpassung am
Folgetag ab, ohne bei jeder Sitzung neu verlangt zu werden."""


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


@dataclass(frozen=True, slots=True)
class OperatorTokenPayload:
    """Entschluesselter Inhalt eines Settings-Zugangstokens."""

    issued_at: datetime


def create_operator_token(settings: Settings) -> str:
    """Signiert ein Zugangstoken fuer das installationsweite Settings-Menue."""
    now = datetime.now(UTC)
    payload = {
        "typ": "operator",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=OPERATOR_TOKEN_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_operator_token(settings: Settings, token: str) -> OperatorTokenPayload:
    """Prueft und entschluesselt ein Settings-Zugangstoken.

    Das ``typ``-Feld trennt diese Tokenart sauber von Spieler-Token (die es
    nicht kennen) und umgekehrt, ohne dass ``decode_token`` etwas davon
    wissen muss.
    """
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise AuthError("Token ungueltig oder abgelaufen") from exc
    if raw.get("typ") != "operator":
        raise AuthError("Falscher Token-Typ")
    try:
        return OperatorTokenPayload(issued_at=datetime.fromtimestamp(raw["iat"], UTC))
    except (KeyError, ValueError) as exc:
        raise AuthError("Token unvollstaendig") from exc


def random_id(length: int = 8) -> str:
    """Kurzer, zufaelliger technischer Bezeichner (z. B. fuer Slugs)."""
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
