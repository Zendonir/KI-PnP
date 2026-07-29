# KI-PnP

Docker-basierte Multiplayer-Plattform für ein KI-gestütztes Pen-&-Paper-Rollenspiel.
Alle Spieler verbinden sich über den Browser ihres Smartphones, die KI übernimmt
die Spielleitung, und der gesamte Spielzustand liegt dauerhaft in PostgreSQL.

```
docker compose up -d --build      # startet die komplette Plattform
open http://localhost:8080        # Runde erstellen, QR-Code zeigen, losspielen
```

Ohne weitere Konfiguration läuft alles offline: der mitgelieferte
Offline-Spielleiter (`AI_PROVIDER=mock`) erzeugt Welt, Szenen und Vorschläge
ohne API-Schlüssel. Für echte KI genügt ein Eintrag in `.env`.

---

## Kernprinzipien

Diese Regeln sind im Code durchgesetzt, nicht nur dokumentiert:

| Prinzip | Umsetzung |
|---|---|
| Die Datenbank ist die einzige Wahrheit | Jeder Zustand liegt in PostgreSQL; das Frontend hält keine Spielwahrheit vor. |
| Das Backend verwaltet die Spiellogik | `app/domain/rules.py` entscheidet über Machbarkeit, Proben und Kosten. |
| Die KI würfelt nicht | Würfe entstehen in `app/domain/dice.py`, *bevor* die KI gefragt wird; sie erhält das Ergebnis als bindende Vorgabe. |
| Die KI ändert keine Daten | Sie liefert nur Vorschläge; `app/services/state_changes.py` validiert und entscheidet. |
| Nichts geht verloren | `events` ist ein reines Anhänge-Protokoll mit lückenloser Sequenznummer. |
| Geheimnisse bleiben geheim | Fakten und Wissen sind nach Sichtbarkeit getrennt; die API filtert pro Spieler. |

## Architektur

```
Smartphone (PWA)  ─┐
Smartphone (PWA)  ─┼─► Caddy ─┬─► Frontend (React/Vite, statisch via nginx)
Smartphone (PWA)  ─┘          └─► Backend (FastAPI)
                                    ├─► PostgreSQL   Spielzustand + Ereignisse
                                    ├─► Redis        Echtzeit über mehrere Instanzen
                                    ├─► LLM-Anbieter mock | anthropic | openai | ollama
                                    └─► TTS-Anbieter none | browser | openai
```

Das Backend folgt einer geschichteten Architektur:

```
app/api        HTTP- und WebSocket-Endpunkte (dünn, keine Spiellogik)
app/services   Anwendungsfälle: Runde, Charakter, Zug, Ereignisse, Kontext
app/domain     reine Regeln: Würfel, Regelwerke, Änderungsvokabular
app/db         ORM-Modelle und Sitzungsverwaltung
app/ai         austauschbare Sprachmodell-Anbieter und der Antwortvertrag
app/tts        austauschbare Sprachausgabe
```

## Der Rundenablauf

Ein Zug läuft bewusst in zwei Phasen, damit ein Ausfall der KI niemals
Spielergebnisse verfälscht oder verliert:

1. **Phase A – mechanisch.** Alle eingereichten Handlungen werden gegen das
   Regelwerk geprüft (lebt der Charakter? reicht das Mana? ist der Gegenstand
   im Inventar?), Kosten werden gebucht, Würfel geworfen, alles protokolliert
   und **festgeschrieben**.
2. **Phase B – erzählerisch.** Die KI erhält die feststehenden Ergebnisse plus
   einen kompakten Kontext und liefert Narration, private Hinweise, neue
   Handlungsvorschläge und Änderungsvorschläge. Das Backend validiert jeden
   Vorschlag gegen die Datenbank und übernimmt nur das Zulässige. Abgelehnte
   Vorschläge werden als Ereignis mit Begründung protokolliert.

Fällt die KI in Phase B aus, bleibt Phase A erhalten: der Spielleiter kann den
Zug mit *KI neu erzählen* erneut erzählen lassen, ohne dass gewürfelte
Ergebnisse verloren gehen.

## KI-Kontext und Langzeitgedächtnis

Die KI bekommt nie das vollständige Protokoll, sondern nur:
aktuelle Szene · Ort · anwesende NSC · Charakterwerte · Inventare · offene
Quests · gültige Fakten · die letzten Ereignisse · verdichtete
Zusammenfassungen.

Nach einer konfigurierbaren Zahl von Ereignissen erzeugt die KI automatisch
eine Zusammenfassung (`scene_summaries`). Diese ergänzt das Protokoll, ersetzt
es aber nie. Dadurch bleiben Kontextlänge und Kosten auch nach tausenden
Spielzügen konstant.

## Fakten- und Wissenssystem

* **`facts`** — was in der Welt wahr ist, mit Schlüssel, Quelle, Zeitpunkt
  (Sequenznummer), Sichtbarkeit und Gültigkeit. Fakten werden nie gelöscht,
  sondern entwertet (`invalidated_at_seq`), sodass die Historie nachvollziehbar
  bleibt.
* **`knowledge`** — wer *glaubt* was: öffentlich, ein bestimmter Charakter oder
  ein NSC, jeweils mit Sicherheitsgrad (`truth`, `rumor`, `belief`, `lie`).

Beim Erzählen erhält die KI pro Charakter nur dessen Wissen. Die Spieler-API
liefert ausschließlich öffentliche und ihnen bekannte Informationen — geheime
Fakten verlassen den Server nicht.

## Erste Schritte

### Mit Docker (empfohlen)

```bash
cp .env.example .env          # Werte anpassen, mindestens JWT_SECRET
docker compose up -d --build
docker compose logs -f backend
```

Danach erreichbar unter <http://localhost:8080>.
Damit Mitspieler per QR-Code beitreten können, muss `PUBLIC_BASE_URL` auf eine
im Netz erreichbare Adresse zeigen, z. B. `http://192.168.1.50:8080`.

Optionale Profile:

```bash
docker compose --profile local-ai up -d    # lokales Modell über Ollama
docker compose --profile worker up -d      # Worker für Sprachausgabe
```

### Ohne Docker (Entwicklung)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="sqlite+aiosqlite:///./dev.db"
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (zweites Terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173, API wird weitergereicht
```

## Konfiguration

Alle Optionen stehen mit Erläuterung in [`.env.example`](.env.example). Die
wichtigsten:

| Variable | Bedeutung |
|---|---|
| `AI_PROVIDER` | `mock` (offline), `anthropic`, `openai`, `ollama` |
| `AI_MODEL` | Modellbezeichner, Vorgabe `claude-opus-5` |
| `AI_EFFORT` | Denktiefe: `low` … `max` |
| `TTS_PROVIDER` | `browser` (im Browser gesprochen), `none`, `openai` |
| `PUBLIC_BASE_URL` | Basis für Beitrittslinks und QR-Codes |
| `JWT_SECRET` | Signatur der Spieler-Token — unbedingt ändern |
| `SITE_ADDRESS` | Domain für automatisches HTTPS via Caddy |

## Bedienung

**Spielleitung:** Runde erstellen → Charakter anlegen → QR-Code zeigen →
*Abenteuer starten*. Im Reiter *Verlauf* stehen Pausieren, Zug auflösen,
KI neu erzählen, Szene überspringen, Zusammenfassen, Audio wiederholen,
Spieler entfernen und Runde beenden.

**Spieler:** QR-Code scannen → Name eingeben → Charakter erstellen oder
zufällig generieren lassen → Vorschlag antippen oder eigene Handlung
eintippen. Sobald alle handlungsfähigen Spieler eingereicht haben, löst das
Backend den Zug automatisch auf.

Die Oberfläche ist eine installierbare PWA (iOS: *Zum Home-Bildschirm*,
Android: *App installieren*).

## Datenmodell

`games` · `game_settings` · `players` · `characters` · `character_stats` ·
`abilities` · `character_abilities` · `items` · `inventories` ·
`inventory_items` · `quests` · `quest_states` · `world_entities` ·
`entity_states` · `locations` · `relationships` · `facts` · `knowledge` ·
`turns` · `actions` · `events` · `dice_rolls` · `narrations` ·
`scene_summaries` · `audio_jobs` · `images`

Schemaänderungen laufen ausschließlich über Alembic:

```bash
cd backend
alembic revision --autogenerate -m "beschreibung"
alembic upgrade head
```

## Tests

```bash
cd backend && pytest              # Domänen- und Integrationstests
cd frontend && npm run typecheck  # strikte Typprüfung
```

Die Tests laufen gegen SQLite und den Offline-Spielleiter — ohne Docker,
ohne Netz, ohne API-Schlüssel. Abgedeckt sind unter anderem Würfelmechanik,
Regelprüfungen, der vollständige Rundenablauf, Rechteprüfung, Sichtbarkeit
von Geheimnissen und die Lückenlosigkeit des Ereignisprotokolls.

## Erweitern

| Vorhaben | Ansatzpunkt |
|---|---|
| Neuer KI-Anbieter | `LLMProvider` implementieren, in `app/ai/registry.py` eintragen |
| Neues Regelwerk (D&D, Cthulhu, …) | `RuleSet` implementieren, in `app/domain/rules.py` registrieren |
| Neue Sprachausgabe / Sonos, Chromecast, Home Assistant | `TTSProvider` implementieren, Ziel in `AUDIO_TARGETS` ergänzen, Worker erweitern |
| Neue Zustandsänderung | Modell in `app/domain/changes.py` ergänzen und Handler in `state_changes.py` schreiben |
| Bildgenerierung | Tabelle `images` ist vorbereitet; Worker analog zu `app/workers/media.py` |

Die API-Dokumentation erzeugt FastAPI automatisch: <http://localhost:8080/api/docs>.

## Status

Erste vollständige Ausbaustufe: Lobby, Charaktererstellung, Weltgenerierung,
Rundenschleife mit Würfeln und Validierung, Event Sourcing, Fakten- und
Wissenssystem, Zusammenfassungen, Echtzeit-Synchronisation, Sprachausgabe im
Browser, Moderationsfunktionen und PWA-Oberfläche.

Vorbereitet, aber noch nicht ausgeführt: serverseitige Sprachsynthese,
Bildgenerierung, Kartenansicht und die Audio-Ziele Sonos, Chromecast,
Home Assistant und AirPlay.
