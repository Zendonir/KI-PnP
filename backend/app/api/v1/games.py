"""Endpunkte fuer Spielrunden, Lobby und Moderation."""

from __future__ import annotations

import io
import uuid

import qrcode
import qrcode.image.svg
import sqlalchemy as sa
from fastapi import APIRouter, Response, status

from app.api.deps import (
    CharacterServiceDep,
    GameServiceDep,
    HostDep,
    PrincipalDep,
    SessionDep,
    SettingsDep,
    TurnServiceDep,
)
from app.core.errors import ConflictError, NotFoundError
from app.db.models import Character, SceneSummary
from app.schemas.api import (
    CharacterCreateRequest,
    CharacterOut,
    GameCreateRequest,
    GameOut,
    GameStateOut,
    JoinRequest,
    OkResponse,
    PlayerOut,
    SessionOut,
    SummaryOut,
)
from app.services.views import character_to_out

router = APIRouter(prefix="/games", tags=["games"])


def _session_payload(settings, game, player, token: str) -> SessionOut:
    """Baut die Antwort mit Beitrittslink und QR-Adresse."""
    base = settings.public_base_url.rstrip("/")
    return SessionOut(
        game=GameOut.model_validate(game),
        player=PlayerOut.model_validate(player),
        token=token,
        join_url=f"{base}/join/{game.code}",
        qr_url=f"{base}/api/v1/games/code/{game.code}/qr.svg",
    )


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_game(
    request: GameCreateRequest, games: GameServiceDep, settings: SettingsDep
) -> SessionOut:
    """Erstellt eine Runde; der Ersteller wird Spielleiter."""
    game, host, token = await games.create_game(request)
    return _session_payload(settings, game, host, token)


@router.post("/code/{code}/join", response_model=SessionOut)
async def join_game(
    code: str, request: JoinRequest, games: GameServiceDep, settings: SettingsDep
) -> SessionOut:
    """Tritt einer Runde ueber den Beitrittscode bei."""
    game, player, token = await games.join_game(code, request.player_name)
    return _session_payload(settings, game, player, token)


@router.get("/code/{code}", response_model=GameOut)
async def peek_game(code: str, games: GameServiceDep) -> GameOut:
    """Oeffentliche Kurzinfo zu einer Runde (fuer die Beitrittsseite)."""
    game = await games.get_by_code(code)
    return GameOut.model_validate(game)


@router.get("/code/{code}/qr.svg", response_class=Response)
async def qr_code(code: str, games: GameServiceDep, settings: SettingsDep) -> Response:
    """Liefert den Beitritts-QR-Code als SVG."""
    game = await games.get_by_code(code)
    url = f"{settings.public_base_url.rstrip('/')}/join/{game.code}"
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/{game_id}/state", response_model=GameStateOut)
async def get_state(
    principal: PrincipalDep, games: GameServiceDep, turns: TurnServiceDep
) -> GameStateOut:
    """Vollstaendiger, fuer diesen Spieler gefilterter Spielzustand.

    Findet sich am Ort des eigenen Charakters noch kein laufender Zug --
    etwa direkt nachdem die Gruppe sich getrennt hat --, wird er hier schon
    angelegt. Sonst saehe der Spieler dort keine Handlungsmoeglichkeit, bis
    zufaellig jemand anders zuerst etwas einreicht.
    """
    turn = await games.current_turn_for_player(principal.game, principal.player)
    if turn is None:
        character = await games.character_of(principal.player)
        if character is not None:
            await turns.ensure_turn_for_character(principal.game, character)
    return await games.build_state(principal.game, principal.player)


@router.post("/{game_id}/characters", response_model=CharacterOut, status_code=201)
async def create_character(
    request: CharacterCreateRequest,
    principal: PrincipalDep,
    characters: CharacterServiceDep,
    session: SessionDep,
) -> CharacterOut:
    """Erstellt den Charakter des aufrufenden Spielers."""
    character = await characters.create(principal.game, principal.player, request)
    await session.commit()
    return await character_to_out(session, character)


@router.post("/{game_id}/start", response_model=GameStateOut)
async def start_game(
    host: HostDep, games: GameServiceDep, turns: TurnServiceDep
) -> GameStateOut:
    """Startet die Runde: die KI erzeugt Welt, Szene und erste Vorschlaege."""
    game = host.game
    if game.status != "lobby":
        raise ConflictError("Die Runde wurde bereits gestartet.")
    characters = await games.character_of(host.player)
    if characters is None:
        raise ConflictError("Der Spielleiter braucht ebenfalls einen Charakter.")
    await turns.bootstrap_world(game)
    return await games.build_state(game, host.player)


@router.post("/{game_id}/pause", response_model=GameOut)
async def pause_game(host: HostDep, games: GameServiceDep) -> GameOut:
    """Pausiert die Runde."""
    return GameOut.model_validate(await games.set_status(host.game, "paused"))


@router.post("/{game_id}/resume", response_model=GameOut)
async def resume_game(host: HostDep, games: GameServiceDep) -> GameOut:
    """Setzt eine pausierte Runde fort."""
    return GameOut.model_validate(await games.set_status(host.game, "active"))


@router.post("/{game_id}/finish", response_model=GameOut)
async def finish_game(host: HostDep, games: GameServiceDep) -> GameOut:
    """Beendet die Runde. Das Protokoll bleibt vollstaendig erhalten."""
    return GameOut.model_validate(await games.set_status(host.game, "finished"))


@router.delete("/{game_id}/players/{player_id}", response_model=OkResponse)
async def kick_player(
    player_id: uuid.UUID, host: HostDep, games: GameServiceDep
) -> OkResponse:
    """Entfernt einen Spieler aus der Runde."""
    await games.remove_player(host.game, player_id)
    return OkResponse(message="Spieler entfernt.")


@router.post("/{game_id}/summary", response_model=SummaryOut)
async def create_summary(host: HostDep, turns: TurnServiceDep) -> SummaryOut:
    """Erzeugt sofort eine Zusammenfassung des bisherigen Verlaufs."""
    summary = await turns.create_summary(host.game)
    return SummaryOut.model_validate(summary)


@router.get("/{game_id}/summaries", response_model=list[SummaryOut])
async def list_summaries(principal: PrincipalDep, session: SessionDep) -> list[SummaryOut]:
    """Alle bisherigen Zusammenfassungen (Langzeitgedaechtnis)."""
    stmt = (
        sa.select(SceneSummary)
        .where(SceneSummary.game_id == principal.game.id)
        .order_by(SceneSummary.to_seq.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [SummaryOut.model_validate(row) for row in rows]


@router.get("/{game_id}/characters", response_model=list[CharacterOut])
async def list_characters(
    principal: PrincipalDep, session: SessionDep
) -> list[CharacterOut]:
    """Alle Charaktere der Runde."""
    stmt = sa.select(Character).where(Character.game_id == principal.game.id)
    rows = (await session.execute(stmt)).scalars().all()
    return [await character_to_out(session, row) for row in rows]


@router.get("/{game_id}", response_model=GameOut)
async def get_game(principal: PrincipalDep) -> GameOut:
    """Stammdaten der Runde."""
    if principal.game is None:  # pragma: no cover - defensiv
        raise NotFoundError("Spielrunde nicht gefunden.")
    return GameOut.model_validate(principal.game)
