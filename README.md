# KI-PnP

Docker-basierte Multiplayer-Plattform für ein KI-gestütztes Pen-&-Paper-Rollenspiel.

## Kernprinzipien

- PostgreSQL ist die maßgebliche Quelle des Spielzustands.
- Jede Spielerhandlung und jede Zustandsänderung wird dauerhaft als Ereignis gespeichert.
- Das Backend validiert Regeln und Änderungen.
- Die KI erzählt, bewertet Ergebnisse und liefert ausschließlich strukturierte Änderungsvorschläge.
- Öffentliche Informationen, private Spielerinformationen und tatsächliche Weltfakten werden strikt getrennt.
- Das Spiel muss auch nach sehr langen Kampagnen konsistent fortgesetzt werden können.

## Zielarchitektur

- FastAPI-Backend
- React/TypeScript-PWA
- PostgreSQL
- WebSockets für Echtzeit-Synchronisation
- austauschbare LLM- und Text-to-Speech-Anbieter
- Docker Compose für den vollständigen Betrieb

## Geplanter Spielablauf

1. Host erstellt eine Spielrunde.
2. Spieler treten über einen QR-Code bei.
3. Charaktere werden erstellt oder generiert.
4. Die KI erzeugt Welt, Szene und individuelle Handlungsmöglichkeiten.
5. Spieler wählen Vorschläge oder geben Freitext ein.
6. Das Backend prüft Handlungen und würfelt regelbasiert.
7. Die KI liefert Narration und strukturierte Änderungsvorschläge.
8. Das Backend validiert und speichert Ereignisse, Fakten und Zustände atomar.
9. Die Erzählung wird als Text und optional per TTS ausgegeben.

## Status

Projektinitialisierung. Die erste Ausbaustufe umfasst Backend, Datenbankmodell, Event-Log, Docker Compose und grundlegende Spiel-API.
