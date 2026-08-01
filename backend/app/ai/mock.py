"""Offline-Spielleiter ohne externes Sprachmodell.

Der Mock-Provider erzeugt regelkonformes JSON aus dem uebergebenen Kontext.
Damit ist die Plattform ohne API-Schluessel vollstaendig spielbar -- und die
Integrationstests laufen deterministisch und kostenlos.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any

from app.ai.base import LLMRequest, LLMResponse
from app.ai.prompts import STALL_ESCALATION_THRESHOLD

_CONTEXT_BLOCK = re.compile(r"```json\s*(.*?)```", re.DOTALL)

_OPENINGS = [
    "Der Wind traegt den Geruch von kaltem Rauch heran.",
    "Ueber euch schliesst sich der Himmel zu einem bleiernen Grau.",
    "Irgendwo in der Ferne schlaegt eine Glocke, dreimal, dann Stille.",
    "Der Boden unter euren Stiefeln gibt nach, feucht und weich.",
]

_BEATS = [
    "Etwas bewegt sich am Rand eures Blickfelds und ist sofort wieder verschwunden.",
    "Eine Spur im Staub fuehrt weiter, als sie sollte.",
    "Ein leises Klopfen antwortet, kaum hoerbar, aus der falschen Richtung.",
    "Der Weg gabelt sich, und beide Richtungen sehen falsch aus.",
]

_PROGRESS_BEATS = [
    "Endlich ein greifbarer Hinweis: Eine frische Spur fuehrt unmissverstaendlich weiter.",
    "Ein Fehler des Gegners verschafft der Gruppe einen entscheidenden Moment.",
    "Ein bisher verschlossener Weg steht ploetzlich offen.",
    "Die Zeit draengt: Ein deutliches Zeichen zwingt zum Handeln, bevor es zu spaet ist.",
]
"""Wird statt eines vagen _BEATS-Satzes verwendet, sobald stall_streak den
Schwellwert erreicht -- konkrete Wendung statt weiterer Atmosphaere, siehe
prompts.build_turn_prompt fuer das Gegenstueck bei einem echten Sprachmodell."""

_SUGGESTION_POOL: list[tuple[str, str, str]] = [
    ("investigate", "Die Umgebung untersuchen", "Vielleicht verraet ein Detail mehr."),
    ("talk", "Das Gespraech suchen", "Worte oeffnen manchmal mehr Tueren als Gewalt."),
    ("sneak", "Sich unbemerkt naehern", "Leise sein kostet Ausdauer, aber spart Blut."),
    ("attack", "Angreifen", "Direkt, laut und gefaehrlich."),
    ("cast", "Magie wirken", "Kostet Mana."),
    ("use_item", "Gegenstand einsetzen", "Ein Blick ins Inventar lohnt sich."),
    ("flee", "Rueckzug antreten", "Ueberleben ist auch ein Ergebnis."),
]


class MockLLMProvider:
    """Erzeugt nachvollziehbare Inhalte ohne externen Dienst."""

    name = "mock"

    def __init__(self, *, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        context = _parse_context(request.prompt)
        builders = {
            "world": self._build_world,
            "turn": self._build_turn,
            "summary": self._build_summary,
            "character": self._build_character,
            "premise": self._build_premise,
        }
        builder = builders.get(request.purpose, self._build_turn)
        return LLMResponse(text=json.dumps(builder(context), ensure_ascii=False), model="mock")

    async def aclose(self) -> None:  # pragma: no cover - nichts freizugeben
        return None

    # -- Bausteine ------------------------------------------------------

    def _characters(self, context: dict[str, Any]) -> list[str]:
        names = [
            str(entry.get("name"))
            for entry in context.get("characters", [])
            if isinstance(entry, dict) and entry.get("name")
        ]
        return names or ["Die Gruppe"]

    def _suggestions(self, context: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
        result: dict[str, list[dict[str, str]]] = {}
        for name in self._characters(context):
            picks = self._random.sample(_SUGGESTION_POOL, k=4)
            result[name] = [
                {"kind": kind, "label": label, "hint": hint} for kind, label, hint in picks
            ]
        return result

    def _build_world(self, context: dict[str, Any]) -> dict[str, Any]:
        settings = context.get("settings", {}) if isinstance(context, dict) else {}
        genre = str(settings.get("genre", "fantasy"))
        world = str(settings.get("world") or "Die Grenzlande von Aschenfurt")
        market = f"{world} - Marktplatz"
        cistern = f"{world} - Alte Zisterne"
        quarter = f"{world} - Handelsviertel"
        gate = f"{world} - Nordtor"
        healer, trader, priest = "Hedda Vorn", "Joran Kessel", "Pater Ilwyn"
        # Bewusst ausschweifend: mehr Orte, NSC, Neben-Quests und Fakten als
        # unbedingt fuer die erste Szene noetig, damit spaeteren Zuegen
        # bereits Vorhandenes zur Verfuegung steht statt improvisiert werden
        # zu muessen (Auftrag in prompts.build_world_prompt).
        changes: list[dict[str, Any]] = [
            {
                "op": "location.create",
                "name": market,
                "description": (
                    f"Ein Platz im Zentrum von {world}. Der Brunnen ist trocken, "
                    "die Staende sind halb abgebaut."
                ),
                "discovered": True,
                "reason": "Startort der Kampagne",
            },
            {
                "op": "location.create",
                "name": cistern,
                "description": "Unter dem Marktplatz, nur ueber einen schmalen Schacht erreichbar.",
                "discovered": False,
                "reason": "Ziel der ersten Quest",
            },
            {
                "op": "location.create",
                "name": quarter,
                "description": (
                    "Enge Gassen mit verrammelten Laeden -- seit Tagen bleiben Karawanen aus."
                ),
                "discovered": False,
                "reason": "Hintergrund fuer die Nebenquest um ausbleibende Lieferungen",
            },
            {
                "op": "location.create",
                "name": gate,
                "description": "Das Nordtor der Stadt, dahinter beginnt die offene Strasse.",
                "discovered": False,
                "reason": "Weiterer Anknuepfungspunkt fuer spaetere Erkundung",
            },
            {
                "op": "entity.create",
                "name": healer,
                "kind": "npc",
                "description": "Brunnenmeisterin, misstrauisch, weiss mehr, als sie zugibt.",
                "location": market,
                "data": {"attitude": "wachsam"},
                "reason": "Auftraggeberin der Hauptquest",
            },
            {
                "op": "entity.create",
                "name": trader,
                "kind": "npc",
                "description": (
                    "Haendler im Handelsviertel, dessen Lieferungen seit Tagen ausbleiben."
                ),
                "location": quarter,
                "data": {"attitude": "besorgt"},
                "reason": "Auftraggeber der ersten Nebenquest",
            },
            {
                "op": "entity.create",
                "name": priest,
                "kind": "npc",
                "description": "Priester am Marktplatz, kennt alte Geschichten ueber die Zisterne.",
                "location": market,
                "data": {"attitude": "zurueckhaltend"},
                "reason": "Auftraggeber der zweiten Nebenquest",
            },
            {
                "op": "quest.create",
                "title": "Das versiegte Wasser",
                "description": (
                    "Findet heraus, warum der Brunnen von "
                    f"{world} seit sieben Tagen trocken liegt."
                ),
                "giver": healer,
                "is_main": True,
                "reason": "Einstiegsquest",
            },
            {
                "op": "quest.create",
                "title": "Vermisste Ware",
                "description": (
                    "Klaert, warum die Karawanen ins Handelsviertel nicht mehr ankommen."
                ),
                "giver": trader,
                "is_main": False,
                "reason": "Nebenquest",
            },
            {
                "op": "quest.create",
                "title": "Der alte Fluch",
                "description": (
                    "Geht dem Geruecht nach, ein Fluch laste seit Generationen auf der Zisterne."
                ),
                "giver": priest,
                "is_main": False,
                "reason": "Nebenquest mit Bezug zum Geheimnis der Hauptquest",
            },
            {
                "op": "fact.assert",
                "key": "well.dry",
                "statement": f"Der Brunnen von {world} ist seit sieben Tagen trocken.",
                "visibility": "public",
                "reason": "Ausgangslage",
            },
            {
                "op": "fact.assert",
                "key": "trade.blocked",
                "statement": "Seit Tagen erreicht keine Karawane mehr das Handelsviertel.",
                "visibility": "public",
                "reason": "Ausgangslage der Nebenquest",
            },
            {
                "op": "fact.assert",
                "key": "cistern.blocked",
                "statement": "Die Zisterne wurde absichtlich zugemauert.",
                "visibility": "secret",
                "reason": "Geheimnis hinter der Hauptquest",
            },
            {
                "op": "fact.assert",
                "key": "curse.rumor",
                "statement": (
                    "Ein alter Fluch soll auf der Zisterne liegen -- deshalb wurde sie "
                    "einst versiegelt."
                ),
                "visibility": "secret",
                "reason": "Geheimnis hinter der Nebenquest um den Fluch",
            },
            {
                "op": "knowledge.grant",
                "subject": "public",
                "subject_type": "public",
                "content": f"Der Brunnen von {world} ist trocken. Niemand weiss, warum.",
                "certainty": "truth",
                "reason": "Oeffentlich bekannt",
            },
            {
                "op": "knowledge.grant",
                "subject": healer,
                "subject_type": "entity",
                "content": "Hedda hat gesehen, wie nachts Steine in die Zisterne geschafft wurden.",
                "certainty": "truth",
                "reason": "NSC-Wissen",
            },
            {
                "op": "knowledge.grant",
                "subject": priest,
                "subject_type": "entity",
                "content": "Pater Ilwyn kennt die alte Geschichte vom Fluch der Zisterne.",
                "certainty": "truth",
                "reason": "NSC-Wissen",
            },
        ]
        for name in self._characters(context):
            changes.append(
                {
                    "op": "character.move",
                    "character": name,
                    "location": market,
                    "reason": "Startaufstellung",
                }
            )
        return {
            "world_summary": (
                f"Ein {genre}-Abenteuer in {world}. Die Gruppe trifft am Marktplatz ein, "
                "waehrend die Stadt langsam verdurstet."
            ),
            "scene_title": "Ankunft am trockenen Brunnen",
            "narration": (
                f"{self._random.choice(_OPENINGS)} {world} empfaengt euch mit leeren Eimern "
                "und misstrauischen Blicken. Am Brunnen steht eine Frau mit verschraenkten "
                "Armen und mustert euch, als waeret ihr die naechste schlechte Nachricht."
            ),
            "public_events": [f"Die Gruppe erreicht {market}."],
            "private_messages": [],
            "suggestions": self._suggestions(context),
            "changes": changes,
            "audio_hint": "ruhig, erwartungsvoll",
        }

    def _build_premise(self, context: dict[str, Any]) -> dict[str, Any]:
        genre = str(context.get("genre") or "fantasy")
        world = str(context.get("world") or "einer noch unbenannten Gegend")
        tone = str(context.get("tone") or "heroic")
        difficulty = str(context.get("difficulty") or "normal")
        return {
            "premise": (
                f"Diese Runde entfuehrt euch in ein {genre}-Abenteuer rund um {world}. "
                f"Der Ton ist {tone}, der Schwierigkeitsgrad {difficulty} -- alles Weitere "
                "zeigt sich erst, sobald die Runde tatsaechlich beginnt."
            )
        }

    def _build_turn(self, context: dict[str, Any]) -> dict[str, Any]:
        results = context.get("action_results", [])
        lines: list[str] = []
        changes: list[dict[str, Any]] = []
        public_events: list[str] = []

        for entry in results if isinstance(results, list) else []:
            if not isinstance(entry, dict):
                continue
            actor = str(entry.get("character") or "Jemand")
            text = str(entry.get("text") or "handelt")
            if not entry.get("allowed", True):
                lines.append(f"{actor} setzt an, doch es gelingt nicht: {entry.get('reason', '')}")
                continue
            degree = str(entry.get("degree") or "")
            if degree in ("critical_success", "success"):
                lines.append(f"{actor} hat Erfolg: {text}")
                public_events.append(f"{actor}: {text} (Erfolg)")
                changes.append(
                    {
                        "op": "knowledge.grant",
                        "subject": actor,
                        "subject_type": "character",
                        "content": f"Erkenntnis aus eigener Handlung: {text}",
                        "certainty": "truth",
                        "reason": "gelungene Probe",
                    }
                )
            elif degree == "partial":
                lines.append(f"{actor} kommt nur halb durch: {text}")
                public_events.append(f"{actor}: {text} (Teilerfolg)")
            elif degree in ("failure", "critical_failure"):
                lines.append(f"{actor} scheitert: {text}")
                public_events.append(f"{actor}: {text} (Fehlschlag)")
            else:
                # Keine Probe noetig (z. B. bewusstes Abwarten) -- weder
                # Erfolg noch Fehlschlag, also auch keine Wertung dazu.
                lines.append(f"{actor}: {text}")
                public_events.append(f"{actor}: {text}")

        if not lines:
            lines.append("Die Gruppe zoegert, und die Szene haelt den Atem an.")

        stall_streak = int(context.get("stall_streak") or 0)
        if stall_streak >= STALL_ESCALATION_THRESHOLD:
            beat = self._random.choice(_PROGRESS_BEATS)
            changes.append(
                {
                    "op": "fact.assert",
                    "key": f"progress.turn.{context.get('turn_number', 0)}",
                    "statement": beat,
                    "visibility": "public",
                    "reason": "Eskalation nach mehreren erfolglosen Zuegen in Folge",
                }
            )
        else:
            beat = self._random.choice(_BEATS)

        return {
            "scene_title": str(context.get("scene_title") or "Fortsetzung"),
            "narration": " ".join(lines) + " " + beat,
            "public_events": public_events,
            "private_messages": [],
            "suggestions": self._suggestions(context),
            "changes": changes,
            "audio_hint": "angespannt",
        }

    def _build_summary(self, context: dict[str, Any]) -> dict[str, Any]:
        events = context.get("events", [])
        highlights = [
            str(entry.get("summary"))
            for entry in events if isinstance(entry, dict) and entry.get("summary")
        ][-6:]
        return {
            "text": " ".join(highlights) or "Bislang ist wenig Berichtenswertes geschehen.",
            "highlights": highlights,
        }

    def _build_character(self, context: dict[str, Any]) -> dict[str, Any]:
        first = ["Kell", "Maren", "Ondra", "Tibor", "Selk", "Yara", "Brun", "Ilva"]
        last = ["Graustein", "vom Moor", "Aschenhand", "Wolkental", "Ohnegleichen"]
        classes = ["Krieger", "Magier", "Schurke", "Barde", "Kleriker"]
        races = ["Mensch", "Elf", "Zwerg", "Halbling", "Ork"]
        return {
            "name": f"{self._random.choice(first)} {self._random.choice(last)}",
            "race": self._random.choice(races),
            "class": self._random.choice(classes),
            "background": (
                "Kam vor Jahren mit nichts als einem Namen und einer Schuld in diese Gegend."
            ),
            "avatar": self._random.choice(["🗡️", "🔮", "🏹", "🎻", "🛡️"]),
            "abilities": ["Zaeher Wille", "Scharfes Auge"],
            "items": ["Reiseproviant", "Fackel"],
        }


def _parse_context(prompt: str) -> dict[str, Any]:
    """Liest den JSON-Kontextblock aus dem Prompt."""
    match = _CONTEXT_BLOCK.search(prompt)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:  # pragma: no cover - defensiv
        return {}
    return parsed if isinstance(parsed, dict) else {}
