"""Endpunkte fuer Handlungen und Rundenaufloesung."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Query

from app.api.deps import (
    GameServiceDep,
    HostDep,
    HubDep,
    PrincipalDep,
    SessionDep,
    TurnServiceDep,
)
from app.core.errors import ConflictError, NotFoundError
from app.db.models import AudioJob, Event, Narration
from app.schemas.api import (
    ActionOut,
    ActionSubmitRequest,
    EventOut,
    GameStateOut,
    NarrationOut,
    OkResponse,
    TurnOut,
)

router = APIRouter(prefix="/games/{game_id}", tags=["turns"])


@router.post("/actions", response_model=ActionOut, status_code=201)
async def submit_action(
    request: ActionSubmitRequest,
    principal: PrincipalDep,
    games: GameServiceDep,
    turns: TurnServiceDep,
) -> ActionOut:
    """Reicht die Handlung des aufrufenden Spielers fuer den aktuellen Zug ein.

    Haben alle handlungsfaehigen Spieler eingereicht, loest das Backend den
    Zug automatisch auf.
    """
    turn = await games.current_turn(principal.game)
    if turn is None:
        raise NotFoundError("Es laeuft derzeit kein Zug.")
    action = await turns.submit_action(principal.game, turn, principal.player, request)

    if await turns.everyone_submitted(principal.game, turn):
        await turns.resolve_turn(principal.game, turn)
    return ActionOut.model_validate(action)


@router.post("/resolve", response_model=TurnOut)
async def resolve_turn(host: HostDep, games: GameServiceDep, turns: TurnServiceDep) -> TurnOut:
    """Loest den laufenden Zug sofort auf (Spielleiter-Funktion)."""
    turn = await games.current_turn(host.game)
    if turn is None:
        raise NotFoundError("Es laeuft derzeit kein Zug.")
    if turn.status == "completed":
        raise ConflictError("Dieser Zug ist bereits abgeschlossen.")
    next_turn = await turns.resolve_turn(host.game, turn)
    return TurnOut(
        id=next_turn.id,
        number=next_turn.number,
        status=next_turn.status,
        scene_title=next_turn.scene_title,
    )


@router.post("/renarrate", response_model=TurnOut)
async def renarrate(host: HostDep, games: GameServiceDep, turns: TurnServiceDep) -> TurnOut:
    """Laesst die KI den aktuellen Zug neu erzaehlen.

    Nuetzlich, wenn die KI ausgefallen ist oder das Ergebnis nicht passt. Die
    bereits gewuerfelten Ergebnisse bleiben unveraendert.
    """
    turn = await games.current_turn(host.game)
    if turn is None:
        raise NotFoundError("Es laeuft derzeit kein Zug.")
    next_turn = await turns.renarrate(host.game, turn)
    return TurnOut(
        id=next_turn.id,
        number=next_turn.number,
        status=next_turn.status,
        scene_title=next_turn.scene_title,
    )


@router.post("/skip", response_model=GameStateOut)
async def skip_scene(host: HostDep, games: GameServiceDep, turns: TurnServiceDep) -> GameStateOut:
    """Ueberspringt die Szene: der Zug wird ohne Handlungen fortgeschrieben."""
    turn = await games.current_turn(host.game)
    if turn is None:
        raise NotFoundError("Es laeuft derzeit kein Zug.")
    await turns.resolve_turn(host.game, turn)
    return await games.build_state(host.game, host.player)


@router.get("/events", response_model=list[EventOut])
async def list_events(
    principal: PrincipalDep,
    session: SessionDep,
    since: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[EventOut]:
    """Ereignisprotokoll ab einer Sequenznummer (Spielverlauf)."""
    stmt = (
        sa.select(Event)
        .where(Event.game_id == principal.game.id, Event.seq > since)
        .order_by(Event.seq.asc())
        .limit(limit)
    )
    events = (await session.execute(stmt)).scalars().all()
    return [
        EventOut.model_validate(event)
        for event in events
        if event.visibility != "private" or event.audience_player_id == principal.player.id
    ]


@router.get("/narrations", response_model=list[NarrationOut])
async def list_narrations(
    principal: PrincipalDep, session: SessionDep, limit: int = Query(default=50, ge=1, le=200)
) -> list[NarrationOut]:
    """Erzaehltexte, die dieser Spieler sehen darf."""
    stmt = (
        sa.select(Narration)
        .where(
            Narration.game_id == principal.game.id,
            sa.or_(
                Narration.kind == "public",
                Narration.audience_player_id == principal.player.id,
            ),
        )
        .order_by(Narration.created_at.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [NarrationOut.model_validate(row) for row in rows]


@router.post("/audio/replay", response_model=OkResponse)
async def replay_audio(host: HostDep, session: SessionDep, hub: HubDep) -> OkResponse:
    """Fordert alle Clients auf, die letzte Sprachausgabe erneut abzuspielen."""
    stmt = (
        sa.select(AudioJob)
        .where(AudioJob.game_id == host.game.id, AudioJob.target == "browser")
        .order_by(AudioJob.created_at.desc())
        .limit(1)
    )
    job = (await session.execute(stmt)).scalars().first()
    if job is None:
        raise NotFoundError("Es liegt keine Sprachausgabe vor.")
    await hub.publish(
        host.game.id,
        "audio.replay",
        {
            "audio_id": str(job.id),
            "text": job.text,
            "voice": job.voice,
            "url": job.url,
            "provider": job.provider,
        },
    )
    return OkResponse(message="Wiedergabe angefordert.")
