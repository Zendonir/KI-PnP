"""Spielrunden verwalten: erstellen, beitreten, Zustand liefern, moderieren."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import create_join_code, create_token
from app.db.base import utcnow
from app.db.models import (
    Action,
    AudioJob,
    Character,
    DiceRoll,
    Fact,
    Game,
    GameSettings,
    Knowledge,
    Location,
    Narration,
    Player,
    Quest,
    Turn,
    WorldEntity,
)
from app.realtime.hub import EventHub
from app.schemas.api import (
    AudioOut,
    DiceRollOut,
    EntityOut,
    EventOut,
    FactOut,
    GameCreateRequest,
    GameOut,
    GameStateOut,
    LocationOut,
    NarrationOut,
    PlayerOut,
    QuestOut,
    SuggestionOut,
    TurnOut,
)
from app.services import events as ev
from app.services.events import EventRecorder, load_recent_events
from app.services.views import character_to_out


class GameService:
    """Anwendungsfaelle rund um eine Spielrunde."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        hub: EventHub,
        recorder: EventRecorder,
    ) -> None:
        self._session = session
        self._settings = settings
        self._hub = hub
        self._recorder = recorder

    # -- Erstellen und Beitreten -----------------------------------------

    async def create_game(self, request: GameCreateRequest) -> tuple[Game, Player, str]:
        """Legt Runde, Einstellungen und den Host als ersten Spieler an."""
        code = await self._unique_code()
        game = Game(code=code, name=request.name.strip(), status="lobby")
        self._session.add(game)
        await self._session.flush()

        payload = request.settings.model_dump()
        game.settings = GameSettings(
            game_id=game.id,
            summary_every_n_events=self._settings.summary_every_n_events,
            **payload,
        )
        host = Player(game_id=game.id, name=request.host_name.strip(), role="host")
        self._session.add(host)
        await self._session.flush()
        game.host_player_id = host.id

        await self._recorder.record(
            game,
            type=ev.GAME_CREATED,
            summary=f"Runde {game.name!r} wurde eroeffnet.",
            payload={"code": game.code, "host": host.name},
            actor_type="player",
            actor_id=host.id,
        )
        await self._session.commit()
        await self._session.refresh(game)

        token = create_token(
            self._settings, player_id=host.id, game_id=game.id, role="host"
        )
        return game, host, token

    async def join_game(self, code: str, player_name: str) -> tuple[Game, Player, str]:
        """Fuegt einen Spieler ueber den Beitrittscode hinzu."""
        game = await self.get_by_code(code)
        if game.status == "finished":
            raise ConflictError("Diese Runde ist bereits beendet.")

        name = player_name.strip()
        if not name:
            raise ValidationError("Bitte einen Namen angeben.")

        existing = await self._session.execute(
            sa.select(Player).where(
                Player.game_id == game.id, sa.func.lower(Player.name) == name.lower()
            )
        )
        player = existing.scalars().first()
        if player is not None:
            # Wiedereinstieg mit demselben Namen ist ausdruecklich erlaubt.
            player.is_active = True
            player.last_seen_at = utcnow()
        else:
            limit = game.settings.max_players if game.settings else 8
            active = await self._session.execute(
                sa.select(sa.func.count())
                .select_from(Player)
                .where(Player.game_id == game.id, Player.is_active.is_(True))
            )
            if (active.scalar_one() or 0) >= limit:
                raise ConflictError("Die Runde ist voll.")
            player = Player(game_id=game.id, name=name, role="player")
            self._session.add(player)
            await self._session.flush()
            await self._recorder.record(
                game,
                type=ev.PLAYER_JOINED,
                summary=f"{name} tritt der Runde bei.",
                payload={"player_id": str(player.id), "name": name},
                actor_type="player",
                actor_id=player.id,
            )

        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        await self._hub.publish(game.id, "lobby.updated", {"player": player.name})

        token = create_token(
            self._settings, player_id=player.id, game_id=game.id, role=player.role
        )
        return game, player, token

    async def _unique_code(self) -> str:
        for _ in range(20):
            code = create_join_code()
            stmt = sa.select(Game.id).where(Game.code == code)
            if (await self._session.execute(stmt)).scalars().first() is None:
                return code
        raise ConflictError("Es konnte kein freier Beitrittscode erzeugt werden.")

    # -- Lesen -----------------------------------------------------------

    async def get(self, game_id: uuid.UUID) -> Game:
        game = await self._session.get(Game, game_id)
        if game is None:
            raise NotFoundError("Spielrunde nicht gefunden.")
        return game

    async def get_by_code(self, code: str) -> Game:
        stmt = sa.select(Game).where(Game.code == code.strip().upper())
        game = (await self._session.execute(stmt)).scalars().first()
        if game is None:
            raise NotFoundError("Kein Spiel mit diesem Code gefunden.")
        return game

    async def get_player(self, game: Game, player_id: uuid.UUID) -> Player:
        player = await self._session.get(Player, player_id)
        if player is None or player.game_id != game.id:
            raise NotFoundError("Spieler gehoert nicht zu dieser Runde.")
        return player

    async def current_turn(self, game: Game) -> Turn | None:
        stmt = (
            sa.select(Turn)
            .where(Turn.game_id == game.id)
            .order_by(Turn.number.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def character_of(self, player: Player) -> Character | None:
        stmt = sa.select(Character).where(Character.player_id == player.id)
        return (await self._session.execute(stmt)).scalars().first()

    # -- Zustand ---------------------------------------------------------

    async def build_state(self, game: Game, player: Player) -> GameStateOut:
        """Erzeugt den spielerspezifisch gefilterten Zustand.

        Geheime Fakten und private Narrationen anderer Spieler sind hier
        bewusst nicht enthalten.
        """
        players = list(
            (
                await self._session.execute(
                    sa.select(Player).where(Player.game_id == game.id).order_by(Player.created_at)
                )
            )
            .scalars()
            .all()
        )
        characters = list(
            (
                await self._session.execute(
                    sa.select(Character).where(Character.game_id == game.id)
                )
            )
            .scalars()
            .all()
        )
        my_character = next(
            (item for item in characters if item.player_id == player.id), None
        )
        turn = await self.current_turn(game)

        narrations = list(
            (
                await self._session.execute(
                    sa.select(Narration)
                    .where(
                        Narration.game_id == game.id,
                        sa.or_(
                            Narration.kind == "public",
                            Narration.audience_player_id == player.id,
                        ),
                    )
                    .order_by(Narration.created_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        rolls = list(
            (
                await self._session.execute(
                    sa.select(DiceRoll)
                    .where(DiceRoll.game_id == game.id)
                    .order_by(DiceRoll.created_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        quests = list(
            (
                await self._session.execute(sa.select(Quest).where(Quest.game_id == game.id))
            )
            .scalars()
            .all()
        )
        locations = list(
            (
                await self._session.execute(
                    sa.select(Location).where(
                        Location.game_id == game.id, Location.is_discovered.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        entities = list(
            (
                await self._session.execute(
                    sa.select(WorldEntity).where(
                        WorldEntity.game_id == game.id,
                        WorldEntity.kind.in_(("npc", "monster", "faction")),
                    )
                )
            )
            .scalars()
            .all()
        )
        facts = list(
            (
                await self._session.execute(
                    sa.select(Fact)
                    .where(
                        Fact.game_id == game.id,
                        Fact.invalidated_at_seq.is_(None),
                        Fact.visibility.in_(("public", "party")),
                    )
                    .order_by(Fact.created_at_seq.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
        knowledge = await self._knowledge_for(game, my_character)
        audio = (
            await self._session.execute(
                sa.select(AudioJob)
                .where(AudioJob.game_id == game.id, AudioJob.target == "browser")
                .order_by(AudioJob.created_at.desc())
                .limit(1)
            )
        ).scalars().first()

        raw_events = await load_recent_events(self._session, game.id, limit=60)
        visible_events = [
            event
            for event in raw_events
            if event.visibility != "private" or event.audience_player_id == player.id
        ]

        turn_out = None
        if turn is not None:
            suggestions = []
            if my_character is not None:
                raw = (turn.suggestions or {}).get(my_character.name, [])
                suggestions = [
                    SuggestionOut(
                        kind=str(item.get("kind", "custom")),
                        label=str(item.get("label", "")),
                        hint=str(item.get("hint", "")),
                    )
                    for item in raw
                    if isinstance(item, dict)
                ]
            submitted = list(
                (
                    await self._session.execute(
                        sa.select(Action.player_id).where(
                            Action.turn_id == turn.id, Action.status == "pending"
                        )
                    )
                )
                .scalars()
                .all()
            )
            turn_out = TurnOut(
                id=turn.id,
                number=turn.number,
                status=turn.status,
                scene_title=turn.scene_title,
                submitted_player_ids=submitted,
                my_suggestions=suggestions,
            )

        return GameStateOut(
            game=GameOut.model_validate(game),
            players=[PlayerOut.model_validate(item) for item in players],
            characters=[
                await character_to_out(self._session, item) for item in characters
            ],
            me=PlayerOut.model_validate(player),
            my_character=(
                await character_to_out(self._session, my_character) if my_character else None
            ),
            turn=turn_out,
            narrations=[
                NarrationOut.model_validate(item) for item in reversed(narrations)
            ],
            dice_rolls=[DiceRollOut.model_validate(item) for item in reversed(rolls)],
            quests=[
                QuestOut(
                    id=quest.id,
                    title=quest.title,
                    description=quest.description,
                    status=quest.current_state.status if quest.current_state else "open",
                    is_main=quest.is_main,
                )
                for quest in quests
                if not quest.current_state or quest.current_state.visibility != "secret"
            ],
            locations=[LocationOut.model_validate(item) for item in locations],
            entities=[EntityOut.model_validate(item) for item in entities],
            facts=[
                FactOut(
                    key=fact.key,
                    statement=fact.statement,
                    visibility=fact.visibility,
                    turn_number=fact.turn_number,
                )
                for fact in reversed(facts)
            ],
            knowledge=knowledge,
            events=[EventOut.model_validate(item) for item in visible_events],
            audio=AudioOut.model_validate(audio) if audio else None,
            is_host=player.role == "host",
        )

    async def _knowledge_for(self, game: Game, character: Character | None) -> list[str]:
        conditions = [Knowledge.subject_type == "public"]
        if character is not None:
            conditions.append(
                sa.and_(
                    Knowledge.subject_type == "character",
                    Knowledge.subject_id == character.id,
                )
            )
        stmt = (
            sa.select(Knowledge)
            .where(Knowledge.game_id == game.id, sa.or_(*conditions))
            .order_by(Knowledge.created_at_seq.desc())
            .limit(40)
        )
        entries = list((await self._session.execute(stmt)).scalars().all())
        return [
            entry.content
            if entry.certainty == "truth"
            else f"[{entry.certainty}] {entry.content}"
            for entry in reversed(entries)
        ]

    # -- Moderation ------------------------------------------------------

    async def set_status(self, game: Game, status: str) -> Game:
        """Pausiert, setzt fort oder beendet eine Runde."""
        if status not in ("active", "paused", "finished"):
            raise ValidationError(f"Unbekannter Status {status!r}.")
        if game.status == "lobby" and status != "finished":
            raise ConflictError("Die Runde wurde noch nicht gestartet.")
        game.status = status
        if status == "finished":
            game.finished_at = utcnow()
        await self._recorder.record(
            game,
            type=ev.GAME_STATUS_CHANGED,
            summary=f"Die Runde ist jetzt {status}.",
            payload={"status": status},
            counts_towards_summary=False,
        )
        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        await self._hub.publish(game.id, "game.status", {"status": status})
        return game

    async def remove_player(self, game: Game, player_id: uuid.UUID) -> None:
        """Entfernt einen Spieler aus der Runde (Charakter bleibt erhalten)."""
        player = await self.get_player(game, player_id)
        if player.id == game.host_player_id:
            raise ConflictError("Der Spielleiter kann sich nicht selbst entfernen.")
        player.is_active = False
        player.is_connected = False
        await self._recorder.record(
            game,
            type=ev.PLAYER_LEFT,
            summary=f"{player.name} hat die Runde verlassen.",
            payload={"player_id": str(player.id)},
            counts_towards_summary=False,
        )
        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        await self._hub.publish(game.id, "lobby.updated", {"player": player.name})

    async def set_connection(self, player: Player, connected: bool) -> None:
        """Vermerkt den Verbindungszustand eines Spielers."""
        player.is_connected = connected
        player.last_seen_at = utcnow()
        await self._session.commit()
