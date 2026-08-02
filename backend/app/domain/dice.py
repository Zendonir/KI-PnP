"""Wuerfelmechanik.

Reine Domaenenlogik ohne Datenbank- oder KI-Abhaengigkeiten. Wuerfe werden
ausschliesslich hier berechnet; die KI erfaehrt nur das Ergebnis.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

_NOTATION = re.compile(r"^\s*(\d{1,2})?d(\d{1,3})\s*([+-]\s*\d{1,3})?\s*$", re.IGNORECASE)

CRITICAL_SUCCESS = "critical_success"
SUCCESS = "success"
PARTIAL = "partial"
FAILURE = "failure"
CRITICAL_FAILURE = "critical_failure"


class InvalidNotationError(ValueError):
    """Die Wuerfelnotation ist ungueltig."""


@dataclass(frozen=True, slots=True)
class DiceNotation:
    """Zerlegte Wuerfelnotation, z. B. ``2d6+3``."""

    count: int
    sides: int
    modifier: int

    def __str__(self) -> str:
        sign = "+" if self.modifier >= 0 else "-"
        suffix = f"{sign}{abs(self.modifier)}" if self.modifier else ""
        return f"{self.count}d{self.sides}{suffix}"


@dataclass(frozen=True, slots=True)
class DiceResult:
    """Ergebnis eines Wurfes."""

    notation: str
    rolls: list[int] = field(default_factory=list)
    modifier: int = 0
    total: int = 0
    difficulty: int | None = None
    success: bool | None = None
    degree: str = ""
    reason: str = ""

    @property
    def natural(self) -> int:
        """Summe der Wuerfelaugen ohne Modifikator."""
        return sum(self.rolls)


def parse_notation(notation: str) -> DiceNotation:
    """Zerlegt eine Wuerfelnotation.

    >>> parse_notation("2d6+3")
    DiceNotation(count=2, sides=6, modifier=3)
    """
    match = _NOTATION.match(notation)
    if not match:
        raise InvalidNotationError(f"Ungueltige Wuerfelnotation: {notation!r}")
    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    if count < 1 or sides < 2:
        raise InvalidNotationError(f"Ungueltige Wuerfelnotation: {notation!r}")
    raw_modifier = (match.group(3) or "0").replace(" ", "")
    return DiceNotation(count=count, sides=sides, modifier=int(raw_modifier))


def roll(
    notation: str,
    *,
    difficulty: int | None = None,
    bonus: int = 0,
    reason: str = "",
    rng: random.Random | None = None,
) -> DiceResult:
    """Wuerfelt und bewertet gegen einen optionalen Schwierigkeitsgrad.

    ``bonus`` ist ein zusaetzlicher, aus Charakterwerten abgeleiteter
    Modifikator und wird auf den Modifikator der Notation addiert.
    """
    generator = rng or random.SystemRandom()
    parsed = parse_notation(notation)
    rolls = [generator.randint(1, parsed.sides) for _ in range(parsed.count)]
    modifier = parsed.modifier + bonus
    total = sum(rolls) + modifier

    success: bool | None = None
    degree = ""
    if difficulty is not None:
        success = total >= difficulty
        degree = _degree(rolls, parsed.sides, total, difficulty)
    return DiceResult(
        notation=str(parsed),
        rolls=rolls,
        modifier=modifier,
        total=total,
        difficulty=difficulty,
        success=success,
        degree=degree,
        reason=reason,
    )


def better(first: DiceResult, second: DiceResult) -> DiceResult:
    """Waehlt bei Vorteil (zwei unabhaengige Wuerfe) das staerkere Ergebnis."""
    return second if second.total > first.total else first


def _degree(rolls: list[int], sides: int, total: int, difficulty: int) -> str:
    """Bewertet den Erfolgsgrad eines Wurfes."""
    if len(rolls) == 1 and sides == 20:
        if rolls[0] == 20:
            return CRITICAL_SUCCESS
        if rolls[0] == 1:
            return CRITICAL_FAILURE
    delta = total - difficulty
    if delta >= 10:
        return CRITICAL_SUCCESS
    if delta >= 0:
        return SUCCESS
    if delta >= -3:
        return PARTIAL
    if delta <= -10:
        return CRITICAL_FAILURE
    return FAILURE
