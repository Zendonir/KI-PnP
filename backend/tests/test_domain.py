"""Unit-Tests der reinen Domaenenlogik (ohne Datenbank und KI)."""

from __future__ import annotations

import random
import uuid

import pytest

from app.domain import dice
from app.domain.rules import (
    ActionRequest,
    CharacterView,
    ClassicRuleSet,
    GritRuleSet,
    StatView,
    ability_modifier,
    get_ruleset,
)


class TestDice:
    def test_parses_full_notation(self) -> None:
        parsed = dice.parse_notation("2d6+3")
        assert (parsed.count, parsed.sides, parsed.modifier) == (2, 6, 3)

    def test_defaults_to_single_die(self) -> None:
        assert dice.parse_notation("d20").count == 1

    def test_parses_negative_modifier(self) -> None:
        assert dice.parse_notation("1d20 - 2").modifier == -2

    @pytest.mark.parametrize("notation", ["", "d", "0d6", "2x6", "1d1", "abc"])
    def test_rejects_invalid_notation(self, notation: str) -> None:
        with pytest.raises(dice.InvalidNotationError):
            dice.parse_notation(notation)

    def test_roll_stays_within_bounds(self) -> None:
        rng = random.Random(7)
        for _ in range(200):
            result = dice.roll("3d6+2", rng=rng)
            assert len(result.rolls) == 3
            assert all(1 <= value <= 6 for value in result.rolls)
            assert result.total == sum(result.rolls) + 2

    def test_bonus_is_added_to_modifier(self) -> None:
        result = dice.roll("1d20+1", bonus=4, rng=random.Random(1))
        assert result.modifier == 5
        assert result.total == result.natural + 5

    def test_natural_twenty_is_critical(self) -> None:
        class AlwaysMax(random.Random):
            def randint(self, a: int, b: int) -> int:  # noqa: D102
                return b

        result = dice.roll("1d20", difficulty=30, rng=AlwaysMax())
        assert result.degree == dice.CRITICAL_SUCCESS

    def test_natural_one_is_critical_failure(self) -> None:
        class AlwaysMin(random.Random):
            def randint(self, a: int, b: int) -> int:  # noqa: D102
                return a

        result = dice.roll("1d20", difficulty=2, rng=AlwaysMin())
        assert result.degree == dice.CRITICAL_FAILURE

    def test_better_picks_higher_total(self) -> None:
        low = dice.roll("1d20", rng=random.Random(1))
        high = dice.roll("1d20+10", rng=random.Random(1))
        assert dice.better(low, high) is high
        assert dice.better(high, low) is high

    def test_success_flag_matches_difficulty(self) -> None:
        result = dice.roll("1d20", difficulty=1, bonus=100, rng=random.Random(3))
        assert result.success is True


def _actor(**overrides: object) -> CharacterView:
    stats = {
        "hp": StatView(20, 20),
        "mana": StatView(10, 10),
        "stamina": StatView(12, 12),
        "strength": StatView(14),
        "dexterity": StatView(10),
        "intelligence": StatView(12),
        "charisma": StatView(8),
    }
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "Testheld",
        "level": 1,
        "is_alive": True,
        "stats": stats,
        "conditions": [],
        "items": ["Fackel"],
        "abilities": [],
    }
    base.update(overrides)
    return CharacterView(**base)  # type: ignore[arg-type]


class TestRules:
    def test_ability_modifier(self) -> None:
        assert ability_modifier(10) == 0
        assert ability_modifier(14) == 2
        assert ability_modifier(7) == -2

    def test_attack_produces_check_and_cost(self) -> None:
        plan = ClassicRuleSet().plan(
            ActionRequest(kind="attack", text="Ich greife an"),
            _actor(),
            difficulty="normal",
            complexity="light",
        )
        assert plan.allowed
        assert plan.check is not None
        assert plan.check.stat == "strength"
        assert plan.check.bonus == 2
        assert plan.costs and plan.costs[0].stat == "stamina"

    def test_wait_needs_no_check_and_no_cost(self) -> None:
        """"Nichts tun" ist immer erlaubt, kostet nichts und braucht keine
        Probe -- es gibt schlicht nichts zu wuerfeln."""
        plan = ClassicRuleSet().plan(
            ActionRequest(kind="wait", text="Ich beobachte die Lage."),
            _actor(),
            difficulty="normal",
            complexity="light",
        )
        assert plan.allowed
        assert plan.check is None
        assert plan.costs == []

    def test_stat_hint_overrides_kind_mapping(self) -> None:
        """Eine frei formulierte Handlung ("custom") wuerfelt sonst immer auf
        Intelligenz -- mit einem gueltigen stat_hint (von der KI-Einschaetzung
        gesetzt) gilt stattdessen dieses Attribut."""
        plan = ClassicRuleSet().plan(
            ActionRequest(kind="custom", text="Ich greife an", stat_hint="strength"),
            _actor(),
            difficulty="normal",
            complexity="light",
        )
        assert plan.check is not None
        assert plan.check.stat == "strength"

    def test_invalid_stat_hint_falls_back_to_kind_mapping(self) -> None:
        plan = ClassicRuleSet().plan(
            ActionRequest(kind="custom", text="Ich ueberlege", stat_hint="nonsense"),
            _actor(),
            difficulty="normal",
            complexity="light",
        )
        assert plan.check is not None
        assert plan.check.stat == "intelligence"

    def test_spell_requires_mana(self) -> None:
        actor = _actor(stats={"mana": StatView(1, 10), "intelligence": StatView(10)})
        plan = ClassicRuleSet().plan(
            ActionRequest(kind="cast", text="Feuerball"),
            actor,
            difficulty="normal",
            complexity="light",
        )
        assert not plan.allowed
        assert "Mana" in plan.reason

    def test_item_must_be_in_inventory(self) -> None:
        plan = ClassicRuleSet().plan(
            ActionRequest(kind="use_item", text="Trank trinken", payload={"item": "Heiltrank"}),
            _actor(),
            difficulty="normal",
            complexity="light",
        )
        assert not plan.allowed
        assert "Inventar" in plan.reason

    def test_known_item_is_accepted(self) -> None:
        plan = ClassicRuleSet().plan(
            ActionRequest(kind="use_item", text="Fackel anzuenden", payload={"item": "fackel"}),
            _actor(),
            difficulty="normal",
            complexity="light",
        )
        assert plan.allowed

    def test_dead_character_cannot_act(self) -> None:
        plan = ClassicRuleSet().plan(
            ActionRequest(kind="attack", text="..."),
            _actor(is_alive=False),
            difficulty="normal",
            complexity="light",
        )
        assert not plan.allowed

    def test_blocking_condition_prevents_action(self) -> None:
        plan = ClassicRuleSet().plan(
            ActionRequest(kind="talk", text="..."),
            _actor(conditions=["bewusstlos"]),
            difficulty="normal",
            complexity="light",
        )
        assert not plan.allowed

    def test_difficulty_and_complexity_shift_target(self) -> None:
        rules = ClassicRuleSet()
        easy = rules.plan(
            ActionRequest(kind="talk", text="x"), _actor(), difficulty="easy", complexity="light"
        )
        deadly = rules.plan(
            ActionRequest(kind="talk", text="x"),
            _actor(),
            difficulty="deadly",
            complexity="crunchy",
        )
        assert easy.check and deadly.check
        assert deadly.check.difficulty > easy.check.difficulty

    def test_grit_ruleset_is_harder(self) -> None:
        request = ActionRequest(kind="attack", text="x")
        classic = ClassicRuleSet().plan(
            request, _actor(), difficulty="normal", complexity="light"
        )
        grit = GritRuleSet().plan(request, _actor(), difficulty="normal", complexity="light")
        assert classic.check and grit.check
        assert grit.check.difficulty == classic.check.difficulty + 2

    def test_critical_failure_costs_health(self) -> None:
        result = dice.DiceResult(
            notation="1d20", rolls=[1], total=1, difficulty=12, success=False,
            degree=dice.CRITICAL_FAILURE,
        )
        effects = ClassicRuleSet().outcome_effects(
            ActionRequest(kind="attack", text="x"), _actor(), result
        )
        assert any(getattr(effect, "stat", "") == "hp" for effect in effects)

    def test_unknown_ruleset_falls_back(self) -> None:
        assert get_ruleset("gibt-es-nicht").name == "classic"

    def test_starting_stats_reflect_class(self) -> None:
        mage = ClassicRuleSet().starting_stats("Magier")
        warrior = ClassicRuleSet().starting_stats("Krieger")
        assert mage["mana"].value > warrior["mana"].value
        assert warrior["strength"].value > mage["strength"].value
