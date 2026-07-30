# KI-PnP auf TrueNAS SCALE

Anleitung für TrueNAS SCALE ab 24.10 („ElectricEel"), also der Version mit
Docker-Unterstützung. Die App besteht aus drei Containern: Datenbank, Backend
und Frontend. Nach außen ist nur ein Port sichtbar — der Frontend-Container
reicht `/api` intern an das Backend weiter.

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
3. Die drei mit `>>> ANPASSEN` markierten Stellen ändern:

   | Stelle | Bedeutung |
   |---|---|
   | `POSTGRES_PASSWORD` und `DATABASE_URL` | Datenbankkennwort, muss an **beiden** Stellen identisch sein und darf nur Buchstaben, Ziffern, `-` und `_` enthalten (siehe unten) |
   | `PUBLIC_BASE_URL` | Adresse im Netz, z. B. `http://192.168.1.50:30080` — landet im QR-Code |
   | `JWT_SECRET` | eigenes Geheimnis, z. B. aus `openssl rand -hex 32` |

4. Namen vergeben (etwa `ki-pnp`) und installieren

> **Zum Datenbankkennwort:** Es steht in `DATABASE_URL` mitten in einer
> Verbindungsadresse. Zeichen wie `@ : / ? # %` haben dort eine eigene
> Bedeutung — das Backend läse die Adresse dann anders als gemeint und käme
> nicht an die Datenbank, während PostgreSQL das Kennwort unverändert
> bekommt. Der Fehler ist schwer zu finden, deshalb: nur Buchstaben,
> Ziffern, `-` und `_` verwenden. `openssl rand -hex 24` liefert immer ein
> passendes Kennwort.

Der erste Start dauert etwas: das Backend wartet auf die Datenbank und spielt
anschließend die Migrationen ein. Sobald alle drei Container laufen, ist die
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

In der Voreinstellung `AI_PROVIDER: mock` übernimmt der eingebaute
Offline-Spielleiter. Er erzeugt Welt, NSC, Quests und Handlungsvorschläge
ohne API-Schlüssel und ohne Internet — gut geeignet, um die Installation zu
prüfen. Für eine echte KI genügt es, in der App-Konfiguration
`AI_PROVIDER` auf `anthropic` zu setzen und `ANTHROPIC_API_KEY` zu füllen.

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
| Keine Sprachausgabe | Sie läuft im Browser und muss im Reiter *Szene* mit *Vorlesen an* eingeschaltet werden; iOS erlaubt sie erst nach einer Berührung der Seite |
