# Änderungsprotokoll

Alle bemerkenswerten Änderungen an diesem Projekt werden hier festgehalten.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung an [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Hinzugefügt

- Diktieren statt Tippen: ein Mikrofon-Knopf neben dem Freitextfeld nutzt
  die browsereigene Spracherkennung (Web Speech API), um die Handlung per
  Sprache statt Tastatur einzugeben. Der erkannte Text landet im normalen
  Eingabefeld und bleibt vor dem Abschicken frei bearbeitbar -- es wird
  nichts automatisch abgesendet. Nur sichtbar, wenn der Browser die API
  unterstuetzt (u. a. Chrome/Edge; bei fehlender Unterstuetzung bleibt nur
  das Tastaturfeld).
- Von der KI erzeugte Weltvorschau: direkt bei der Rundenerstellung schreibt
  die KI aus den gewaehlten Einstellungen eine kurze, bewusst grobe Vorschau
  (2-4 Saetze) auf die kommende Welt, die ganz oben in der Lobby steht --
  noch vor der eigentlichen Weltentstehung, damit Spieler wissen, was sie
  erwartet, wenn sie ihren Charakter bauen. Schlaegt der Aufruf fehl (die
  Rundenerstellung wird dadurch nie blockiert), zeigt die Lobby ersatzweise
  weiterhin den zuvor eingefuehrten, rein lokal aus den Einstellungen
  zusammengesetzten Weltbild-Abriss.
- Ausschweiflicherer Weltaufbau beim Rundenstart: die KI legt jetzt deutlich
  mehr schon zu Beginn fest (mehrere Orte, mehrere NSC mit eigenem Geheimnis,
  eine Haupt- und mehrere Nebenquests, oeffentliche wie geheime Fakten),
  statt vieles erst waehrend des Spiels improvisieren zu muessen.
- Gruppenereignisse: eine Handlung laesst sich beim Absenden als
  Gruppenereignis markieren ("Wir gehen zur Hoehle."). Andere aktive
  Personen am selben Ort bekommen ein Angebot, mitzumachen. Wer zustimmt,
  teilt sich dieselbe Handlung (kein eigener Text noetig), wuerfelt aber
  mit dem eigenen Charakterwert und bekommt einen Bonus auf den Wurf. Der
  Zug loest erst auf, wenn jede erwartete Person entweder die eigene
  Handlung eingereicht oder auf das Angebot geantwortet hat.
- Keine vorgefertigten Handlungsvorschlaege mehr in der Handlungsleiste:
  nur noch „Nichts tun" und ein Freitextfeld. Statt eines „Los"-Knopfes
  werden alle Attribute des Charakters gelistet (die vier Grundattribute
  sowie alle selbst benannten Faehigkeiten) — wer handelt, entscheidet
  selbst, worauf die Probe gewuerfelt wird. Die KI bewertet danach nur
  noch, ob diese Wahl inhaltlich zur Handlung passt: bei loser Passung
  wird die Probe schwerer, bei offensichtlich falscher Wahl misslingt die
  Handlung ohne Wurf. Scheitert die Einschaetzung, gilt die Wahl als
  passend — eine einzelne fehlgeschlagene Pruefung blockiert die Handlung
  nicht. Inventar-Gegenstaende lassen sich weiterhin per Klick markieren,
  ohne die Handlung damit sofort abzusenden.
- Charaktererstellung: nach dem Anlegen (nicht beim Zufallspfad) fragt ein
  zusaetzlicher Schritt nach frei benannten Zusatzfaehigkeiten (z. B.
  „Schloesser knacken"), auf die insgesamt 100 Punkte verteilt werden
  koennen. Sie stehen danach in der Handlungsleiste gleichberechtigt neben
  den vier Grundattributen zur Wahl.
- Fortschritts-Zaehler gegen erzaehlerischen Stillstand: kommt eine Gruppe
  zwei Zuege in Folge bei keiner gewerteten Handlung zum Erfolg (auch ein
  abgelehnter Versuch zaehlt), muss die KI ab dem naechsten Zug eine
  konkrete, spielrelevante Wendung liefern — einen greifbaren Hinweis, den
  Fehler eines Gegners, einen neuen Weg — statt nur weiterer Atmosphaere
  ohne Fortschritt. Ein einzelner Erfolg setzt den Zaehler sofort zurueck.
  Gilt auch offline: der Spielleiter ohne KI-Schluessel greift ab dem
  Schwellwert auf eigene, konkrete statt vager Erzaehl-Beats zurueck.
- Wuerfel-Popup: nach einer Probe erscheint eine kurze Rollanimation mit
  dem Ergebnis (Erfolg, kritischer Erfolg, Patzer usw.), bevor die schon
  im Hintergrund fertiggestellte Erzaehlung samt Sprachausgabe sichtbar
  wird beziehungsweise Ton abspielt. Die KI und die Vertonung laufen
  bereits waehrend der Animation. Das Aufdecken ist jetzt gruppenweit
  synchronisiert: Erzaehlung, Ton und die Wuerfelergebnisse im Verlauf
  bleiben verborgen, bis jede an der Szene beteiligte Person ihr Popup
  bestaetigt hat — niemand liest oder hoert vor dem Rest der Gruppe
  weiter. Die Spielleitung kann vorzeitig aufdecken, falls jemand nicht
  mehr reagiert. Dieser Fortschritt (Server-Wahrheit, kein reiner
  Client-Zustand) uebersteht auch einen Neuladen der Seite mitten in der
  Wartezeit.
- Wuerfelergebnisse einer unabhaengig laufenden Szene an einem anderen Ort
  (Split-Party) tauchten bislang sofort im eigenen Verlauf auf, noch bevor
  der eigene Zug ueberhaupt abgeschlossen war — derselbe Ortsfilter wie
  bei der Erzaehlung gilt jetzt auch fuer Wuerfe.
- Handlungsleiste entschlackt: kompaktere Anordnung (Freitext und „Nichts
  tun" nebeneinander, Attribut-Auswahl als waagerecht scrollende Reihe
  statt Raster), damit sie auf einem normalen Handy-Bildschirm nicht mehr
  vom unteren Reiter-Balken abgeschnitten wird.
- Neue Handlungsart „Nichts tun": bei jeder Runde als eigener, immer
  sichtbarer Knopf verfuegbar (nicht nur unter den KI-Vorschlaegen).
  Bewusstes Abwarten ist immer erlaubt, kostet nichts und braucht keine
  Probe.
- Seltenes Quick-Time-Event (rund 10 % der Zugaufloesungen): eine
  zufaellig ausgewaehlte, an derselben Stelle anwesende Person bekommt ein
  paar Sekunden lang die Moeglichkeit „einzugreifen" — nimmt sie rechtzeitig
  an, wuerfelt die betroffene Handlung mit Vorteil (zwei Wuerfe, der
  bessere zaehlt).
- Fortlaufende Integration: Tests, statische Analyse, Typprüfung und Build
  laufen bei jedem Push und Pull Request; zusätzlich wird geprüft, ob
  Migration und Modelle auseinanderlaufen
- Veröffentlichung der Container-Images in der GitHub Container Registry bei
  jedem Tag `v*` sowie auf Zuruf über *Run workflow*
- App-Definition für TrueNAS SCALE ab 24.10 unter `deploy/truenas/` —
  eingerichtet auf OpenAI für Erzählung und Stimme, mit Redis, damit eine
  fertige Aufnahme die Geräte sofort erreicht statt beim nächsten Abgleich
- Serverseitige Sprachausgabe über die OpenAI-Schnittstelle `/audio/speech`.
  Die Aufnahme entsteht im Medien-Worker, wird in der Datenbank abgelegt und
  über einen abgesicherten Endpunkt ausgeliefert — die Runde wartet dabei nie
  auf die Vertonung.
- Lokale Sprachmodelle nutzbar: `TTS_BASE_URL` auf einen selbst betriebenen,
  OpenAI-kompatiblen Dienst zeigen lassen (etwa auf demselben TrueNAS). Ein
  Schlüssel ist dort nicht erforderlich.
- Ein Gerät am Tisch gibt den Ton aus, voreingestellt das der Spielleitung.
  Die neue Rundeneinstellung `audio_playback` (`host` | `all` | `none`) legt
  fest, wer mithören darf.
- Freischaltung der Wiedergabe auf iPhone und iPad: ein dauerhaft bestehendes
  Audio-Element wird bei der ersten Berührung entsperrt, danach spielt jede
  weitere Aufnahme von selbst. Solange die Freigabe fehlt, heißt der Schalter
  *Freischalten* und holt beim Antippen eine wartende Aufnahme nach.
- Scheitert die Vertonung, liest das Gerät die Erzählung selbst vor. Still
  bleibt es nur, wenn die Runde ohne Sprachausgabe angelegt wurde oder der
  Anbieter `none` eingestellt ist.
- Ältere Aufnahmen einer Runde geben ihre Daten wieder frei
  (`AUDIO_KEEP_LAST`); der Auftrag bleibt als Protokolleintrag erhalten.

- Getrennte Gruppen: Charaktere an unterschiedlichen Orten warten nicht mehr
  aufeinander. Jeder Ort bekommt seinen eigenen Zug, der unabhängig
  aufläuft; ein Charakter, der an einen Ort mit laufender Szene zieht, ist
  automatisch Teil davon. Bleibt die Gruppe zusammen, ändert sich nichts.
  Die Spielleitung sieht im Reiter *Verlauf* eine Übersicht aller
  gleichzeitig laufenden Orte und kann jeden gezielt auflösen.
- Passwortgeschütztes Einstellungen-Menü (`/settings`), abgesichert über die
  neue Umgebungsvariable `SETTINGS_PASSWORD` — installationsweit und
  unabhängig von Spieler-/Spielleiter-Token, leer gelassen bleibt der
  Bereich deaktiviert. Dort lassen sich die aktive TTS-Stimme (feste Auswahl
  bei OpenAI, Freitext bei einem lokalen Dienst) und die Sprechgeschwindigkeit
  ändern, auch während einer laufenden Runde: eine bereits wartende
  Sprachausgabe wird noch mit den alten Werten fertig, die nächste neu
  entstehende übernimmt die Änderung ganz ohne Neustart.
- Versionsanzeige: `/api/health` nennt jetzt `version` und `git_sha`, die
  Startseite zeigt beides klein im Fußbereich. Damit lässt sich einem
  gezogenen `:latest`-Image ansehen, ob es tatsächlich einen neuen Stand
  enthält. Beide Seiten lesen dieselbe Quelle (`backend/pyproject.toml`) —
  ein von Hand über *Run workflow* ausgelöster Bau ohne neuen Tag zeigt
  sonst auf der Startseite „vlatest", während `/api/health` weiterhin die
  echte Paketversion nennt.

### Geändert

- Ereigniszähler (`event_seq`) und Zugzähler (`current_turn_number`) werden
  jetzt atomar in der Datenbank erhöht statt in Python gelesen und
  zurückgeschrieben. Nötig, seit mehrere Züge desselben Spiels gleichzeitig
  auflösen können (getrennte Gruppen) — sonst hätten zwei gleichzeitige
  Auflösungen dieselbe Nummer vergeben können.
- Der Medien-Worker wartet jetzt auch auf das Backend (nicht nur auf die
  Datenbank), bevor er startet. Sonst kann er nach einem Update kurzzeitig
  Spalten abfragen, die das Backend erst beim Einspielen der Migrationen
  anlegt — der Fehler heilte sich zwar von selbst, war aber vermeidbar.
- Der geerbte Gesundheitscheck des Backend-Images (`curl .../api/health`)
  ist beim Medien-Worker jetzt abgeschaltet. Er startet keinen Webserver,
  der Test konnte dort nie bestehen — der Container (und mit ihm die ganze
  App, etwa in TrueNAS) blieb dadurch dauerhaft auf „wird gestartet"
  stehen, obwohl alle Dienste längst liefen.
- Der Medien-Worker läuft in `docker-compose.yml` nicht mehr in einem Profil,
  sondern immer mit — ohne ihn entsteht bei serverseitiger Stimme kein Ton.
- Die Sprachausgabe über OpenAI war bisher nur angedeutet und lieferte nie
  eine Aufnahme; sie ist nun vollständig umgesetzt.
- Der OpenAI-Anbieter für die Spielleiter-KI kommt auch mit Modellen zurecht,
  die `max_completion_tokens` statt `max_tokens` verlangen, und weist auf ein
  Modell hin, das nicht zum eingestellten Anbieter passt.

- Der Frontend-Container reicht Anfragen unter `/api` nun selbst an das
  Backend weiter, einschließlich WebSocket. Damit genügt für einen
  Einzelplatz-Betrieb ein einziger veröffentlichter Port; ein zusätzlicher
  Reverse Proxy ist nur noch für TLS oder mehrere Instanzen nötig.

### Behoben

- KI-Vorschlaege (z. B. eine Quest samt Auftraggeber) konnten stillschweigend
  scheitern, wenn die KI abhaengige Aenderungen in der "falschen"
  Reihenfolge lieferte -- etwa eine Quest vor dem NSC, der sie vergibt. Ein
  zweiter Anwendungsdurchlauf gibt so einer Aenderung jetzt eine zweite
  Chance, nachdem der Rest bereits angewendet ist.
- Der Fortschritts-Zaehler gegen erzaehlerischen Stillstand reagierte nur
  auf Wuerfel-Erfolge -- eine Serie erfolgreicher, aber inhaltlich
  folgenloser Proben konnte die Geschichte trotzdem zum Stillstand bringen,
  ohne dass die KI eskalierte. Echter Fortschritt in den tatsaechlich
  angewendeten Aenderungen (neue Quest, entdeckter Ort usw.) setzt den
  Zaehler jetzt zusaetzlich zurueck, unabhaengig vom Wuerfelergebnis.
- Rundenstart schlug mit einem Datenbankfehler fehl, wenn zwischen dem
  Anlegen eines Charakters und dem Klick auf „Abenteuer starten" mehr als
  eine automatische Statusabfrage lag (praktisch jede Lobby-Wartezeit über
  ~12 Sekunden). Ursache: `GET .../state` legte für Spieler ohne laufenden
  Zug vorsorglich schon einen Zug „Nummer 1" an, obwohl die Runde noch gar
  nicht lief — der echte erste Zug beim Start kollidierte dann mit dieser
  Nummer. Die Rückfallregel greift jetzt nur noch, wenn die Runde bereits
  aktiv ist.

## [0.1.0] – 2026-07-29

Erste Ausbaustufe: eine vollständig spielbare, containerisierte Plattform.

### Hinzugefügt

**Plattform und Betrieb**

- Vollständige Docker-Compose-Umgebung: Backend, Frontend, PostgreSQL, Redis
  und Caddy als Reverse Proxy
- Optionale Profile für ein lokales Sprachmodell (`local-ai`, Ollama) und
  einen Medien-Worker (`worker`)
- Automatisches HTTPS über Caddy, sobald `SITE_ADDRESS` auf eine Domain zeigt
- Migrationen laufen beim Start automatisch; der Container wartet zuvor auf
  die Datenbank

**Spielablauf**

- Runde erstellen mit Genre, Spielwelt, Schwierigkeitsgrad, Dauer,
  Spieleranzahl, Regelkomplexität, Spielstil, Stimmung und Kampagnenform
- Beitritt über sechsstelligen Code, Beitrittslink oder QR-Code
- Charaktererstellung von Hand oder als KI-Vorschlag, mit regelwerkabhängigen
  Startwerten, Fähigkeiten und Startinventar
- Weltgenerierung zum Spielstart: Orte, NSC mit Geheimnissen, Hauptquest,
  Fakten, Wissenseinträge und die erste Szene
- Rundenschleife mit individuellen Handlungsvorschlägen je Charakter und
  freier Texteingabe; der Zug löst automatisch auf, sobald alle
  handlungsfähigen Spieler eingereicht haben

**Spiellogik im Backend**

- Zweiphasige Auflösung: erst Regelprüfung, Kosten und Würfe festschreiben,
  dann die KI erzählen lassen. Fällt die KI aus, bleiben die Ergebnisse
  erhalten und der Zug kann neu erzählt werden
- Würfelmechanik mit Erfolgsgraden von Patzer bis kritischem Erfolg
- Austauschbare Regelwerke (`classic`, `grit`) über ein `RuleSet`-Protokoll
- Prüfung jeder Handlung auf Handlungsfähigkeit, blockierende Zustände,
  Ressourcen und Inventar
- Validierung sämtlicher KI-Änderungsvorschläge gegen die Datenbank;
  abgelehnte Vorschläge werden mit Begründung protokolliert

**Persistenz und Gedächtnis**

- 26 Tabellen für Runden, Spieler, Charaktere, Werte, Fähigkeiten,
  Gegenstände, Inventare, Quests, Orte, Weltobjekte, Beziehungen, Fakten,
  Wissen, Züge, Handlungen, Ereignisse, Würfe, Narrationen,
  Zusammenfassungen, Audio- und Bildaufträge
- Event Sourcing mit lückenloser Sequenznummer je Runde; Ereignisse werden
  nur angehängt
- Faktensystem mit Quelle, Zeitpunkt, Sichtbarkeit und Gültigkeit; Fakten
  werden entwertet statt gelöscht
- Wissenssystem mit Trennung von Wahrheit, öffentlichem Wissen,
  Spielerwissen, NSC-Wissen, Vermutungen und Lügen
- Automatische Zusammenfassungen als Langzeitgedächtnis; der KI-Kontext
  bleibt dadurch auch nach tausenden Zügen konstant klein

**Schnittstellen**

- REST-API mit automatisch erzeugter OpenAPI-Beschreibung unter `/api/docs`
- WebSocket für Echtzeit-Synchronisation, optional über Redis für mehrere
  Backend-Instanzen
- JWT-basierter Zugang, an Spieler und Runde gebunden
- Austauschbare KI-Anbieter: `mock` (offline, ohne Schlüssel spielbar),
  `anthropic`, OpenAI-kompatibel und `ollama`
- Austauschbare Sprachausgabe: `none`, `browser`, `openai`

**Oberfläche**

- Installierbare PWA für iPhone und Android, auf Smartphones ausgelegt
- Erzählstrang mit Narration, privaten Hinweisen und Würfelprotokoll
- Charakterbogen, Inventar, Quests, Weltübersicht und Spielverlauf
- Sprachausgabe im Browser mit Stimmenauswahl und Wiederholung
- Moderationsfunktionen für die Spielleitung: pausieren, fortsetzen, Zug
  auflösen, KI neu erzählen lassen, Szene überspringen, zusammenfassen,
  Audio wiederholen, Spieler entfernen, Runde beenden

**Qualitätssicherung**

- 57 Tests gegen SQLite und den Offline-Spielleiter, ohne Docker, ohne Netz
  und ohne API-Schlüssel
- Abgedeckt: Würfelmechanik, Regelprüfungen, vollständiger Rundenablauf,
  Rechteprüfung, Sichtbarkeit von Geheimnissen und Lückenlosigkeit des
  Ereignisprotokolls
- Strikte Typprüfung im Frontend, statische Analyse im Backend
- Alembic-Migration ohne Schema-Drift gegenüber den Modellen

### Vorbereitet, aber noch nicht ausgeführt

Die folgenden Punkte sind im Datenmodell und in den Schnittstellen angelegt,
aber bewusst noch nicht implementiert, da sie zum Testen jeweils Geräte oder
externe Dienste voraussetzen:

- Serverseitige Sprachsynthese über den Medien-Worker
- Bildgenerierung (Tabelle `images` und Anbieterschnittstelle vorhanden)
- Kartenansicht
- Audio-Ziele Sonos, Chromecast, Home Assistant und AirPlay

[Unveröffentlicht]: https://github.com/Zendonir/KI-PnP/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Zendonir/KI-PnP/releases/tag/v0.1.0
