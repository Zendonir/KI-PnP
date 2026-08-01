"""FastAPI-Abhaengigkeiten."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import AuthError, PermissionError_
from app.core.security import (
    OperatorTokenPayload,
    TokenPayload,
    decode_operator_token,
    decode_token,
)
from app.db.models import Game, Player
from app.realtime.hub import EventHub
from app.services.character_service import CharacterService
from app.services.events import EventRecorder
from app.services.game_service import GameService
from app.services.turn_service import TurnService


def get_container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


ContainerDep = Annotated[Container, Depends(get_container)]


def get_settings_dep(container: ContainerDep) -> Settings:
    return container.settings


def get_hub(container: ContainerDep) -> EventHub:
    return container.hub


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.database.session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
HubDep = Annotated[EventHub, Depends(get_hub)]


def get_recorder(session: SessionDep, hub: HubDep) -> EventRecorder:
    return EventRecorder(session, hub)


RecorderDep = Annotated[EventRecorder, Depends(get_recorder)]


def get_game_service(
    session: SessionDep,
    settings: SettingsDep,
    hub: HubDep,
    recorder: RecorderDep,
    container: ContainerDep,
) -> GameService:
    return GameService(session, settings, hub, recorder, container.llm)


def get_turn_service(
    session: SessionDep,
    settings: SettingsDep,
    hub: HubDep,
    recorder: RecorderDep,
    container: ContainerDep,
) -> TurnService:
    return TurnService(session, settings, container.llm, container.tts, hub, recorder)


def get_character_service(
    session: SessionDep, settings: SettingsDep, recorder: RecorderDep, container: ContainerDep
) -> CharacterService:
    return CharacterService(session, settings, container.llm, recorder)


GameServiceDep = Annotated[GameService, Depends(get_game_service)]
TurnServiceDep = Annotated[TurnService, Depends(get_turn_service)]
CharacterServiceDep = Annotated[CharacterService, Depends(get_character_service)]


def parse_bearer(authorization: str | None) -> str:
    """Extrahiert das Token aus dem Authorization-Header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Kein Zugangstoken uebermittelt.")
    return authorization.split(" ", 1)[1].strip()


@dataclass(slots=True)
class Principal:
    """Der authentifizierte Spieler samt Runde."""

    game: Game
    player: Player
    token: TokenPayload

    @property
    def is_host(self) -> bool:
        return self.player.role == "host"


async def get_principal(
    game_id: Annotated[uuid.UUID, Path()],
    games: GameServiceDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """Prueft das Token gegen die angefragte Runde."""
    payload = decode_token(settings, parse_bearer(authorization))
    if payload.game_id != game_id:
        raise PermissionError_("Das Token gehoert zu einer anderen Runde.")
    game = await games.get(game_id)
    player = await games.get_player(game, payload.player_id)
    if not player.is_active:
        raise PermissionError_("Dieser Spieler wurde aus der Runde entfernt.")
    return Principal(game=game, player=player, token=payload)


PrincipalDep = Annotated[Principal, Depends(get_principal)]


async def require_host(principal: PrincipalDep) -> Principal:
    """Beschraenkt einen Endpunkt auf den Spielleiter."""
    if not principal.is_host:
        raise PermissionError_("Diese Aktion ist dem Spielleiter vorbehalten.")
    return principal


HostDep = Annotated[Principal, Depends(require_host)]


@dataclass(slots=True)
class OperatorPrincipal:
    """Der authentifizierte Zugang zum installationsweiten Settings-Menue."""

    token: OperatorTokenPayload


async def get_operator_principal(
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> OperatorPrincipal:
    """Prueft das Settings-Zugangstoken. Unabhaengig von Spieler-Token."""
    return OperatorPrincipal(token=decode_operator_token(settings, parse_bearer(authorization)))


OperatorDep = Annotated[OperatorPrincipal, Depends(get_operator_principal)]
