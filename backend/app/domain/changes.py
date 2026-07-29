"""Kanonisches Vokabular fuer Zustandsaenderungen.

Sowohl das Regelwerk als auch die KI duerfen ausschliesslich Aenderungen aus
diesem Vokabular *vorschlagen*. Ob eine Aenderung tatsaechlich uebernommen
wird, entscheidet allein das Backend (siehe ``app.services.state_changes``).

Referenzen auf Spielobjekte erfolgen ueber Namen. Das Backend loest Namen in
IDs auf und lehnt unbekannte Referenzen ab -- so kann die KI keine Fakten
erfinden.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Change(BaseModel):
    """Basisklasse aller Aenderungsvorschlaege."""

    model_config = ConfigDict(extra="ignore")

    reason: str = Field(default="", max_length=500)
    """Begruendung der KI bzw. des Regelwerks -- wird mitprotokolliert."""


class AdjustStat(_Change):
    op: Literal["character.adjust_stat"] = "character.adjust_stat"
    character: str
    stat: str
    delta: int = Field(ge=-9999, le=9999)


class SetCondition(_Change):
    op: Literal["character.set_condition"] = "character.set_condition"
    character: str
    condition: str = Field(max_length=60)
    active: bool = True


class MoveCharacter(_Change):
    op: Literal["character.move"] = "character.move"
    character: str
    location: str


class GrantExperience(_Change):
    op: Literal["character.grant_experience"] = "character.grant_experience"
    character: str
    amount: int = Field(ge=0, le=10000)


class DefineItem(_Change):
    op: Literal["item.define"] = "item.define"
    name: str = Field(max_length=120)
    description: str = ""
    kind: str = "misc"
    weight: int = 0
    value: int = 0
    properties: dict[str, object] = Field(default_factory=dict)


class AddItem(_Change):
    op: Literal["inventory.add_item"] = "inventory.add_item"
    owner: str
    """Name eines Charakters, eines Weltobjekts oder eines Ortes."""
    owner_type: Literal["character", "entity", "location"] = "character"
    item: str
    quantity: int = Field(default=1, ge=1, le=999)


class RemoveItem(_Change):
    op: Literal["inventory.remove_item"] = "inventory.remove_item"
    owner: str
    owner_type: Literal["character", "entity", "location"] = "character"
    item: str
    quantity: int = Field(default=1, ge=1, le=999)


class EquipItem(_Change):
    op: Literal["inventory.equip_item"] = "inventory.equip_item"
    character: str
    item: str
    equipped: bool = True
    slot: str | None = None


class CreateEntity(_Change):
    op: Literal["entity.create"] = "entity.create"
    name: str = Field(max_length=120)
    kind: Literal["npc", "monster", "object", "faction", "riddle"] = "npc"
    description: str = ""
    location: str | None = None
    data: dict[str, object] = Field(default_factory=dict)


class UpdateEntity(_Change):
    op: Literal["entity.update"] = "entity.update"
    entity: str
    description: str | None = None
    is_alive: bool | None = None
    location: str | None = None
    states: dict[str, str] = Field(default_factory=dict)


class CreateLocation(_Change):
    op: Literal["location.create"] = "location.create"
    name: str = Field(max_length=120)
    description: str = ""
    parent: str | None = None
    discovered: bool = True


class DiscoverLocation(_Change):
    op: Literal["location.discover"] = "location.discover"
    location: str


class CreateQuest(_Change):
    op: Literal["quest.create"] = "quest.create"
    title: str = Field(max_length=200)
    description: str = ""
    giver: str | None = None
    is_main: bool = False
    visibility: Literal["public", "party", "private", "secret"] = "public"


class UpdateQuest(_Change):
    op: Literal["quest.update"] = "quest.update"
    quest: str
    status: Literal["hidden", "open", "active", "completed", "failed"]
    note: str = ""
    progress: dict[str, object] = Field(default_factory=dict)


class SetRelationship(_Change):
    op: Literal["relationship.set"] = "relationship.set"
    source: str
    target: str
    kind: str = "attitude"
    value: int = Field(default=0, ge=-100, le=100)
    notes: str = ""


class AssertFact(_Change):
    op: Literal["fact.assert"] = "fact.assert"
    key: str = Field(max_length=120)
    statement: str
    visibility: Literal["public", "party", "private", "secret"] = "public"
    confidence: int = Field(default=100, ge=0, le=100)


class InvalidateFact(_Change):
    op: Literal["fact.invalidate"] = "fact.invalidate"
    key: str


class GrantKnowledge(_Change):
    op: Literal["knowledge.grant"] = "knowledge.grant"
    subject: str
    """Charaktername, Entitaetsname oder ``public``."""
    subject_type: Literal["public", "character", "entity"] = "character"
    content: str
    certainty: Literal["truth", "rumor", "belief", "lie"] = "truth"


StateChange = Annotated[
    AdjustStat
    | SetCondition
    | MoveCharacter
    | GrantExperience
    | DefineItem
    | AddItem
    | RemoveItem
    | EquipItem
    | CreateEntity
    | UpdateEntity
    | CreateLocation
    | DiscoverLocation
    | CreateQuest
    | UpdateQuest
    | SetRelationship
    | AssertFact
    | InvalidateFact
    | GrantKnowledge,
    Field(discriminator="op"),
]

SUPPORTED_OPS: tuple[str, ...] = (
    "character.adjust_stat",
    "character.set_condition",
    "character.move",
    "character.grant_experience",
    "item.define",
    "inventory.add_item",
    "inventory.remove_item",
    "inventory.equip_item",
    "entity.create",
    "entity.update",
    "location.create",
    "location.discover",
    "quest.create",
    "quest.update",
    "relationship.set",
    "fact.assert",
    "fact.invalidate",
    "knowledge.grant",
)
