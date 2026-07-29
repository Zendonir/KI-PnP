"""Der Rundenablauf -- Herzstueck der Spiellogik.

Ein Zug laeuft in zwei Phasen:

**Phase A (mechanisch, transaktional):** Alle eingereichten Handlungen werden
gegen das Regelwerk geprueft, Kosten gebucht, Wuerfe berechnet und
protokolliert. Das Ergebnis steht damit fest, bevor die KI ueberhaupt gefragt
wird.

**Phase B (erzaehlerisch):** Die KI bekommt die feststehenden Ergebnisse und
liefert Narration sowie Aenderungsvorschlaege. Das Backend validiert diese
Vorschlaege und schreibt nur an, was zulaessig ist.

Faellt die KI aus, bleibt Phase A erhalten und der Zug kann erneut erzaehlt
werden -- es geht nichts verloren.
"""

from __future__ import annotations

import logging
from typing import Any

import pydantic
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.base import LLMProvider, LLMRequest, extract_json
from app.ai.contracts import NarrationResponse, SummaryResponse, WorldResponse
from app.core.config import Settings
from app.core.errors import AIError, ConflictError, ValidationError
from app.db.base import utcnow
from app.db.models import (
    Action,
    AudioJob,
    Character,
    DiceRoll,
    Game,
    Narration,
    Player,
    SceneSummary,
    Turn,
)
from app.domain import dice
from app.domain.rules import ActionRequest, get_ruleset
from app.realtime.hub import EventHub
from app.schemas.api import ActionSubmitRequest
from app.services import events as ev
from app.services.context import ContextBuilder
from app.services.events import EventRecorder
from app.services.state_changes import StateChangeApplier
from app.services.views import character_to_domain
from app.tts.providers import SpeechRequest, TTSProvider

logger = logging.getLogger(__name__)


class TurnService:
    """Steuert Weltgenerierung, Handlungen und Rundenaufloesung."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        llm: LLMProvider,
        tts: TTSProvider,
        hub: EventHub,
        recorder: EventRecorder,
    ) -> None:
        self._session = session
        self._settings = settings
        self._llm = llm
        self._tts = tts
        self._hub = hub
        self._recorder = recorder

    # -- Weltgenerierung -------------------------------------------------

    async def bootstrap_world(self, game: Game) -> Turn:
        """Erzeugt Welt, Einleitung und die erste Runde."""
        builder = ContextBuilder(self._session, game, self._settings)
        context = await builder.build_world_context()
        response = await self._ask(
            game,
            prompt=prompts.build_world_prompt(context),
            model=WorldResponse,
            purpose="world",
        )

        game.status = "active"
        game.current_turn_number = 1
        turn = Turn(
            game_id=game.id,
            number=1,
            status="collecting",
            scene_title=response.scene_title or "Auftakt",
        )
        self._session.add(turn)
        await self._session.flush()

        applier = StateChangeApplier(self._session, game, self._recorder, turn_id=turn.id)
        application = await applier.apply_raw(response.changes, source="ai")

        await self._recorder.record(
            game,
            type=ev.GAME_STARTED,
            summary=f"Die Kampagne beginnt: {response.scene_title}",
            payload={
                "world_summary": response.world_summary,
                "accepted_changes": application.accepted_count,
                "rejected_changes": application.rejected_count,
            },
            turn_id=turn.id,
        )
        await self._persist_narration(game, turn, response)
        await self._align_turn_location(game, turn)
        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        await self._hub.publish(game.id, "turn.started", {"turn_number": turn.number})
        return turn

    # -- Handlungen ------------------------------------------------------

    async def submit_action(
        self, game: Game, turn: Turn, player: Player, request: ActionSubmitRequest
    ) -> Action:
        """Nimmt die Handlung eines Spielers entgegen."""
        if game.status != "active":
            raise ConflictError("Die Runde laeuft gerade nicht.")
        if turn.status != "collecting":
            raise ConflictError("Fuer diesen Zug werden keine Handlungen mehr angenommen.")

        character = await self._character_of(player)
        if character is None:
            raise ValidationError("Ohne Charakter kann nicht gehandelt werden.")
        if not character.is_alive:
            raise ConflictError(f"{character.name} ist nicht handlungsfaehig.")

        stmt = sa.select(Action).where(
            Action.turn_id == turn.id,
            Action.player_id == player.id,
            Action.status == "pending",
        )
        action = (await self._session.execute(stmt)).scalars().first()
        if action is None:
            action = Action(
                game_id=game.id,
                turn_id=turn.id,
                player_id=player.id,
                character_id=character.id,
            )
            self._session.add(action)

        action.kind = request.kind
        action.text = request.text
        action.target_ref = request.target_ref
        action.payload = dict(request.payload)
        action.status = "pending"
        await self._session.flush()

        await self._recorder.record(
            game,
            type=ev.ACTION_SUBMITTED,
            summary=f"{character.name} plant: {request.text}",
            payload={"action_id": str(action.id), "kind": request.kind, "text": request.text},
            turn_id=turn.id,
            actor_type="character",
            actor_id=character.id,
        )
        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        return action

    async def pending_player_ids(self, turn: Turn) -> set[Any]:
        """Spieler, die in diesem Zug bereits eingereicht haben."""
        stmt = sa.select(Action.player_id).where(
            Action.turn_id == turn.id, Action.status == "pending"
        )
        return set((await self._session.execute(stmt)).scalars().all())

    async def everyone_submitted(self, game: Game, turn: Turn) -> bool:
        """Prueft, ob alle handlungsfaehigen Spieler eingereicht haben."""
        stmt = (
            sa.select(Player.id)
            .join(Character, Character.player_id == Player.id)
            .where(
                Player.game_id == game.id,
                Player.is_active.is_(True),
                Character.is_alive.is_(True),
            )
        )
        expected = set((await self._session.execute(stmt)).scalars().all())
        if not expected:
            return False
        return expected.issubset(await self.pending_player_ids(turn))

    # -- Aufloesung ------------------------------------------------------

    async def resolve_turn(self, game: Game, turn: Turn) -> Turn:
        """Fuehrt beide Phasen aus und startet die naechste Runde."""
        if turn.status == "completed":
            raise ConflictError("Dieser Zug ist bereits abgeschlossen.")

        results = await self._resolve_mechanics(game, turn)
        return await self._narrate(game, turn, results)

    async def renarrate(self, game: Game, turn: Turn) -> Turn:
        """Erzaehlt einen bereits mechanisch aufgeloesten Zug neu."""
        results = await self._results_from_actions(turn)
        return await self._narrate(game, turn, results)

    async def _resolve_mechanics(self, game: Game, turn: Turn) -> list[dict[str, Any]]:
        """Phase A: Regelpruefung, Kosten und Wuerfe."""
        turn.status = "resolving"
        settings = game.settings
        ruleset = get_ruleset(settings.ruleset if settings else "classic")
        difficulty = settings.difficulty if settings else "normal"
        complexity = settings.rule_complexity if settings else "light"

        stmt = sa.select(Action).where(Action.turn_id == turn.id, Action.status == "pending")
        actions = list((await self._session.execute(stmt)).scalars().all())
        applier = StateChangeApplier(self._session, game, self._recorder, turn_id=turn.id)
        results: list[dict[str, Any]] = []

        for action in actions:
            character = (
                await self._session.get(Character, action.character_id)
                if action.character_id
                else None
            )
            if character is None:
                action.status = "rejected"
                action.rejection_reason = "Kein Charakter zugeordnet."
                continue

            actor = await character_to_domain(self._session, character)
            request = ActionRequest(
                kind=action.kind,
                text=action.text,
                target_ref=action.target_ref,
                payload=dict(action.payload or {}),
            )
            plan = ruleset.plan(
                request, actor, difficulty=difficulty, complexity=complexity
            )

            if not plan.allowed:
                action.status = "rejected"
                action.rejection_reason = plan.reason
                await self._recorder.record(
                    game,
                    type=ev.ACTION_REJECTED,
                    summary=f"{character.name} kann nicht handeln: {plan.reason}",
                    payload={"action_id": str(action.id), "reason": plan.reason},
                    turn_id=turn.id,
                    actor_type="character",
                    actor_id=character.id,
                )
                results.append(
                    {
                        "character": character.name,
                        "kind": action.kind,
                        "text": action.text,
                        "allowed": False,
                        "reason": plan.reason,
                    }
                )
                continue

            await applier.apply(plan.costs, source="rules")

            roll = None
            if plan.check is not None:
                roll = dice.roll(
                    plan.check.notation,
                    difficulty=plan.check.difficulty,
                    bonus=plan.check.bonus,
                    reason=plan.check.reason,
                )
                self._session.add(
                    DiceRoll(
                        game_id=game.id,
                        turn_id=turn.id,
                        action_id=action.id,
                        character_id=character.id,
                        notation=roll.notation,
                        rolls=list(roll.rolls),
                        modifier=roll.modifier,
                        total=roll.total,
                        difficulty=roll.difficulty,
                        success=roll.success,
                        degree=roll.degree,
                        reason=roll.reason,
                    )
                )
                await self._recorder.record(
                    game,
                    type=ev.DICE_ROLLED,
                    summary=(
                        f"{character.name} wuerfelt {roll.notation}: {roll.total} "
                        f"gegen {roll.difficulty} -> {roll.degree}"
                    ),
                    payload={
                        "character": character.name,
                        "notation": roll.notation,
                        "rolls": list(roll.rolls),
                        "modifier": roll.modifier,
                        "total": roll.total,
                        "difficulty": roll.difficulty,
                        "success": roll.success,
                        "degree": roll.degree,
                    },
                    turn_id=turn.id,
                    actor_type="character",
                    actor_id=character.id,
                )

            await applier.apply(
                ruleset.outcome_effects(request, actor, roll), source="rules"
            )

            outcome = {
                "allowed": True,
                "success": roll.success if roll else None,
                "degree": roll.degree if roll else "",
                "total": roll.total if roll else None,
                "difficulty": roll.difficulty if roll else None,
            }
            action.status = "resolved"
            action.outcome = outcome
            await self._recorder.record(
                game,
                type=ev.ACTION_RESOLVED,
                summary=f"{character.name}: {action.text} ({outcome['degree'] or 'ohne Probe'})",
                payload={"action_id": str(action.id), **outcome},
                turn_id=turn.id,
                actor_type="character",
                actor_id=character.id,
            )
            results.append(
                {
                    "character": character.name,
                    "kind": action.kind,
                    "text": action.text,
                    "allowed": True,
                    **outcome,
                }
            )

        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        return results

    async def _narrate(
        self, game: Game, turn: Turn, results: list[dict[str, Any]]
    ) -> Turn:
        """Phase B: KI erzaehlt, Backend validiert die Vorschlaege."""
        builder = ContextBuilder(self._session, game, self._settings)
        context = await builder.build_turn_context(turn, action_results=results)
        response = await self._ask(
            game,
            prompt=prompts.build_turn_prompt(context),
            model=NarrationResponse,
            purpose="turn",
        )

        applier = StateChangeApplier(self._session, game, self._recorder, turn_id=turn.id)
        application = await applier.apply_raw(response.changes, source="ai")

        turn.status = "completed"
        turn.resolved_at = utcnow()
        await self._recorder.record(
            game,
            type=ev.TURN_COMPLETED,
            summary=f"Zug {turn.number} abgeschlossen.",
            payload={
                "turn_number": turn.number,
                "accepted_changes": application.accepted_count,
                "rejected_changes": application.rejected_count,
            },
            turn_id=turn.id,
            counts_towards_summary=False,
        )

        game.current_turn_number += 1
        next_turn = Turn(
            game_id=game.id,
            number=game.current_turn_number,
            status="collecting",
            scene_title=response.scene_title or turn.scene_title,
        )
        self._session.add(next_turn)
        await self._session.flush()

        await self._persist_narration(game, next_turn, response)
        await self._align_turn_location(game, next_turn)
        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        await self._hub.publish(
            game.id, "turn.started", {"turn_number": next_turn.number}
        )

        await self._maybe_summarize(game)
        return next_turn

    async def _results_from_actions(self, turn: Turn) -> list[dict[str, Any]]:
        """Rekonstruiert die Ergebnisse eines bereits gewuerfelten Zuges."""
        stmt = sa.select(Action).where(Action.turn_id == turn.id)
        results: list[dict[str, Any]] = []
        for action in (await self._session.execute(stmt)).scalars().all():
            character = (
                await self._session.get(Character, action.character_id)
                if action.character_id
                else None
            )
            results.append(
                {
                    "character": character.name if character else "Unbekannt",
                    "kind": action.kind,
                    "text": action.text,
                    "allowed": action.status != "rejected",
                    "reason": action.rejection_reason or "",
                    **(action.outcome or {}),
                }
            )
        return results

    # -- Narration und Audio ---------------------------------------------

    async def _persist_narration(
        self, game: Game, turn: Turn, response: NarrationResponse
    ) -> None:
        """Speichert Erzaehltext, private Hinweise und Handlungsvorschlaege."""
        turn.suggestions = {
            name: [item.model_dump() for item in suggestions]
            for name, suggestions in response.suggestions.items()
        }
        turn.scene_title = response.scene_title or turn.scene_title

        if response.narration.strip():
            narration = Narration(
                game_id=game.id,
                turn_id=turn.id,
                kind="public",
                text=response.narration.strip(),
                scene_title=response.scene_title,
            )
            self._session.add(narration)
            await self._session.flush()
            await self._recorder.record(
                game,
                type=ev.NARRATION_CREATED,
                summary=response.scene_title or "Die Geschichte geht weiter.",
                payload={"narration_id": str(narration.id), "text": narration.text},
                turn_id=turn.id,
                actor_type="ai",
            )
            await self._create_audio_job(game, narration, response.audio_hint)

        for message in response.private_messages:
            player = await self._player_of_character(game, message.character)
            if player is None:
                continue
            private = Narration(
                game_id=game.id,
                turn_id=turn.id,
                kind="private",
                audience_player_id=player.id,
                text=message.text,
                scene_title=response.scene_title,
            )
            self._session.add(private)
            await self._recorder.record(
                game,
                type=ev.NARRATION_CREATED,
                summary=f"Private Information fuer {message.character}.",
                payload={"text": message.text},
                turn_id=turn.id,
                actor_type="ai",
                visibility="private",
                audience_player_id=player.id,
                counts_towards_summary=False,
            )

        for line in response.public_events:
            await self._recorder.record(
                game,
                type="story.beat",
                summary=line,
                payload={},
                turn_id=turn.id,
                actor_type="ai",
            )

    async def _create_audio_job(
        self, game: Game, narration: Narration, mood: str
    ) -> None:
        """Legt einen Sprachausgabe-Auftrag an (ein Auftrag je Ausgabeziel)."""
        settings = game.settings
        if settings is not None and not settings.tts_enabled:
            return
        targets = list(settings.audio_targets or ["browser"]) if settings else ["browser"]
        result = await self._tts.synthesize(
            SpeechRequest(
                text=narration.text, voice=self._settings.tts_voice, mood=mood
            )
        )
        for target in targets or ["browser"]:
            job = AudioJob(
                game_id=game.id,
                narration_id=narration.id,
                provider=self._tts.name,
                voice=self._settings.tts_voice,
                status=result.status,
                target=target,
                url=result.url,
                text=narration.text,
                error=result.error,
                meta=dict(result.meta or {}),
            )
            self._session.add(job)
            await self._session.flush()
            if result.status == "ready":
                await self._recorder.record(
                    game,
                    type=ev.AUDIO_READY,
                    summary="Sprachausgabe bereit.",
                    payload={
                        "audio_id": str(job.id),
                        "target": target,
                        "url": job.url,
                        "text": job.text,
                        "voice": job.voice,
                        "provider": job.provider,
                    },
                    turn_id=narration.turn_id,
                    actor_type="ai",
                    counts_towards_summary=False,
                )

    # -- Zusammenfassungen -----------------------------------------------

    async def _maybe_summarize(self, game: Game) -> None:
        """Verdichtet das Protokoll, sobald genug Ereignisse aufgelaufen sind."""
        settings = game.settings
        threshold = (
            settings.summary_every_n_events
            if settings
            else self._settings.summary_every_n_events
        )
        if game.events_since_summary < threshold:
            return
        try:
            await self.create_summary(game)
        except Exception as exc:  # noqa: BLE001 - Zusammenfassung darf nie blockieren
            logger.warning("Zusammenfassung fehlgeschlagen: %s", exc)

    async def create_summary(self, game: Game) -> SceneSummary:
        """Erzeugt einen Gedaechtniseintrag ueber die juengsten Ereignisse."""
        last_stmt = (
            sa.select(SceneSummary.to_seq)
            .where(SceneSummary.game_id == game.id)
            .order_by(SceneSummary.to_seq.desc())
            .limit(1)
        )
        from_seq = (await self._session.execute(last_stmt)).scalars().first() or 0

        builder = ContextBuilder(self._session, game, self._settings)
        context = await builder.build_summary_context(from_seq=from_seq)
        response = await self._ask(
            game,
            prompt=prompts.build_summary_prompt(context),
            model=SummaryResponse,
            purpose="summary",
            max_tokens=1500,
        )

        summary = SceneSummary(
            game_id=game.id,
            from_seq=from_seq,
            to_seq=game.event_seq,
            turn_number=game.current_turn_number,
            text=response.text,
            highlights=list(response.highlights),
        )
        self._session.add(summary)
        game.events_since_summary = 0
        await self._recorder.record(
            game,
            type=ev.SUMMARY_CREATED,
            summary="Zusammenfassung aktualisiert.",
            payload={"from_seq": from_seq, "to_seq": game.event_seq},
            counts_towards_summary=False,
        )
        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        return summary

    # -- Hilfsmittel -----------------------------------------------------

    async def _ask(
        self,
        game: Game,
        *,
        prompt: str,
        model: type[pydantic.BaseModel],
        purpose: str,
        max_tokens: int | None = None,
    ) -> Any:
        """Fragt die KI und validiert die Antwort gegen den Vertrag."""
        language = game.settings.language if game.settings else "de"
        request = LLMRequest(
            system=prompts.system_prompt(language),
            prompt=prompt,
            max_tokens=max_tokens or self._settings.ai_max_tokens,
            purpose=purpose,
        )
        response = await self._llm.complete(request)
        try:
            return model.model_validate(extract_json(response.text))
        except pydantic.ValidationError as exc:
            raise AIError(
                "Die KI-Antwort entspricht nicht dem vereinbarten Format.",
                details={"errors": exc.errors()[:3]},
            ) from exc

    async def _character_of(self, player: Player) -> Character | None:
        stmt = sa.select(Character).where(Character.player_id == player.id)
        return (await self._session.execute(stmt)).scalars().first()

    async def _player_of_character(self, game: Game, character_name: str) -> Player | None:
        stmt = (
            sa.select(Player)
            .join(Character, Character.player_id == Player.id)
            .where(
                Player.game_id == game.id,
                sa.func.lower(Character.name) == character_name.strip().lower(),
            )
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def _align_turn_location(self, game: Game, turn: Turn) -> None:
        """Uebernimmt den Aufenthaltsort der Gruppe in die Runde."""
        stmt = (
            sa.select(Character.location_id)
            .where(Character.game_id == game.id, Character.location_id.isnot(None))
            .limit(1)
        )
        location_id = (await self._session.execute(stmt)).scalars().first()
        if location_id is not None:
            turn.location_id = location_id
