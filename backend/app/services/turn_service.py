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

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass
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
    TurnAck,
)
from app.domain import dice
from app.domain.rules import ActionRequest, get_ruleset
from app.realtime.hub import EventHub
from app.schemas.api import ActionSubmitRequest
from app.services import events as ev
from app.services import interventions
from app.services.context import ContextBuilder
from app.services.events import EventRecorder, increment_game_counter, reset_game_counter
from app.services.runtime_settings import get_effective_tts
from app.services.state_changes import StateChangeApplier
from app.services.views import character_to_domain
from app.tts.providers import SpeechRequest, TTSProvider

logger = logging.getLogger(__name__)

_INTERVENTION_CHANCE = 0.10
"""Anteil der Zugaufloesungen, bei denen ein Mitspieler kurz eingreifen darf --
selten genug, um zu ueberraschen (siehe _maybe_offer_intervention)."""

_POOR_FIT_DIFFICULTY_DELTA = 4
"""Zusaetzliche Schwierigkeit, wenn das selbst gewaehlte Attribut nur locker
zur Handlung passt (siehe _judge_stat_fit)."""


@dataclass(frozen=True, slots=True)
class _StatFit:
    """Ergebnis der KI-Passungspruefung fuer ein selbst gewaehltes Attribut."""

    difficulty_delta: int = 0
    auto_fail: bool = False

_INTERVENTION_TIMEOUT_SECONDS = 8.0


async def expected_player_ids(
    session: AsyncSession, game: Game, location_id: uuid.UUID | None
) -> set[uuid.UUID]:
    """Aktive, lebende Spieler, deren Charakter sich an diesem Ort befindet.

    Eigenstaendige Funktion statt einer TurnService-Methode: sowohl die
    Zug-Bereitschaft (turn_ready, hier in dieser Datei) als auch die
    Zusammenfassung des Aufdeckungs-Fortschritts (GameService.build_state,
    fuer state.pending_reveal) brauchen dieselbe Menge.
    """
    location_filter = (
        Character.location_id.is_(None)
        if location_id is None
        else Character.location_id == location_id
    )
    stmt = (
        sa.select(Player.id)
        .join(Character, Character.player_id == Player.id)
        .where(
            Player.game_id == game.id,
            Player.is_active.is_(True),
            Character.is_alive.is_(True),
            location_filter,
        )
    )
    return set((await session.execute(stmt)).scalars().all())


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

    # -- Nebenlaeufigkeit --------------------------------------------------

    async def _lock_game(self, game: Game) -> Game:
        """Sperrt die Spielzeile fuer die Dauer der Transaktion.

        Sobald mehrere Orte gleichzeitig einen Zug abschliessen koennen,
        wuerden parallele Anfragen sonst auf denselben event_seq/
        current_turn_number-Stand lesen und sich beim Schreiben ueberholen.
        Auf Postgres ein echter FOR-UPDATE-Zeilenlock; auf SQLite (Tests) ein
        wirkungsloses No-Op, weil SQLite Schreiber ohnehin serialisiert.
        populate_existing sorgt dafuer, dass das schon geladene Game-Objekt
        den aktuellsten committeten Stand traegt, bevor +=1 darauf arbeitet.
        """
        locked = await self._session.get(
            Game, game.id, with_for_update=True, populate_existing=True
        )
        assert locked is not None
        return locked

    async def _sync_location_turns(
        self, game: Game, character_ids: list[Any], *, carry_scene_title: str
    ) -> list[tuple[Turn, bool]]:
        """Holt oder legt pro vertretenem Ort genau einen laufenden Zug an.

        Das ist zugleich der gesamte Mechanismus fuer automatisches Einreihen
        und Wiedervereinigen: existiert am Zielort schon ein Zug, wird er
        wiederverwendet -- unabhaengig davon, ob der Charakter gerade zum
        ersten Mal dort ankommt oder die Gruppe sich dort wieder trifft. Das
        zweite Element pro Eintrag sagt, ob der Zug dabei neu angelegt wurde
        (nur dafuer lohnt ein turn.started-Event -- ein wiederverwendeter Zug
        kuendigt sich bereits durch das state.changed-Ereignis des Umzugs an).
        Muss innerhalb einer per _lock_game gesicherten Transaktion laufen.
        """
        if not character_ids:
            return []

        stmt = sa.select(Character.location_id).where(
            Character.id.in_(character_ids), Character.is_alive.is_(True)
        )
        location_ids = set((await self._session.execute(stmt)).scalars().all())

        results: list[tuple[Turn, bool]] = []
        for location_id in location_ids:
            # "resolving" zaehlt hier bewusst mit: sonst haelt kein Zug den
            # Ort besetzt, waehrend Phase A schon fertig ist, aber noch auf
            # /continue wartet -- ein zweiter, neu angelegter "collecting"-
            # Zug am selben Ort waere sonst moeglich (etwa ueber
            # ensure_turn_for_character).
            existing_stmt = sa.select(Turn).where(
                Turn.game_id == game.id,
                Turn.status.in_(("collecting", "resolving")),
                Turn.location_id.is_(None) if location_id is None
                else Turn.location_id == location_id,
            )
            existing = (await self._session.execute(existing_stmt)).scalars().first()
            if existing is not None:
                results.append((existing, False))
                continue

            number = await increment_game_counter(self._session, game, Game.current_turn_number)
            turn = Turn(
                game_id=game.id,
                number=number,
                status="collecting",
                scene_title=carry_scene_title,
                location_id=location_id,
            )
            self._session.add(turn)
            results.append((turn, True))
        await self._session.flush()
        return results

    async def ensure_turn_for_character(
        self, game: Game, character: Character
    ) -> Turn | None:
        """Holt oder legt den Zug an, der zum Ort dieses Charakters passt.

        Absicherung fuer den seltenen Fall, dass ein Charakter (etwa ein
        spaeter Beitritt mitten im Spiel) an einem Ort steht, fuer den noch
        kein laufender Zug existiert -- im Regelbetrieb bekommt das jeder Ort
        bereits proaktiv bei der vorigen Rundenaufloesung
        (_sync_location_turns), dieser Weg greift nur, wenn das ausnahmsweise
        nicht der Fall war. Ein toter Charakter braucht keinen Zug.

        Vor dem eigentlichen Rundenstart gibt es grundsaetzlich keine Zuege:
        ohne diese Sperre wuerde ein Spieler, der waehrend der Lobby-
        Wartezeit einen /state-Abgleich abschickt, hier einen verwaisten Zug
        ohne Ort anlegen. bootstrap_world setzt current_turn_number beim
        Start bewusst auf 0 zurueck, damit der erste echte Zug die Nummer 1
        traegt -- kollidiert das mit einem schon vorhandenen, verwaisten Zug
        derselben Nummer, schlaegt der Rundenstart mit einem
        Datenbankfehler fehl.
        """
        if not character.is_alive:
            return None
        if game.status != "active":
            return None
        game = await self._lock_game(game)
        synced = await self._sync_location_turns(
            game, [character.id], carry_scene_title=""
        )
        if not synced:
            return None
        turn, created = synced[0]
        if created:
            await self._session.commit()
            await self._recorder.flush_to_clients(game.id)
            await self._hub.publish(
                game.id,
                "turn.started",
                {
                    "turn_number": turn.number,
                    "turn_id": str(turn.id),
                    "location_id": str(turn.location_id) if turn.location_id else None,
                },
            )
        return turn

    # -- Weltgenerierung -------------------------------------------------

    async def bootstrap_world(self, game: Game) -> Turn:
        """Erzeugt Welt, Einleitung und die erste Runde."""
        game = await self._lock_game(game)
        builder = ContextBuilder(self._session, game, self._settings)
        context = await builder.build_world_context()
        response = await self._ask(
            game,
            prompt=prompts.build_world_prompt(context),
            model=WorldResponse,
            purpose="world",
        )

        game.status = "active"
        # Zaehler startet bei 0: die Nummer 1 gehoert dem ersten wirklich
        # bespielbaren Zug, den _sync_location_turns unten vergibt -- der
        # Traeger-Zug hier ist reine Buchfuehrung und soll die Zaehlung
        # nicht verschieben.
        game.current_turn_number = 0
        # Traeger-Zug: haelt Ereignisse und Aenderungen der Weltentstehung
        # fest, bevor feststeht, wo die Charaktere am Ende landen. Er wird
        # nie von Spielern bespielt und ist unten sofort abgeschlossen --
        # dasselbe Muster wie am Ende jedes gewoehnlichen Zugs.
        origin = Turn(
            game_id=game.id,
            number=0,
            status="collecting",
            scene_title=response.scene_title or "Auftakt",
        )
        self._session.add(origin)
        await self._session.flush()

        applier = StateChangeApplier(self._session, game, self._recorder, turn_id=origin.id)
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
            turn_id=origin.id,
        )
        origin.status = "completed"
        origin.resolved_at = utcnow()

        character_ids = list(
            (
                await self._session.execute(
                    sa.select(Character.id).where(
                        Character.game_id == game.id, Character.is_alive.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        synced = await self._sync_location_turns(
            game, character_ids, carry_scene_title=origin.scene_title
        )
        if not synced:
            # Kein Charakter wurde platziert (oder es gibt noch keinen) --
            # ohne einen Ort zum Anknuepfen bleibt der Traeger-Zug der
            # einzige Ansprechpartner und wird selbst zum ersten Zug.
            game.current_turn_number = 1
            origin.number = 1
            origin.status = "collecting"
            origin.resolved_at = None
            synced = [(origin, True)]

        primary, _ = synced[0]
        await self._persist_narration(game, primary, response)
        for other, _ in synced[1:]:
            other.scene_title = response.scene_title or other.scene_title

        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        for started, created in synced:
            if created:
                await self._hub.publish(
                    game.id,
                    "turn.started",
                    {
                        "turn_number": started.number,
                        "turn_id": str(started.id),
                        "location_id": (
                            str(started.location_id) if started.location_id else None
                        ),
                    },
                )
        return primary

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
        payload = dict(request.payload)
        if request.stat:
            payload["stat"] = request.stat
        action.payload = payload
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

    async def turn_ready(self, game: Game, turn: Turn) -> bool:
        """Prueft, ob alle handlungsfaehigen Spieler an diesem Ort eingereicht haben.

        Nur Spieler, deren Charakter sich gerade am Ort dieses Zugs
        befindet, zaehlen -- das ist der Mechanismus, der eine Aufteilung
        der Gruppe ueberhaupt erst unabhaengig aufloesen laesst.
        """
        expected = await expected_player_ids(self._session, game, turn.location_id)
        if not expected:
            return False
        return expected.issubset(await self.pending_player_ids(turn))

    # -- Aufdecken ---------------------------------------------------------
    #
    # Wuerfelergebnisse, Erzaehlung und Ton eines abgeschlossenen Zugs
    # entstehen sofort im Hintergrund, werden aber erst fuer alle sichtbar,
    # sobald jeder erwartete Spieler sein Wuerfel-Popup bestaetigt hat (oder
    # die Spielleitung vorzeitig aufdeckt) -- niemand liest oder hoert vor
    # dem Rest der Gruppe weiter.

    async def acknowledge_turn(self, game: Game, turn: Turn, player: Player) -> Turn:
        """Merkt sich, dass ein Spieler die Wuerfelergebnisse gesehen hat."""
        if turn.status != "completed":
            raise ConflictError("Dieser Zug ist noch nicht abgeschlossen.")
        if turn.revealed_at is None:
            exists_stmt = sa.select(TurnAck.id).where(
                TurnAck.turn_id == turn.id, TurnAck.player_id == player.id
            )
            already = (await self._session.execute(exists_stmt)).scalar_one_or_none()
            if already is None:
                self._session.add(TurnAck(turn_id=turn.id, player_id=player.id))
                await self._session.flush()

            acked_stmt = sa.select(TurnAck.player_id).where(TurnAck.turn_id == turn.id)
            acked = set((await self._session.execute(acked_stmt)).scalars().all())
            expected = await expected_player_ids(self._session, game, turn.location_id)
            if not expected or expected.issubset(acked):
                await self._reveal_turn(game, turn)

            await self._session.commit()
            await self._recorder.flush_to_clients(game.id)
        return turn

    async def force_reveal_turn(self, game: Game, turn: Turn) -> Turn:
        """Deckt einen Zug sofort auf, unabhaengig von fehlenden Bestaetigungen.

        Nur der Spielleitung erlaubt (HostDep am Endpunkt) -- fuer den Fall,
        dass ein Mitspieler nicht mehr reagiert (App im Hintergrund,
        Verbindung weg) und die Runde sonst haengen bliebe.
        """
        if turn.status != "completed":
            raise ConflictError("Dieser Zug ist noch nicht abgeschlossen.")
        if turn.revealed_at is None:
            await self._reveal_turn(game, turn)
            await self._session.commit()
            await self._recorder.flush_to_clients(game.id)
        return turn

    async def _reveal_turn(self, game: Game, turn: Turn) -> None:
        turn.revealed_at = utcnow()
        await self._recorder.record(
            game,
            type=ev.TURN_REVEALED,
            summary=f"Zug {turn.number}: Ergebnisse fuer alle sichtbar.",
            payload={"turn_id": str(turn.id), "turn_number": turn.number},
            turn_id=turn.id,
            counts_towards_summary=False,
        )

    # -- Aufloesung ------------------------------------------------------

    async def resolve_turn(self, game: Game, turn: Turn) -> Turn:
        """Fuehrt beide Phasen aus und startet die naechste Runde."""
        if turn.status == "completed":
            raise ConflictError("Dieser Zug ist bereits abgeschlossen.")

        results = await self._resolve_mechanics(game, turn)
        return await self._narrate(game, turn, results)

    async def renarrate(self, game: Game, turn: Turn) -> Turn:
        """Erzaehlt einen bereits mechanisch aufgeloesten Zug neu.

        Nuetzlich, wenn die KI ausgefallen ist oder das Ergebnis nicht
        passt -- die bereits gewuerfelten Ergebnisse bleiben unveraendert.
        """
        results = await self._results_from_actions(turn)
        return await self._narrate(game, turn, results)

    async def _resolve_mechanics(self, game: Game, turn: Turn) -> list[dict[str, Any]]:
        """Phase A: Regelpruefung, Kosten und Wuerfe."""
        pending_stmt = sa.select(Action).where(
            Action.turn_id == turn.id, Action.status == "pending"
        )
        pending_actions = list((await self._session.execute(pending_stmt)).scalars().all())

        # Das Attribut waehlt jetzt der Spieler selbst (payload["stat"]).
        # Die KI wird nur noch gefragt, ob diese Wahl zur Handlung passt --
        # vor dem Sperren der Spielzeile, damit die Anfragen nicht seriell
        # unter Lock warten.
        stat_actions = [a for a in pending_actions if str((a.payload or {}).get("stat") or "")]
        stat_fits: dict[uuid.UUID, _StatFit] = {}
        if stat_actions:
            judged = await asyncio.gather(
                *(
                    self._judge_stat_fit(a.text, str((a.payload or {}).get("stat") or ""))
                    for a in stat_actions
                )
            )
            stat_fits = dict(zip((a.id for a in stat_actions), judged, strict=True))

        # Seltenes Quick-Time-Event: bevor die Wuerfe fallen, darf ein
        # zufaelliger Mitspieler kurz eingreifen. Bewusst ausserhalb des
        # Zeilensperren unten, damit ein bis zu 8 Sekunden langes Warten auf
        # eine Antwort keine anderen, an diesem Spiel arbeitenden Anfragen
        # blockiert (etwa die Aufloesung eines anderen Ortes).
        advantage_action_id, helper_name = await self._maybe_offer_intervention(
            game, turn, pending_actions
        )

        game = await self._lock_game(game)
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
            action_payload = dict(action.payload or {})
            request = ActionRequest(
                kind=action.kind,
                text=action.text,
                target_ref=action.target_ref,
                payload=action_payload,
                stat_hint=str(action_payload.get("stat") or "") or None,
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

            fit = stat_fits.get(action.id)
            auto_fail = bool(fit and fit.auto_fail and plan.check is not None)

            roll = None
            if plan.check is not None and not auto_fail:
                if fit and fit.difficulty_delta:
                    plan.check.difficulty += fit.difficulty_delta
                roll = dice.roll(
                    plan.check.notation,
                    difficulty=plan.check.difficulty,
                    bonus=plan.check.bonus,
                    reason=plan.check.reason,
                )
                if action.id == advantage_action_id:
                    second_roll = dice.roll(
                        plan.check.notation,
                        difficulty=plan.check.difficulty,
                        bonus=plan.check.bonus,
                        reason=plan.check.reason,
                    )
                    roll = dice.better(roll, second_roll)
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

            if auto_fail:
                outcome = {
                    "allowed": True,
                    "success": False,
                    "degree": "failure",
                    "total": None,
                    "difficulty": None,
                    "helped_by": None,
                    "reason": "Das gewaehlte Attribut passt nicht zur Handlung.",
                }
            else:
                outcome = {
                    "allowed": True,
                    "success": roll.success if roll else None,
                    "degree": roll.degree if roll else "",
                    "total": roll.total if roll else None,
                    "difficulty": roll.difficulty if roll else None,
                    "helped_by": helper_name if action.id == advantage_action_id else None,
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

        # Erfolglose Zuege in Folge zaehlen -- signalisiert der KI, wann sie
        # statt weiterer Atmosphaere eine konkrete Wendung liefern muss
        # (siehe ContextBuilder.build_turn_context / prompts.build_turn_prompt).
        # Ein reiner "wait"-Zug (niemand hat es versucht) aendert nichts;
        # ein abgelehnter Versuch zaehlt wie ein Fehlschlag als Stillstand.
        graded_results = [r for r in results if r.get("kind") != "wait"]
        if graded_results:
            made_progress = any(
                r.get("degree") in ("success", "critical_success", "partial")
                for r in graded_results
            )
            if made_progress:
                await reset_game_counter(self._session, game, Game.stall_streak)
            else:
                await increment_game_counter(self._session, game, Game.stall_streak)

        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        return results

    async def _judge_stat_fit(self, text: str, stat: str) -> _StatFit:
        """Laesst die KI beurteilen, ob das selbst gewaehlte Attribut passt.

        Der Spieler waehlt das Attribut selbst; die KI entscheidet nichts
        mechanisch, sondern schlaegt nur eine Erschwernis oder einen
        erzwungenen Fehlschlag vor, wenn die Wahl offensichtlich nicht zur
        Handlung passt. Scheitert die Einschaetzung -- KI nicht erreichbar,
        unerwartete Antwort, was auch immer --, gilt die Wahl als passend.
        Eine einzelne fehlgeschlagene Einschaetzung darf die Handlung nicht
        blockieren, deshalb wird hier bewusst breit abgefangen.
        """
        try:
            request = LLMRequest(
                system=prompts.STAT_FIT_SYSTEM,
                prompt=prompts.build_stat_fit_prompt(text, stat),
                max_tokens=60,
                purpose="stat_fit",
            )
            response = await self._llm.complete(request)
            fit = str(extract_json(response.text).get("fit", "")).strip().lower()
        except Exception:
            logger.warning(
                "Attribut-Passungspruefung fehlgeschlagen, werte als passend.", exc_info=True
            )
            return _StatFit()
        if fit == "auto_fail":
            return _StatFit(auto_fail=True)
        if fit == "poor":
            return _StatFit(difficulty_delta=_POOR_FIT_DIFFICULTY_DELTA)
        return _StatFit()

    async def _maybe_offer_intervention(
        self, game: Game, turn: Turn, pending_actions: list[Action]
    ) -> tuple[uuid.UUID | None, str | None]:
        """Bietet selten einem zufaelligen Mitspieler an, kurz einzugreifen.

        Nimmt jemand rechtzeitig an, bekommt eine zufaellig gewaehlte
        Handlung dieses Zuges Vorteil (zwei Wuerfe, der bessere zaehlt).
        Damit das ueberrascht, greift das nur bei einem kleinen Bruchteil
        der Zuege und nie, wenn niemand sonst am selben Ort ist, der helfen
        koennte.
        """
        if not pending_actions or random.random() >= _INTERVENTION_CHANCE:
            return None, None

        target = random.choice(pending_actions)
        location_filter = (
            Character.location_id.is_(None)
            if turn.location_id is None
            else Character.location_id == turn.location_id
        )
        stmt = (
            sa.select(Player, Character.name)
            .join(Character, Character.player_id == Player.id)
            .where(
                Player.game_id == game.id,
                Player.id != target.player_id,
                Player.is_active.is_(True),
                Character.is_alive.is_(True),
                location_filter,
            )
        )
        candidates = list((await self._session.execute(stmt)).all())
        if not candidates:
            return None, None

        helper, helper_char_name = random.choice(candidates)
        target_character = (
            await self._session.get(Character, target.character_id)
            if target.character_id
            else None
        )
        target_name = target_character.name if target_character else "jemandem"

        intervention_id = interventions.create_waiter(helper.id)
        await self._hub.publish(
            game.id,
            "intervention.offer",
            {
                "intervention_id": str(intervention_id),
                "actor": target_name,
                "action_text": target.text,
                "timeout_seconds": _INTERVENTION_TIMEOUT_SECONDS,
            },
            audience_player_id=helper.id,
        )
        accepted = await interventions.wait_for_response(
            intervention_id, timeout=_INTERVENTION_TIMEOUT_SECONDS
        )
        if not accepted:
            return None, None

        await self._recorder.record(
            game,
            type=ev.INTERVENTION_HELPED,
            summary=f"{helper_char_name} greift {target_name} im letzten Moment unter die Arme.",
            payload={"helper": helper_char_name, "actor": target_name},
            turn_id=turn.id,
            actor_type="character",
            actor_id=helper.id,
        )
        return target.id, helper_char_name

    async def _narrate(
        self, game: Game, turn: Turn, results: list[dict[str, Any]]
    ) -> Turn:
        """Phase B: KI erzaehlt, Backend validiert die Vorschlaege."""
        game = await self._lock_game(game)

        # Wer zu diesem Zug gehoerte, bevor die KI etwas veraendert hat --
        # nicht nur, wer tatsaechlich eine Handlung eingereicht hat. Bei
        # einem von der Spielleitung erzwungenen Aufloesen (/resolve,
        # /skip) kann das auch niemand oder nur ein Teil der Gruppe sein;
        # trotzdem braucht jeder von ihnen anschliessend einen Folgezug.
        location_filter = (
            Character.location_id.is_(None)
            if turn.location_id is None
            else Character.location_id == turn.location_id
        )
        character_ids_before = list(
            (
                await self._session.execute(
                    sa.select(Character.id)
                    .join(Player, Player.id == Character.player_id)
                    .where(
                        Character.game_id == game.id,
                        Character.is_alive.is_(True),
                        Player.is_active.is_(True),
                        location_filter,
                    )
                )
            )
            .scalars()
            .all()
        )

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

        # Wer an diesem Zug beteiligt war, bestimmt die Folgezuege. Im
        # Regelfall bleibt die Gruppe an einem Ort -- ein Folgezug, wie
        # bisher. Sind Charaktere durch character.move auseinandergegangen,
        # bekommt jeder neue Ort seinen eigenen; ist am Zielort schon eine
        # Szene im Gang, reiht sich der Ankommende dort automatisch ein.
        # Tote (z. B. durch diesen Zug gestorbene) Charaktere fallen hier
        # automatisch heraus -- _sync_location_turns filtert selbst nochmal
        # auf is_alive, das Herausfiltern hier dient nur der Vollstaendigkeit.
        character_ids = list(
            (
                await self._session.execute(
                    sa.select(Character.id).where(
                        Character.id.in_(character_ids_before), Character.is_alive.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        synced = await self._sync_location_turns(
            game, character_ids, carry_scene_title=response.scene_title or turn.scene_title
        )
        if not synced:
            # Niemand aus diesem Zug ist noch handlungsfaehig (z. B. alle
            # gestorben) -- die Erzaehlung bleibt am abgeschlossenen Zug.
            synced = [(turn, False)]

        # Die Erzaehlung der KI ist ein einzelner Text fuer den ganzen
        # abgeschlossenen Zug; sie gehoert an den Folgezug am urspruenglichen
        # Ort (oder an den ersten neuen, falls die Gruppe komplett
        # weitergezogen ist). Andere neu entstandene Orte bekommen zunaechst
        # nur den Szenentitel -- ihre eigene Erzaehlung entsteht, sobald dort
        # der naechste Zug aufgeloest wird.
        primary, _ = next(
            ((t, c) for t, c in synced if t.location_id == turn.location_id), synced[0]
        )
        await self._persist_narration(game, primary, response)
        for other, _ in synced:
            if other.id != primary.id:
                other.scene_title = response.scene_title or other.scene_title

        await self._session.commit()
        await self._recorder.flush_to_clients(game.id)
        for started, created in synced:
            if created:
                await self._hub.publish(
                    game.id,
                    "turn.started",
                    {
                        "turn_number": started.number,
                        "turn_id": str(started.id),
                        "location_id": (
                            str(started.location_id) if started.location_id else None
                        ),
                    },
                )

        await self._maybe_summarize(game)
        return primary

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
        """Legt genau einen Sprachausgabe-Auftrag zur Narration an.

        Erzeugt der Server das Audio selbst, bleibt der Auftrag zunaechst
        offen: der Medien-Worker holt ihn ab und meldet die fertige Aufnahme
        anschliessend per WebSocket. Der Spieltisch wartet also nie auf die
        Tonspur. Spricht dagegen das Endgeraet selbst, ist der Auftrag sofort
        fertig und traegt nur den Text.
        """
        settings = game.settings
        if settings is not None and not settings.tts_enabled:
            return
        if settings is not None and settings.audio_playback == "none":
            return

        targets = list(settings.audio_targets or []) if settings else []
        target = targets[0] if targets else "browser"

        effective = await get_effective_tts(self._session, self._settings)

        job = AudioJob(
            game_id=game.id,
            narration_id=narration.id,
            provider=self._tts.name,
            voice=effective.voice,
            speed=effective.speed,
            target=target,
            text=narration.text,
            meta={"mood": mood},
        )

        if self._tts.server_side:
            job.status = "pending"
            self._session.add(job)
            await self._session.flush()
            return

        result = await self._tts.synthesize(
            SpeechRequest(
                text=narration.text, voice=effective.voice, speed=effective.speed, mood=mood
            )
        )
        job.status = result.status
        job.url = result.url
        job.error = result.error
        job.meta = {"mood": mood, **dict(result.meta or {})}
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
                    "playback": settings.audio_playback if settings else "host",
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

