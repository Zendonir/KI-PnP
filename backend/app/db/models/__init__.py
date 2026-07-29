"""Alle ORM-Modelle.

Der Import hier stellt sicher, dass Alembic saemtliche Tabellen kennt.
"""

from app.db.base import Base
from app.db.models.character import (
    Ability,
    Character,
    CharacterAbility,
    CharacterStat,
    Inventory,
    InventoryItem,
    Item,
)
from app.db.models.game import Game, GameSettings, Player
from app.db.models.media import AudioJob, Image
from app.db.models.quest import Quest, QuestState
from app.db.models.turn import (
    Action,
    DiceRoll,
    Event,
    Narration,
    SceneSummary,
    Turn,
)
from app.db.models.world import (
    EntityState,
    Fact,
    Knowledge,
    Location,
    Relationship,
    WorldEntity,
)

__all__ = [
    "Ability",
    "Action",
    "AudioJob",
    "Base",
    "Character",
    "CharacterAbility",
    "CharacterStat",
    "DiceRoll",
    "EntityState",
    "Event",
    "Fact",
    "Game",
    "GameSettings",
    "Image",
    "Inventory",
    "InventoryItem",
    "Item",
    "Knowledge",
    "Location",
    "Narration",
    "Player",
    "Quest",
    "QuestState",
    "Relationship",
    "SceneSummary",
    "Turn",
    "WorldEntity",
]
