"""Endpunkte fuer Handlungen und Rundenaufloesung."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Query, Response

from app.api.deps import (
    GameServiceDep,
    HostDep,
    HubDep,
    Principal,
    PrincipalDep,
    SessionDep,
    TurnServiceDep,
)
from app.core.errors import ConflictError, NotFoundError
from app.db.models import AudioJob, Event, Narration, Turn
from app.schemas.api import (
    ActionOut,
    ActionSubmitRequest,
    EventOut,
    GameStateOut,
    NarrationOut,
    OkResponse,
    TurnOut,
)
from app.services.game_service import GameService

router = APIRouter(prefix="/games/{game_id}", tags=["turns"])


@router.post("/actions", response_model=ActionOut, status_code=201)
async def submit_action(
    request: ActionSubmitRequest,
    principal: PrincipalDep,
    games: GameServiceDep,
    turns: TurnServiceDep,
) -> ActionOut:
    """Reicht die Handlung des aufrufenden Spielers fuer den aktuellen Zug ein.

    Der Zug richtet sich nach dem Ort des eigenen Charakters -- bleibt die
    Gruppe zusammen, ist das fuer alle derselbe. Haben alle handlungsfaehigen
    Spieler an diesem Ort eingereicht, loest das Backend den Zug dort
    automatisch auf, unabhaengig davon, was an anderen Orten passiert.
    """
    turn = await games.current_turn_for_player(principal.game, principal.player)
    if turn is None:
        # Sollte durch _sync_location_turns eigentlich nie vorkommen -- am
        # ehesten bei einem spaeten Beitritt, dessen Charakter noch keinem
        # Zug zugeordnet wurde. Einmalig nachholen statt hart abzulehnen.
        character = await games.character_of(principal.player)
        if character is not None:
            turn = await turns.ensure_turn_for_character(principal.game, character)
    if turn is None:
        raise NotFoundError("Es laeuft derzeit kein Zug.")
    action = await turns.submit_action(principal.game, turn, principal.player, request)

    if await turns.turn_ready(principal.game, turn):
        await turns.resolve_turn(principal.game, turn)
    return ActionOut.model_validate(action)


def _turn_out(turn: Turn) -> TurnOut:
    return TurnOut(
        id=turn.id,
        number=turn.number,
        status=turn.status,
        scene_title=turn.scene_title,
        location_id=turn.location_id,
    )


async def _resolve_target_turn(
    turn_id: uuid.UUID | None,
    host: Principal,
    games: GameService,
    session: SessionDep,
) -> Turn:
    """Ermittelt den vom Aufruf gemeinten Zug.

    Mit turn_id: genau dieser Zug (muss zur Runde gehoeren). Ohne turn_id:
    der Zug am Ort der Spielleitung selbst -- ohne Aufteilung ist das
    ohnehin der einzige, bestehende Aufrufe ohne den Parameter funktionieren
    also unveraendert weiter.
    """
    if turn_id is not None:
        turn = await session.get(Turn, turn_id)
        if turn is None or turn.game_id != host.game.id:
            raise NotFoundError("Dieser Zug gehoert nicht zu dieser Runde.")
        return turn
    turn = await games.current_turn_for_player(host.game, host.player)
    if turn is None:
        raise NotFoundError("Es laeuft derzeit kein Zug.")
    return turn


@router.post("/resolve", response_model=TurnOut)
async def resolve_turn(
    host: HostDep,
    games: GameServiceDep,
    turns: TurnServiceDep,
    session: SessionDep,
    turn_id: uuid.UUID | None = None,
) -> TurnOut:
    """Loest einen laufenden Zug sofort auf (Spielleiter-Funktion).

    Ohne turn_id den Zug am eigenen Ort; mit turn_id gezielt einen von
    mehreren gleichzeitig laufenden Zuegen -- die anderen bleiben unberuehrt.
    """
    turn = await _resolve_target_turn(turn_id, host, games, session)
    if turn.status == "completed":
        raise ConflictError("Dieser Zug ist bereits abgeschlossen.")
    next_turn = await turns.resolve_turn(host.game, turn)
    return _turn_out(next_turn)


@router.post("/renarrate", response_model=TurnOut)
async def renarrate(
    host: HostDep,
    games: GameServiceDep,
    turns: TurnServiceDep,
    session: SessionDep,
    turn_id: uuid.UUID | None = None,
) -> TurnOut:
    """Laesst die KI einen Zug neu erzaehlen.

    Nuetzlich, wenn die KI ausgefallen ist oder das Ergebnis nicht passt. Die
    bereits gewuerfelten Ergebnisse bleiben unveraendert.
    """
    turn = await _resolve_target_turn(turn_id, host, games, session)
    next_turn = await turns.renarrate(host.game, turn)
    return _turn_out(next_turn)


@router.post("/skip", response_model=GameStateOut)
async def skip_scene(
    host: HostDep,
    games: GameServiceDep,
    turns: TurnServiceDep,
    session: SessionDep,
    turn_id: uuid.UUID | None = None,
) -> GameStateOut:
    """Ueberspringt eine Szene: der Zug wird ohne Handlungen fortgeschrieben."""
    turn = await _resolve_target_turn(turn_id, host, games, session)
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
    principal: PrincipalDep,
    games: GameServiceDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[NarrationOut]:
    """Erzaehltexte, die dieser Spieler sehen darf.

    Oeffentliche Narration nur vom eigenen Ort -- wie in build_state, sonst
    liesse sich hier die Erzaehlung einer unabhaengig laufenden Szene an
    einem anderen Ort mitlesen.
    """
    character = await games.character_of(principal.player)
    if character is not None and character.location_id is not None:
        same_location = Turn.location_id == character.location_id
    elif character is not None:
        same_location = Turn.location_id.is_(None)
    else:
        same_location = sa.true()

    stmt = (
        sa.select(Narration)
        .outerjoin(Turn, Turn.id == Narration.turn_id)
        .where(
            Narration.game_id == principal.game.id,
            sa.or_(
                sa.and_(Narration.kind == "public", sa.or_(Turn.id.is_(None), same_location)),
                Narration.audience_player_id == principal.player.id,
            ),
        )
        .order_by(Narration.created_at.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [NarrationOut.model_validate(row) for row in rows]


@router.get("/audio/{audio_id}", response_class=Response)
async def get_audio(
    audio_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> Response:
    """Liefert eine serverseitig erzeugte Sprachaufnahme aus.

    Der Zugang ist an die Runde gebunden: ohne gueltiges Spieler-Token gibt es
    kein Audio, und Aufnahmen anderer Runden sind nicht erreichbar.
    """
    job = await session.get(AudioJob, audio_id)
    if job is None or job.game_id != principal.game.id:
        raise NotFoundError("Sprachaufnahme nicht gefunden.")
    if not job.has_audio:
        raise NotFoundError(
            "Zu dieser Aufnahme liegen keine Audiodaten vor."
            if job.status != "pending"
            else "Die Aufnahme wird noch erzeugt."
        )
    return Response(
        content=job.data,
        media_type=job.mime_type or "audio/mpeg",
        headers={
            "Cache-Control": "private, max-age=86400",
            "Content-Disposition": f'inline; filename="narration-{job.id}.mp3"',
            "Accept-Ranges": "none",
        },
    )


@router.post("/audio/replay", response_model=OkResponse)
async def replay_audio(host: HostDep, session: SessionDep, hub: HubDep) -> OkResponse:
    """Fordert alle Clients auf, die letzte Sprachausgabe erneut abzuspielen."""
    stmt = (
        sa.select(AudioJob)
        .where(AudioJob.game_id == host.game.id, AudioJob.status == "ready")
        .order_by(AudioJob.created_at.desc())
        .limit(1)
    )
    job = (await session.execute(stmt)).scalars().first()
    if job is None:
        raise NotFoundError("Es liegt keine fertige Sprachausgabe vor.")
    await hub.publish(
        host.game.id,
        "audio.replay",
        {
            "audio_id": str(job.id),
            "text": job.text,
            "voice": job.voice,
            "url": job.url,
            "provider": job.provider,
            "mime_type": job.mime_type,
        },
    )
    return OkResponse(message="Wiedergabe angefordert.")
