# KI-PnP auf TrueNAS SCALE

Anleitung für TrueNAS SCALE ab 24.10 („ElectricEel"), also der Version mit
Docker-Unterstützung. Die App besteht aus fünf Containern: Datenbank, Redis,
Backend, Medien-Worker für die Sprachausgabe und Frontend. Nach außen ist nur
ein Port sichtbar — der Frontend-Container reicht `/api` intern an das Backend
weiter.

Der Worker verwendet dasselbe Image wie das Backend, nur mit einem anderen
Startbefehl; es wird also kein zweites Image geladen. Redis dient allein als
kurzer Weg für Meldungen zwischen Backend und Worker und speichert nichts.

## Voraussetzungen

Die Container-Images liegen bereits veröffentlicht und ohne Anmeldung ziehbar
in der GitHub Container Registry:

```
ghcr.io/zendonir/ki-pnp-backend:latest
ghcr.io/zendonir/ki-pnp-frontend:latest
```

Für die Installation ist also nichts vorzubereiten. Neu gebaut werden sie bei
jedem Tag `v*` automatisch — dann zusätzlich mit der Versionsnummer als
Bezeichner — oder auf Zuruf über *Actions* → *Release-Images* →
*Run workflow*.

<details>
<summary>Falls das Herunterladen mit <code>denied</code> scheitert</summary>

Dann sind die Pakete privat. Das passiert, wenn das Repository privat ist oder
die Sichtbarkeit der Pakete umgestellt wurde. Zwei Wege:

Auf der GitHub-Profilseite unter *Packages* jeweils `ki-pnp-backend` und
`ki-pnp-frontend` öffnen → *Package settings* → *Change visibility* →
**Public**.

Oder die Images privat halten und sich auf dem TrueNAS-Server einmalig
anmelden (SSH, als root):

```bash
docker login ghcr.io -u <github-benutzername>
# Kennwort: ein Personal Access Token mit dem Recht read:packages
```

</details>

## Installation

1. In der TrueNAS-Oberfläche: *Apps* → *Discover Apps* → oben rechts
   *Custom App* → **Install via YAML**
2. Den Inhalt von [`ki-pnp.yaml`](ki-pnp.yaml) vollständig einfügen
3. Die mit `>>> ANPASSEN` markierten Stellen ändern:

   | Stelle | Bedeutung |
   |---|---|
   | `POSTGRES_PASSWORD` und `DATABASE_URL` | Datenbankkennwort, muss bei `db`, `backend` **und** `worker` identisch sein und darf nur Buchstaben, Ziffern, `-` und `_` enthalten (siehe unten) |
   | `PUBLIC_BASE_URL` | Adresse im Netz, z. B. `http://192.168.1.50:30080` — landet im QR-Code |
   | `JWT_SECRET` | eigenes Geheimnis, z. B. aus `openssl rand -hex 32` |
   | `OPENAI_API_KEY` | Schlüssel für Spielleiter-KI und Sprachausgabe; bei `backend` und `worker` eintragen |

4. Namen vergeben (etwa `ki-pnp`) und installieren

> **Zum Datenbankkennwort:** Es steht in `DATABASE_URL` mitten in einer
> Verbindungsadresse. Zeichen wie `@ : / ? # %` haben dort eine eigene
> Bedeutung — das Backend läse die Adresse dann anders als gemeint und käme
> nicht an die Datenbank, während PostgreSQL das Kennwort unverändert
> bekommt. Der Fehler ist schwer zu finden, deshalb: nur Buchstaben,
> Ziffern, `-` und `_` verwenden. `openssl rand -hex 24` liefert immer ein
> passendes Kennwort.

Der erste Start dauert etwas: das Backend wartet auf die Datenbank und spielt
anschließend die Migrationen ein. Sobald alle fünf Container laufen, ist die
Oberfläche unter der eingetragenen Adresse erreichbar.

## Warum Port 30080

Die TrueNAS-Weboberfläche belegt 80 und 443 — diese Ports sind für Apps tabu.
30080 ist frei und außerhalb des reservierten Bereichs. Ein anderer Port geht
auch, dann muss `PUBLIC_BASE_URL` denselben Port nennen, sonst zeigt der
QR-Code ins Leere.

## Erste Runde

1. Adresse am Rechner oder Smartphone öffnen
2. *Runde erstellen* → Name, Genre und Schwierigkeitsgrad wählen
3. Charakter anlegen
4. Mitspieler scannen den QR-Code aus der Lobby
5. *Abenteuer starten*

## Spielleiter-KI und Sprachausgabe

Die mitgelieferte YAML ist auf OpenAI eingestellt: `AI_PROVIDER: openai` mit
`AI_MODEL: gpt-4o` für die Erzählung und `TTS_PROVIDER: openai` mit
`gpt-4o-mini-tts` für die Stimme. Beides nutzt `OPENAI_API_KEY` — dieser muss
bei `backend` **und** bei `worker` stehen.

Bleibt der Schlüssel leer, läuft die App trotzdem: dann übernimmt der
eingebaute Offline-Spielleiter. Er erzeugt Welt, NSC, Quests und
Handlungsvorschläge ohne Internet, erzählt aber schlichter — gut geeignet, um
die Installation zu prüfen. Die Sprachausgabe fällt in diesem Fall auf die
Stimme des Browsers zurück.

Wichtig: `AI_MODEL` muss zum Anbieter passen. Ein Anthropic-Modellname bei
`AI_PROVIDER: openai` wird abgewiesen.

### Lokales Sprachmodell für die Stimme

Wer die Vertonung im Haus behalten will, betreibt einen OpenAI-kompatiblen
TTS-Dienst mit dem Endpunkt `/audio/speech` als eigene App auf demselben
TrueNAS und richtet die Sprachausgabe darauf:

```yaml
      TTS_PROVIDER: openai
      TTS_BASE_URL: http://192.168.1.50:8880/v1
      TTS_MODEL: kokoro
      TTS_VOICE: af_heart
      TTS_API_KEY: ""
```

Ein Schlüssel wird für lokale Dienste nicht verlangt. Die Adresse muss vom
Container aus erreichbar sein — läuft der Dienst als eigene TrueNAS-App,
genügt die IP des Servers samt dessen Port. Diese Werte gehören bei `backend`
und `worker` gleichlautend hinein.

### Wo der Ton herauskommt

Am Tisch spricht genau ein Gerät, voreingestellt das der Spielleitung. Der
Server erzeugt die Aufnahme, der Worker holt sie ab, und das iPhone der
Spielleitung spielt sie ab. Jedes Gerät kann sich über den Schalter
*Ton hier* im Reiter *Szene* selbst stumm schalten oder die Ausgabe
übernehmen.

Safari auf dem iPhone erlaubt Ton erst nach einer Berührung. Der Schalter
heißt dann *Freischalten*; ein Antippen gibt den Ton frei und holt eine
wartende Aufnahme nach. Danach spielt jede weitere von selbst.

Bleibt die Vertonung aus — kein Schlüssel, kein Guthaben, Dienst nicht
erreichbar —, liest das Gerät die Erzählung selbst vor. Die Runde wartet nie
auf den Ton.

## Betrieb

**Sicherung.** Die Spieldaten liegen im Docker-Volume `postgres-data`
innerhalb des `ix-apps`-Datensatzes. Wer sie lieber sichtbar im Pool hätte,
ersetzt das Volume beim Dienst `db` durch einen Pfad:

```yaml
    volumes:
      - /mnt/tank/apps/ki-pnp/postgres:/var/lib/postgresql/data
```

Das Verzeichnis muss vorher als Datensatz angelegt werden. Ein Auszug der
Datenbank geht auch jederzeit so:

```bash
docker exec ix-ki-pnp-db-1 pg_dump -U kipnp kipnp > ki-pnp-sicherung.sql
```

**Aktualisieren.** In der App *Edit* öffnen und den Image-Bezeichner auf die
gewünschte Version setzen, etwa `:0.2.0` statt `:latest`. Migrationen laufen
beim Start von selbst. Für den produktiven Betrieb ist eine feste Version
ratsam — `:latest` ändert sich unbemerkt.

**Wie prüfe ich, welcher Stand tatsächlich läuft?** `:latest` in der Registry
wird nur neu gebaut, wenn im Repository ein Tag `v*` erscheint oder jemand
den Workflow *Release-Images* von Hand anstößt (*Actions* → *Run workflow*)
— ein Zusammenführen in `main` allein löst das nicht aus. Ein frisch
gezogenes `:latest` kann also trotzdem der alte Stand sein. Zwei Wege, das
zu erkennen:

- Auf der Startseite der Oberfläche steht klein im Fußbereich
  `vX.Y.Z · <Commit>`.
- `curl http://<adresse>:30080/api/health` nennt dasselbe unter `version`
  und `git_sha`.

Stimmt der Commit nicht mit dem erwarteten überein, wurde entweder das
Image nicht neu gebaut oder der Container zieht es nicht neu — dann hilft
in der App-Oberfläche *Update* bzw. das Image von Hand erneut ziehen.

**Von außen erreichbar machen.** Für den Zugriff über das Internet gehört ein
Reverse Proxy mit TLS davor (etwa Traefik oder Nginx Proxy Manager auf
demselben Server). Danach `PUBLIC_BASE_URL` auf die öffentliche Adresse
setzen, sonst verweisen die Beitrittslinks weiterhin auf die interne IP.
Ohne HTTPS lässt sich die PWA auf iPhones nicht installieren.

## Wenn etwas klemmt

| Symptom | Ursache und Abhilfe |
|---|---|
| `denied` beim Herunterladen | Die GHCR-Pakete sind privat — siehe den ausklappbaren Hinweis unter *Voraussetzungen* |
| `manifest unknown` | Der gewählte Bezeichner existiert nicht. `:latest` ist vorhanden; Versionsbezeichner entstehen erst mit einem Tag `v*` |
| Oberfläche lädt, aber jede Aktion meldet einen Fehler | Backend nicht bereit. Logs des Containers `backend` prüfen; meist stimmt das Kennwort in `DATABASE_URL` nicht mit `POSTGRES_PASSWORD` überein |
| QR-Code führt ins Leere | `PUBLIC_BASE_URL` zeigt nicht auf die tatsächliche Adresse samt Port |
| Backend startet immer wieder neu | Datenbank noch nicht bereit — der Start wartet bis zu zwei Minuten; hält es länger an, in den Logs von `db` nachsehen |
| Keine Sprachausgabe | Im Reiter *Szene* muss der Schalter aktiv sein; steht dort *Freischalten*, einmal antippen — Safari verlangt eine Berührung |
| „Für diese Runde ist die Sprachausgabe abgeschaltet" | Die Runde wurde ohne Sprachausgabe angelegt. Das lässt sich nur beim Erstellen wählen, nicht nachträglich |
| Rechts steht „Gerätestimme" statt „Serverstimme" | Es kommt keine Aufnahme vom Server. Logs des Containers `worker` prüfen: fehlt `OPENAI_API_KEY`, meldet er den Auftrag als fehlgeschlagen |
| Der Worker meldet `401` | Der Schlüssel ist ungültig oder hat kein Guthaben. Bei einem lokalen Dienst darf `TTS_API_KEY` leer bleiben |
| Der Worker meldet einen Verbindungsfehler | `TTS_BASE_URL` ist vom Container aus nicht erreichbar. Bei einem lokalen Dienst die IP des Servers verwenden, nicht `localhost` |
| Die Erzählung hallt mehrfach durch den Raum | Mehrere Geräte geben Ton aus. Auf den übrigen *Ton hier* ausschalten |
| Die App bleibt dauerhaft auf „Deploying" stehen, obwohl alle Container laufen | Ältere `ki-pnp.yaml` ohne `healthcheck: disable: true` beim Dienst `worker`. Er erbt sonst den Gesundheitscheck des Backends (`curl .../api/health`), kann ihn aber nie bestehen, weil er keinen Webserver startet. Die aktuelle `ki-pnp.yaml` aus diesem Repository einspielen (App bearbeiten → YAML ersetzen) |
