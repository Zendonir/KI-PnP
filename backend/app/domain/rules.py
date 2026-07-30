"""Regelwerk-Engine.

Das Regelwerk entscheidet, ob eine Handlung ueberhaupt moeglich ist, welche
Probe gewuerfelt wird und welche mechanischen Kosten entstehen. Es ist reine
Domaenenlogik: keine Datenbank, keine KI, kein Zufall (der Wurf wird von
``app.domain.dice`` erledigt und hier nur ausgewertet).

Neue Regelwerke (D&D, Cthulhu, Shadowrun ...) werden durch Implementieren des
``RuleSet``-Protokolls und Registrieren in ``RULESETS`` ergaenzt.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.domain import changes as ch
from app.domain.dice import CRITICAL_FAILURE, CRITICAL_SUCCESS, DiceResult

# Standard-Handlungsarten, die das Frontend als Vorschlaege anbietet.
ACTION_KINDS: tuple[str, ...] = (
    "attack",
    "investigate",
    "talk",
    "sneak",
    "cast",
    "use_item",
    "flee",
    "custom",
)

# Die vier Grundattribute, gegen die gewuerfelt werden kann.
KNOWN_STATS: tuple[str, ...] = ("strength", "dexterity", "intelligence", "charisma")

DIFFICULTY_TARGETS: dict[str, int] = {
    "story": 8,
    "easy": 10,
    "normal": 12,
    "hard": 15,
    "deadly": 18,
}


@dataclass(slots=True)
class StatView:
    """Ein Charakterwert mit optionalem Maximum."""

    value: int
    max_value: int | None = None


@dataclass(slots=True)
class CharacterView:
    """Schreibgeschuetzte Sicht auf einen Charakter fuer die Regelpruefung."""

    id: uuid.UUID
    name: str
    level: int = 1
    is_alive: bool = True
    stats: dict[str, StatView] = field(default_factory=dict)
    conditions: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    abilities: list[str] = field(default_factory=list)

    def stat(self, key: str) -> int:
        entry = self.stats.get(key)
        return entry.value if entry else 0

    def has_item(self, name: str) -> bool:
        target = name.strip().casefold()
        return any(item.strip().casefold() == target for item in self.items)


@dataclass(slots=True)
class ActionRequest:
    """Was ein Spieler tun moechte."""

    kind: str
    text: str
    target_ref: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
    stat_hint: str | None = None
    """Von der KI vorgeschlagenes Attribut fuer eine frei formulierte
    Handlung (kind == "custom"). Ungueltige oder fehlende Werte fallen auf
    die feste Zuordnung nach Handlungsart zurueck."""


@dataclass(slots=True)
class CheckSpec:
    """Beschreibung der zu wuerfelnden Probe."""

    stat: str
    notation: str
    difficulty: int
    bonus: int
    reason: str


@dataclass(slots=True)
class ActionPlan:
    """Ergebnis der Regelpruefung vor dem Wurf."""

    allowed: bool
    reason: str = ""
    check: CheckSpec | None = None
    costs: list[ch.StateChange] = field(default_factory=list)


class RuleSet(Protocol):
    """Vertrag eines Regelmoduls."""

    name: str

    def starting_stats(self, char_class: str) -> dict[str, StatView]:
        """Startwerte fuer einen neuen Charakter."""

    def plan(
        self, request: ActionRequest, actor: CharacterView, *, difficulty: str, complexity: str
    ) -> ActionPlan:
        """Prueft Voraussetzungen und legt die Probe fest."""

    def outcome_effects(
        self, request: ActionRequest, actor: CharacterView, result: DiceResult | None
    ) -> list[ch.StateChange]:
        """Mechanische Folgen des Wurfes (ohne narrative Interpretation)."""


def ability_modifier(value: int) -> int:
    """Klassischer Attributsmodifikator."""
    return (value - 10) // 2


class ClassicRuleSet:
    """Leichtgewichtiges, generisches d20-Regelwerk.

    Bewusst systemneutral gehalten, damit es fuer Fantasy, Sci-Fi und Horror
    gleichermaszen funktioniert.
    """

    name = "classic"

    _STAT_FOR_KIND: dict[str, str] = {
        "attack": "strength",
        "investigate": "intelligence",
        "talk": "charisma",
        "sneak": "dexterity",
        "cast": "intelligence",
        "use_item": "dexterity",
        "flee": "dexterity",
        "custom": "intelligence",
    }

    _COSTS: dict[str, tuple[str, int]] = {
        "attack": ("stamina", 1),
        "cast": ("mana", 3),
        "sneak": ("stamina", 1),
        "flee": ("stamina", 2),
    }

    _BLOCKING_CONDITIONS = ("bewusstlos", "unconscious", "gelaehmt", "paralyzed", "tot", "dead")

    def starting_stats(self, char_class: str) -> dict[str, StatView]:
        base = {
            "hp": StatView(20, 20),
            "mana": StatView(10, 10),
            "stamina": StatView(12, 12),
            "strength": StatView(10),
            "dexterity": StatView(10),
            "intelligence": StatView(10),
            "charisma": StatView(10),
        }
        bumps: dict[str, dict[str, int]] = {
            "krieger": {"strength": 4, "hp": 6},
            "warrior": {"strength": 4, "hp": 6},
            "magier": {"intelligence": 4, "mana": 8},
            "mage": {"intelligence": 4, "mana": 8},
            "schurke": {"dexterity": 4, "stamina": 4},
            "rogue": {"dexterity": 4, "stamina": 4},
            "barde": {"charisma": 4, "mana": 4},
            "bard": {"charisma": 4, "mana": 4},
            "kleriker": {"charisma": 2, "mana": 6, "hp": 2},
            "cleric": {"charisma": 2, "mana": 6, "hp": 2},
        }
        for stat, bonus in bumps.get(char_class.strip().casefold(), {}).items():
            entry = base[stat]
            entry.value += bonus
            if entry.max_value is not None:
                entry.max_value += bonus
        return base

    def plan(
        self, request: ActionRequest, actor: CharacterView, *, difficulty: str, complexity: str
    ) -> ActionPlan:
        if not actor.is_alive:
            return ActionPlan(allowed=False, reason="Der Charakter ist nicht handlungsfaehig.")

        blocking = [
            condition
            for condition in actor.conditions
            if condition.strip().casefold() in self._BLOCKING_CONDITIONS
        ]
        if blocking:
            return ActionPlan(
                allowed=False, reason=f"Zustand verhindert die Handlung: {', '.join(blocking)}."
            )

        kind = request.kind if request.kind in ACTION_KINDS else "custom"

        if kind == "use_item":
            item = str(request.payload.get("item") or request.target_ref or "").strip()
            if not item:
                return ActionPlan(allowed=False, reason="Es wurde kein Gegenstand angegeben.")
            if not actor.has_item(item):
                return ActionPlan(
                    allowed=False, reason=f"'{item}' befindet sich nicht im Inventar."
                )

        costs: list[ch.StateChange] = []
        cost = self._COSTS.get(kind)
        if cost is not None:
            stat_key, amount = cost
            available = actor.stat(stat_key)
            if available < amount:
                label = "Mana" if stat_key == "mana" else "Ausdauer"
                return ActionPlan(
                    allowed=False,
                    reason=f"Nicht genug {label} ({available}/{amount}).",
                )
            costs.append(
                ch.AdjustStat(
                    character=actor.name,
                    stat=stat_key,
                    delta=-amount,
                    reason=f"Kosten fuer Handlung '{kind}'",
                )
            )

        stat_key = (
            request.stat_hint
            if request.stat_hint in KNOWN_STATS
            else self._STAT_FOR_KIND.get(kind, "intelligence")
        )
        target = DIFFICULTY_TARGETS.get(difficulty, DIFFICULTY_TARGETS["normal"])
        if complexity == "crunchy":
            target += 1
        elif complexity == "narrative":
            target -= 1

        bonus = ability_modifier(actor.stat(stat_key)) + (actor.level - 1) // 2
        check = CheckSpec(
            stat=stat_key,
            notation="1d20",
            difficulty=target,
            bonus=bonus,
            reason=f"{kind} ({stat_key})",
        )
        return ActionPlan(allowed=True, check=check, costs=costs)

    def outcome_effects(
        self, request: ActionRequest, actor: CharacterView, result: DiceResult | None
    ) -> list[ch.StateChange]:
        if result is None or result.degree not in (CRITICAL_FAILURE, CRITICAL_SUCCESS):
            return []
        effects: list[ch.StateChange] = []
        if result.degree == CRITICAL_FAILURE and request.kind in ("attack", "sneak", "flee"):
            effects.append(
                ch.AdjustStat(
                    character=actor.name,
                    stat="hp",
                    delta=-2,
                    reason="Patzer bei koerperlicher Handlung",
                )
            )
        if result.degree == CRITICAL_FAILURE and request.kind == "cast":
            effects.append(
                ch.AdjustStat(
                    character=actor.name, stat="mana", delta=-2, reason="Magischer Patzer"
                )
            )
        if result.degree == CRITICAL_SUCCESS:
            effects.append(
                ch.GrantExperience(character=actor.name, amount=10, reason="Kritischer Erfolg")
            )
        return effects


class GritRuleSet(ClassicRuleSet):
    """Haertere Variante fuer Horror-Kampagnen: hoehere Proben, weniger Puffer."""

    name = "grit"

    def starting_stats(self, char_class: str) -> dict[str, StatView]:
        stats = super().starting_stats(char_class)
        stats["hp"] = StatView(max(6, stats["hp"].value - 6), stats["hp"].max_value)
        if stats["hp"].max_value is not None:
            stats["hp"].max_value = stats["hp"].value
        return stats

    def plan(
        self, request: ActionRequest, actor: CharacterView, *, difficulty: str, complexity: str
    ) -> ActionPlan:
        plan = super().plan(request, actor, difficulty=difficulty, complexity=complexity)
        if plan.check is not None:
            plan.check.difficulty += 2
        return plan


RULESETS: dict[str, RuleSet] = {
    ClassicRuleSet.name: ClassicRuleSet(),
    GritRuleSet.name: GritRuleSet(),
}


def get_ruleset(name: str) -> RuleSet:
    """Liefert das Regelmodul; faellt auf ``classic`` zurueck."""
    return RULESETS.get(name, RULESETS["classic"])
