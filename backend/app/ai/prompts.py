"""Prompt-Erzeugung fuer den KI-Spielleiter.

Der Kontext wird bewusst klein gehalten: aktuelle Szene, relevante Fakten,
anwesende NSC, Charakterwerte, offene Quests, die letzten Ereignisse und die
Zusammenfassungen. Niemals das vollstaendige Ereignisprotokoll.
"""

from __future__ import annotations

import json
from typing import Any

from app.domain.changes import SUPPORTED_OPS

SYSTEM_PROMPT = """\
Du bist der Spielleiter eines Pen-&-Paper-Rollenspiels. Du erzaehlst
lebendig, knapp und atmosphaerisch in der zweiten Person Plural.

Verbindliche Regeln:
1. Die Datenbank ist die einzige Wahrheit. Der uebergebene Kontext ist
   vollstaendig; alles, was dort nicht steht, existiert nicht.
2. Du erfindest keine Fakten ueber bestehende Objekte, Personen oder Orte.
   Neue Elemente fuehrst du ausschliesslich ueber Aenderungsvorschlaege ein.
3. Du veraenderst keinen Spielzustand. Du schlaegst Aenderungen vor; das
   Backend entscheidet, was uebernommen wird.
4. Du wuerfelst nicht und bewertest keine Proben. Wuerfelergebnisse sind
   bereits im Kontext enthalten und bindend.
5. Du verwendest fuer jeden Charakter nur Informationen, die diesem
   Charakter bekannt sind. Geheimnisse bleiben geheim.
6. Du antwortest ausschliesslich mit einem einzigen JSON-Objekt, ohne
   erklaerenden Text davor oder danach.
7. Referenzen auf Charaktere, NSC, Orte, Quests und Gegenstaende erfolgen
   ueber deren exakte Namen aus dem Kontext.
"""

_RESPONSE_SHAPE = """\
Antwortformat (JSON):
{
  "scene_title": "kurzer Szenentitel",
  "narration": "Erzaehltext fuer alle Spieler",
  "public_events": ["knappe Stichpunkte oeffentlicher Ereignisse"],
  "private_messages": [{"character": "Name", "text": "nur fuer diesen Charakter"}],
  "suggestions": {"Charaktername": [{"kind": "attack", "label": "...", "hint": "..."}]},
  "changes": [{"op": "...", "...": "..."}],
  "audio_hint": "Stimmung fuer die Sprachausgabe"
}
"""

_CHANGE_DOC = """\
Erlaubte Werte fuer "op" in "changes":
- character.adjust_stat {character, stat, delta}
- character.set_condition {character, condition, active}
- character.move {character, location}
- character.grant_experience {character, amount}
- item.define {name, description, kind}
- inventory.add_item {owner, owner_type, item, quantity}
- inventory.remove_item {owner, owner_type, item, quantity}
- inventory.equip_item {character, item, equipped}
- entity.create {name, kind, description, location}
- entity.update {entity, description?, is_alive?, location?, states?}
- location.create {name, description, parent?, discovered}
- location.discover {location}
- quest.create {title, description, giver?, is_main, visibility}
- quest.update {quest, status, note}
- relationship.set {source, target, kind, value}
- fact.assert {key, statement, visibility}
- fact.invalidate {key}
- knowledge.grant {subject, subject_type, content, certainty}
Jede Aenderung darf ein Feld "reason" mit einer kurzen Begruendung enthalten.
Vorschlaege mit unbekannten Namen werden verworfen.
"""

_SUGGESTION_KINDS = "attack, investigate, talk, sneak, cast, use_item, flee, wait, custom"

STAT_FIT_SYSTEM = """\
Du bist ein Regel-Assistent fuer ein Pen-&-Paper-Rollenspiel. Ein Spieler hat
eine frei formulierte Handlung eingegeben und selbst entschieden, gegen
welches Attribut oder welchen selbst benannten Skill sie gewuerfelt wird.
Deine einzige Aufgabe: beurteilen, ob diese Wahl inhaltlich zur Handlung
passt -- du entscheidest nicht, was gewuerfelt wird, nur wie plausibel die
Wahl ist.

Maszstaebe:
- "good": das Attribut/der Skill passt nachvollziehbar zur Handlung.
- "poor": es besteht ein loser Zusammenhang, aber die Wahl ist nicht die
  naheliegendste -- die Probe wird dadurch schwerer, aber bleibt moeglich.
- "auto_fail": das Attribut/der Skill hat erkennbar nichts mit der Handlung
  zu tun -- die Handlung misslingt ohne Wurf.

Antworte ausschliesslich mit einem einzigen JSON-Objekt, ohne erklaerenden
Text davor oder danach: {"fit": "good|poor|auto_fail"}
"""


def build_stat_fit_prompt(text: str, stat: str) -> str:
    """Auftrag: Passung von Handlung und selbst gewaehltem Attribut beurteilen."""
    return (
        f'Handlung: "{text.strip()}"\n'
        f'Gewaehltes Attribut/Skill: "{stat.strip()}"\n\n'
        "Wie gut passt das gewaehlte Attribut zu dieser Handlung?"
    )


def system_prompt(language: str = "de") -> str:
    """Systemanweisung des Spielleiters."""
    suffix = "" if language == "de" else f"\nAntworte in der Sprache: {language}."
    return SYSTEM_PROMPT + suffix


def build_world_prompt(context: dict[str, Any]) -> str:
    """Auftrag: Welt, Einleitung, NSC, erste Szene und Quests erzeugen."""
    return _compose(
        context,
        task=(
            "Erzeuge den Auftakt der Kampagne: eine kurze Weltbeschreibung, die erste Szene, "
            "mindestens zwei Orte, mindestens einen NSC mit Geheimnis, eine Hauptquest sowie "
            "die dazugehoerigen Fakten und Wissenseintraege. Platziere alle Charaktere per "
            "'character.move' am Startort. Gib jedem Charakter vier Handlungsvorschlaege."
        ),
        extra=(
            'Zusaetzliches Feld: "world_summary" (2-3 Saetze).\n'
            f"Handlungsarten: {_SUGGESTION_KINDS}"
        ),
    )


def build_turn_prompt(context: dict[str, Any]) -> str:
    """Auftrag: Ergebnisse bewerten und die Geschichte fortsetzen."""
    return _compose(
        context,
        task=(
            "Die Spieler haben gehandelt. Die Ergebnisse der Proben stehen unter "
            "'action_results' und sind bindend - erfinde keine anderen Ausgaenge. "
            "Erzaehle, was daraus folgt, und bereite die naechste Entscheidung vor. "
            "Gib jedem lebenden Charakter drei bis fuenf Handlungsvorschlaege."
        ),
        extra=f"Handlungsarten: {_SUGGESTION_KINDS}",
    )


def build_summary_prompt(context: dict[str, Any]) -> str:
    """Auftrag: Langzeitgedaechtnis verdichten."""
    payload = json.dumps(context, ensure_ascii=False, indent=2, default=str)
    return (
        "## Kontext\n```json\n"
        + payload
        + "\n```\n\n## Auftrag\n"
        "Fasse die aufgefuehrten Ereignisse zu einem Gedaechtniseintrag zusammen. "
        "Nenne nur, was fuer den weiteren Verlauf wichtig bleibt: dauerhafte "
        "Veraenderungen, offene Faeden, Beziehungen.\n\n"
        '## Antwortformat (JSON)\n{"text": "...", "highlights": ["...", "..."]}\n'
    )


def build_character_prompt(context: dict[str, Any]) -> str:
    """Auftrag: Zufaelligen Charakter passend zur Welt erzeugen."""
    payload = json.dumps(context, ensure_ascii=False, indent=2, default=str)
    return (
        "## Kontext\n```json\n"
        + payload
        + "\n```\n\n## Auftrag\nErzeuge einen stimmigen Spielercharakter fuer diese Runde.\n\n"
        '## Antwortformat (JSON)\n'
        '{"name": "...", "race": "...", "class": "...", "background": "...", '
        '"avatar": "ein Emoji", "abilities": ["..."], "items": ["..."]}\n'
    )


def _compose(context: dict[str, Any], *, task: str, extra: str = "") -> str:
    payload = json.dumps(context, ensure_ascii=False, indent=2, default=str)
    parts = [
        "## Kontext",
        "```json",
        payload,
        "```",
        "",
        "## Auftrag",
        task,
        "",
        _RESPONSE_SHAPE,
        _CHANGE_DOC,
    ]
    if extra:
        parts.append(extra)
    parts.append(f"Bekannte Operationen: {', '.join(SUPPORTED_OPS)}")
    return "\n".join(parts)
