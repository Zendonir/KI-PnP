"""Charaktererstellung."""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.base import LLMProvider, LLMRequest, extract_json
from app.ai.contracts import CharacterDraft
from app.core.config import Settings
from app.core.errors import ConflictError, ValidationError
from app.db.models import (
    Ability,
    Character,
    CharacterAbility,
    CharacterStat,
    Game,
    Inventory,
    InventoryItem,
    Item,
    Player,
)
from app.domain.rules import get_ruleset
from app.schemas.api import CharacterCreateRequest
from app.services import events as ev
from app.services.context import ContextBuilder
from app.services.events import EventRecorder

logger = logging.getLogger(__name__)

_DEFAULT_ITEMS = ("Reiseproviant", "Fackel", "Wasserschlauch")


class CharacterService:
    """Erstellt Charaktere -- manuell oder per KI-Vorschlag."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        llm: LLMProvider,
        recorder: EventRecorder,
    ) -> None:
        self._session = session
        self._settings = settings
        self._llm = llm
        self._recorder = recorder

    async def create(
        self, game: Game, player: Player, request: CharacterCreateRequest
    ) -> Character:
        """Legt den Charakter eines Spielers an."""
        existing = await self._session.execute(
            sa.select(Character).where(Character.player_id == player.id)
        )
        if existing.scalars().first() is not None:
            raise ConflictError("Dieser Spieler hat bereits einen Charakter.")

        draft = await self._resolve_draft(game, request)
        if not draft.name.strip():
            raise ValidationError("Der Charakter braucht einen Namen.")

        clash = await self._session.execute(
            sa.select(Character).where(
                Character.game_id == game.id,
                sa.func.lower(Character.name) == draft.name.strip().lower(),
            )
        )
        if clash.scalars().first() is not None:
            raise ConflictError(f"Der Name {draft.name!r} ist in dieser Runde bereits vergeben.")

        character = Character(
            game_id=game.id,
            player_id=player.id,
            name=draft.name.strip(),
            race=draft.race,
            char_class=draft.char_class,
            background=draft.background,
            avatar=draft.avatar or "🎲",
            conditions=[],
        )
        self._session.add(character)
        await self._session.flush()

        ruleset = get_ruleset(game.settings.ruleset if game.settings else "classic")
        for key, stat in ruleset.starting_stats(character.char_class).items():
            self._session.add(
                CharacterStat(
                    character_id=character.id,
                    key=key,
                    value=stat.value,
                    max_value=stat.max_value,
                )
            )

        await self._attach_abilities(game, character, draft.abilities)
        await self._attach_items(game, character, draft.items or list(_DEFAULT_ITEMS))
        await self._session.flush()
        await self._session.refresh(character)

        await self._recorder.record(
            game,
            type=ev.CHARACTER_CREATED,
            summary=f"{character.name} ({character.char_class}) tritt der Gruppe bei.",
            payload={
                "character_id": str(character.id),
                "name": character.name,
                "class": character.char_class,
                "race": character.race,
            },
            actor_type="player",
            actor_id=player.id,
        )
        return character

    async def _resolve_draft(
        self, game: Game, request: CharacterCreateRequest
    ) -> CharacterDraft:
        """Nimmt die Spielereingabe oder laesst die KI einen Vorschlag machen."""
        needs_ai = request.randomize or not request.name.strip()
        if not needs_ai:
            return CharacterDraft(
                name=request.name,
                race=request.race,
                **{"class": request.char_class},
                background=request.background,
                avatar=request.avatar,
                abilities=[],
                items=list(_DEFAULT_ITEMS),
            )

        builder = ContextBuilder(self._session, game, self._settings)
        context = await builder.build_character_context()
        try:
            response = await self._llm.complete(
                LLMRequest(
                    system=prompts.system_prompt(game.settings.language if game.settings else "de"),
                    prompt=prompts.build_character_prompt(context),
                    max_tokens=1500,
                    purpose="character",
                )
            )
            draft = CharacterDraft.model_validate(extract_json(response.text))
        except Exception as exc:  # noqa: BLE001 - Charaktererstellung darf nie blockieren
            logger.warning("Charaktergenerierung fehlgeschlagen (%s), nutze Rueckfallwerte.", exc)
            draft = CharacterDraft(
                name=request.name or "Namenlose Gestalt",
                race=request.race or "Mensch",
                **{"class": request.char_class or "Abenteurer"},
                background=request.background,
                avatar=request.avatar or "🎲",
                items=list(_DEFAULT_ITEMS),
            )

        # Vom Spieler gesetzte Felder haben Vorrang vor dem KI-Vorschlag.
        if request.name.strip():
            draft.name = request.name.strip()
        if request.race.strip():
            draft.race = request.race.strip()
        if request.char_class.strip():
            draft.char_class = request.char_class.strip()
        if request.background.strip():
            draft.background = request.background.strip()
        if request.avatar.strip():
            draft.avatar = request.avatar.strip()
        return draft

    async def _attach_abilities(
        self, game: Game, character: Character, names: list[str]
    ) -> None:
        for name in names[:6]:
            clean = name.strip()
            if not clean:
                continue
            stmt = sa.select(Ability).where(
                Ability.game_id == game.id, sa.func.lower(Ability.name) == clean.lower()
            )
            ability = (await self._session.execute(stmt)).scalars().first()
            if ability is None:
                ability = Ability(game_id=game.id, name=clean, description="")
                self._session.add(ability)
                await self._session.flush()
            self._session.add(
                CharacterAbility(character_id=character.id, ability_id=ability.id)
            )

    async def _attach_items(self, game: Game, character: Character, names: list[str]) -> None:
        inventory = Inventory(
            game_id=game.id, owner_type="character", owner_id=character.id
        )
        self._session.add(inventory)
        await self._session.flush()
        for name in names[:10]:
            clean = name.strip()
            if not clean:
                continue
            stmt = sa.select(Item).where(
                Item.game_id == game.id, sa.func.lower(Item.name) == clean.lower()
            )
            item = (await self._session.execute(stmt)).scalars().first()
            if item is None:
                item = Item(game_id=game.id, name=clean, description="", kind="misc")
                self._session.add(item)
                await self._session.flush()
            self._session.add(
                InventoryItem(inventory_id=inventory.id, item_id=item.id, quantity=1)
            )
