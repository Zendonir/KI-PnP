/** Lobby und Spieltisch. */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ActionBar } from "../components/ActionBar";
import { AudioControls } from "../components/AudioControls";
import { DiceRollModal } from "../components/DiceRollModal";
import { InterventionPrompt } from "../components/InterventionPrompt";
import {
  CharacterSheet,
  InventoryPanel,
  LocationOverviewPanel,
  LogPanel,
  PartyPanel,
  QuestPanel,
  WorldPanel,
} from "../components/Panels";
import { NarrationFeed } from "../components/NarrationFeed";
import { Badge, Button, Card, ErrorNote, Field, Spinner, TextInput } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { clearSession, loadSession } from "../lib/session";
import type { DiceRoll, GameState, InterventionOffer, RealtimeMessage } from "../lib/types";
import { useGameState } from "../lib/useGameState";

type Tab = "story" | "character" | "quests" | "world" | "log";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "story", label: "Szene", icon: "📖" },
  { id: "character", label: "Held", icon: "🛡️" },
  { id: "quests", label: "Quests", icon: "📜" },
  { id: "world", label: "Welt", icon: "🗺️" },
  { id: "log", label: "Verlauf", icon: "🕰️" },
];

export function GamePage() {
  const { gameId = "" } = useParams();
  const navigate = useNavigate();
  const session = useMemo(() => loadSession(), []);
  const token = session?.gameId === gameId ? session.token : null;
  const { state, error, connected, loading, refresh, lastMessage } = useGameState(gameId, token);

  if (!token) {
    return (
      <main className="mx-auto w-full max-w-md space-y-4 px-5 py-12">
        <ErrorNote>Fuer diese Runde liegt kein Zugang vor.</ErrorNote>
        <Button className="w-full" onClick={() => navigate("/")}>
          Zur Startseite
        </Button>
      </main>
    );
  }

  if (loading && !state) {
    return (
      <main className="flex min-h-full items-center justify-center px-5">
        <Spinner label="Spielstand wird geladen ..." />
      </main>
    );
  }

  if (!state) {
    return (
      <main className="mx-auto w-full max-w-md space-y-4 px-5 py-12">
        <ErrorNote>{error ?? "Die Runde ist nicht erreichbar."}</ErrorNote>
        <Button className="w-full" variant="ghost" onClick={() => void refresh()}>
          Erneut versuchen
        </Button>
        <Button
          className="w-full"
          variant="subtle"
          onClick={() => {
            clearSession();
            navigate("/");
          }}
        >
          Runde verlassen
        </Button>
      </main>
    );
  }

  return state.game.status === "lobby" ? (
    <LobbyView state={state} token={token} onChanged={refresh} connected={connected} />
  ) : (
    <TableView
      state={state}
      token={token}
      onChanged={refresh}
      connected={connected}
      lastMessage={lastMessage}
    />
  );
}

/* -------------------------------------------------------------------- */

function StatusBar({ state, connected }: { state: GameState; connected: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-ink-700 bg-ink-900/95 px-4 py-2 backdrop-blur">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-parchment">{state.game.name}</p>
        <p className="truncate text-xs text-parchment/50">
          Code {state.game.code} · Zug{" "}
          {state.turn?.number ?? state.game.current_turn_number} ·{" "}
          {state.turn?.scene_title || state.game.status}
        </p>
      </div>
      <span
        className={`h-2.5 w-2.5 shrink-0 rounded-full ${connected ? "bg-moss-500" : "bg-blood-500"}`}
        title={connected ? "Echtzeit verbunden" : "keine Echtzeitverbindung"}
      />
    </div>
  );
}

function LobbyView({
  state,
  token,
  onChanged,
  connected,
}: {
  state: GameState;
  token: string;
  onChanged: () => Promise<void>;
  connected: boolean;
}) {
  const [name, setName] = useState("");
  const [charClass, setCharClass] = useState("Krieger");
  const [race, setRace] = useState("Mensch");
  const [background, setBackground] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Zwei getrennte Schritte nach dem Erstellen: erst alle Namen sammeln
  // (ein Freitextfeld pro Zeile, keine konkurrierenden Breitenangaben),
  // dann -- nur fuer die dabei benannten Faehigkeiten -- die Punkte
  // verteilen.
  const [skillStep, setSkillStep] = useState<"names" | "points" | null>(null);
  const [skillNames, setSkillNames] = useState<string[]>([""]);
  const [skillPoints, setSkillPoints] = useState<Record<string, number>>({});
  const joinUrl = `${window.location.origin}/join/${state.game.code}`;

  const createCharacter = async (randomize: boolean) => {
    setBusy(true);
    setError(null);
    try {
      await api.createCharacter(state.game.id, token,
        randomize
          ? { randomize: true }
          : { name, class: charClass, race, background },
      );
      // Der Zufallspfad ist bewusst schnell und ueberspringt die
      // Fähigkeiten-Verteilung; wer den Charakter selbst baut, bekommt
      // direkt danach den Verteilungsschritt gezeigt.
      if (randomize) {
        await onChanged();
      } else {
        setSkillNames([""]);
        setSkillStep("names");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Charakter konnte nicht erstellt werden.");
    } finally {
      setBusy(false);
    }
  };

  const proceedToPoints = () => {
    const cleaned = Array.from(
      new Set(skillNames.map((entry) => entry.trim()).filter((entry) => entry)),
    );
    if (cleaned.length === 0) {
      void skipSkills();
      return;
    }
    setSkillPoints(Object.fromEntries(cleaned.map((entry) => [entry, 0])));
    setSkillStep("points");
  };

  const skillPointsUsed = Object.values(skillPoints).reduce((sum, value) => sum + (value || 0), 0);
  const skillPointsLeft = 100 - skillPointsUsed;

  const finishSkills = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload = Object.entries(skillPoints).map(([entryName, points]) => ({
        name: entryName,
        points: points || 0,
      }));
      if (payload.length > 0) {
        await api.setCharacterSkills(state.game.id, token, payload);
      }
      setSkillStep(null);
      await onChanged();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Faehigkeiten konnten nicht gespeichert werden.",
      );
    } finally {
      setBusy(false);
    }
  };

  const skipSkills = async () => {
    setSkillStep(null);
    await onChanged();
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.startGame(state.game.id, token);
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Die Runde konnte nicht starten.");
    } finally {
      setBusy(false);
    }
  };

  const everyoneReady =
    state.players.filter((player) => player.is_active).length > 0 &&
    state.players
      .filter((player) => player.is_active)
      .every((player) => state.characters.some((item) => item.player_id === player.id));

  return (
    <div className="safe-top safe-bottom mx-auto flex min-h-full w-full max-w-md flex-col">
      <StatusBar state={state} connected={connected} />
      <div className="space-y-4 px-4 py-4">
        {error && <ErrorNote>{error}</ErrorNote>}

        <Card title="Mitspieler einladen">
          <div className="flex flex-col items-center gap-3">
            <img
              src={api.qrUrl(state.game.code)}
              alt={`QR-Code zum Beitreten der Runde ${state.game.code}`}
              className="h-44 w-44 rounded-xl bg-parchment p-2"
            />
            <p className="text-center font-mono text-2xl tracking-[0.3em] text-ember-400">
              {state.game.code}
            </p>
            <div className="flex w-full gap-2">
              <Button
                variant="ghost"
                className="flex-1"
                onClick={() => void navigator.clipboard?.writeText(joinUrl)}
              >
                Link kopieren
              </Button>
              {typeof navigator !== "undefined" && "share" in navigator && (
                <Button
                  variant="ghost"
                  className="flex-1"
                  onClick={() =>
                    void navigator
                      .share({ title: state.game.name, url: joinUrl })
                      .catch(() => undefined)
                  }
                >
                  Teilen
                </Button>
              )}
            </div>
          </div>
        </Card>

        <PartyPanel
          players={state.players}
          characters={state.characters}
          submittedIds={[]}
          hostId={state.players.find((player) => player.role === "host")?.id ?? null}
        />

        {state.my_character ? (
          <CharacterSheet character={state.my_character} />
        ) : skillStep === "names" ? (
          <Card title="Fähigkeiten benennen">
            <p className="mb-3 text-sm text-parchment/65">
              Erfinde eigene Fähigkeiten (z. B. „Schlösser knacken"). Im naechsten Schritt
              verteilst du 100 Punkte darauf.
            </p>
            <div className="space-y-2">
              {skillNames.map((value, index) => (
                <div key={index} className="flex items-center gap-2">
                  <TextInput
                    value={value}
                    onChange={(event) => {
                      const next = [...skillNames];
                      next[index] = event.target.value;
                      setSkillNames(next);
                    }}
                    placeholder="z. B. Schlösser knacken"
                  />
                  {skillNames.length > 1 && (
                    <Button
                      variant="ghost"
                      onClick={() => setSkillNames(skillNames.filter((_, i) => i !== index))}
                    >
                      ✕
                    </Button>
                  )}
                </div>
              ))}
            </div>
            <Button
              variant="ghost"
              className="mt-2 w-full"
              disabled={skillNames.length >= 12}
              onClick={() => setSkillNames([...skillNames, ""])}
            >
              + Fähigkeit hinzufügen
            </Button>
            <div className="mt-3 flex gap-2">
              <Button className="flex-1" onClick={proceedToPoints}>
                Weiter
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => void skipSkills()}>
                Überspringen
              </Button>
            </div>
          </Card>
        ) : skillStep === "points" ? (
          <Card title="Punkte verteilen">
            <p className="mb-3 text-sm text-parchment/65">
              Verteile insgesamt 100 Punkte auf deine Fähigkeiten. Sie stehen dir spaeter
              zusaetzlich zu den vier Grundattributen als Wuerfel-Attribut zur Wahl.
            </p>
            <div className="space-y-2">
              {Object.keys(skillPoints).map((entryName) => (
                <div key={entryName} className="flex items-center justify-between gap-3">
                  <span className="text-sm text-parchment">{entryName}</span>
                  <TextInput
                    type="number"
                    min={0}
                    max={100}
                    value={skillPoints[entryName]}
                    onChange={(event) =>
                      setSkillPoints({
                        ...skillPoints,
                        [entryName]: Number(event.target.value) || 0,
                      })
                    }
                    className="!w-24 text-right"
                  />
                </div>
              ))}
            </div>
            <p
              className={`mt-3 text-sm ${
                skillPointsLeft < 0 ? "text-blood-400" : "text-parchment/60"
              }`}
            >
              Verbleibend: {skillPointsLeft} von 100 Punkten
            </p>
            <div className="mt-3 flex gap-2">
              <Button variant="ghost" disabled={busy} onClick={() => setSkillStep("names")}>
                Zurück
              </Button>
              <Button
                className="flex-1"
                disabled={busy || skillPointsLeft < 0}
                onClick={() => void finishSkills()}
              >
                Fertig
              </Button>
            </div>
          </Card>
        ) : (
          <Card title="Charakter erstellen">
            <div className="space-y-3">
              <Field label="Name">
                <TextInput
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="z. B. Kell Graustein"
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Klasse">
                  <TextInput
                    value={charClass}
                    onChange={(event) => setCharClass(event.target.value)}
                  />
                </Field>
                <Field label="Volk">
                  <TextInput value={race} onChange={(event) => setRace(event.target.value)} />
                </Field>
              </div>
              <Field label="Hintergrund" hint="Optional -- die KI greift ihn spaeter auf.">
                <TextInput
                  value={background}
                  onChange={(event) => setBackground(event.target.value)}
                  placeholder="Woher kommst du? Was treibt dich?"
                />
              </Field>
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  disabled={busy || !name.trim()}
                  onClick={() => void createCharacter(false)}
                >
                  Erstellen
                </Button>
                <Button variant="ghost" disabled={busy} onClick={() => void createCharacter(true)}>
                  🎲 Zufall
                </Button>
              </div>
            </div>
          </Card>
        )}

        {state.is_host && (
          <Card title="Spielleitung">
            <p className="mb-3 text-sm text-parchment/65">
              Beim Start erzeugt die KI Welt, NSC, Quests und die erste Szene. Danach koennen
              weitere Spieler jederzeit nachkommen.
            </p>
            <Button
              className="w-full"
              disabled={busy || !state.my_character}
              onClick={() => void start()}
            >
              {busy ? "Die Welt entsteht ..." : "Abenteuer starten"}
            </Button>
            {!everyoneReady && (
              <p className="mt-2 text-xs text-parchment/50">
                Hinweis: Nicht alle Spieler haben schon einen Charakter.
              </p>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

function TableView({
  state,
  token,
  onChanged,
  connected,
  lastMessage,
}: {
  state: GameState;
  token: string;
  onChanged: () => Promise<void>;
  connected: boolean;
  lastMessage: RealtimeMessage | null;
}) {
  const [tab, setTab] = useState<Tab>("story");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const characterNames = useMemo(
    () => Object.fromEntries(state.characters.map((item) => [item.id, item.name])),
    [state.characters],
  );
  const hasSubmitted = Boolean(
    state.turn?.submitted_player_ids.includes(state.me.id),
  );
  const paused = state.game.status === "paused";
  const finished = state.game.status === "finished";

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  // Das Backend loest einen Zug vollstaendig auf, sobald alle eingereicht
  // haben -- Erzaehlung und Sprachausgabe entstehen also schon im
  // Hintergrund, waehrend hier noch das Wuerfel-Popup laeuft. Ein Wechsel
  // der Zug-Kennung zeigt an, dass der zuvor gezeigte Zug gerade
  // abgeschlossen wurde; dessen Wuerfe werden dann kurz zurueckgehalten und
  // angezeigt, bevor "Weiter" die schon fertige Erzaehlung (und deren Ton)
  // freigibt -- rein lokal, ohne weiteren Netzwerkaufruf.
  const previousTurnIdRef = useRef<string | null>(null);
  const [pendingReveal, setPendingReveal] = useState<
    { turnId: string; rolls: DiceRoll[] } | null
  >(null);
  useEffect(() => {
    const currentId = state.turn?.id ?? null;
    const previousId = previousTurnIdRef.current;
    if (previousId && currentId !== previousId) {
      const rolls = state.dice_rolls.filter((roll) => roll.turn_id === previousId);
      if (rolls.length > 0) {
        setPendingReveal({ turnId: previousId, rolls });
      }
    }
    previousTurnIdRef.current = currentId;
    // state.dice_rolls absichtlich nicht in den Abhaengigkeiten: der
    // Zug-Wechsel selbst ist das Ausloesekriterium, die Wuerfe werden aus
    // demselben, zu diesem Zeitpunkt schon aktuellen state gelesen.
  }, [state.turn?.id]);

  const pendingNarrationIds = useMemo(() => {
    if (!pendingReveal) return new Set<string>();
    return new Set(
      state.narrations
        .filter((item) => item.turn_id === pendingReveal.turnId)
        .map((item) => item.id),
    );
  }, [pendingReveal, state.narrations]);

  const visibleNarrations = pendingNarrationIds.size
    ? state.narrations.filter((item) => !pendingNarrationIds.has(item.id))
    : state.narrations;
  const visibleRolls = pendingReveal
    ? state.dice_rolls.filter((roll) => roll.turn_id !== pendingReveal.turnId)
    : state.dice_rolls;
  const visibleLatestNarration = visibleNarrations.at(-1) ?? null;
  const visibleAudio =
    pendingNarrationIds.size &&
    state.audio?.narration_id &&
    pendingNarrationIds.has(state.audio.narration_id)
      ? null
      : state.audio;

  // Quick-Time-Event: ein an mich persoenlich gerichtetes Angebot bleibt
  // sichtbar, bis es beantwortet ist oder die Zeit ablaeuft.
  const [interventionOffer, setInterventionOffer] = useState<InterventionOffer | null>(null);
  useEffect(() => {
    if (
      lastMessage?.type === "intervention.offer" &&
      lastMessage.audience_player_id === state.me.id
    ) {
      setInterventionOffer(lastMessage.payload as unknown as InterventionOffer);
    }
  }, [lastMessage, state.me.id]);

  // Feste Hoehe mit eigenem Scrollbereich: so verdeckt die Handlungsleiste
  // niemals den Erzaehlstrang -- auch nicht bei langen Vorschlagslisten.
  return (
    <div className="mx-auto flex h-dvh w-full max-w-md flex-col overflow-hidden">
      {pendingReveal && (
        <DiceRollModal
          rolls={pendingReveal.rolls}
          characterNames={characterNames}
          onDismiss={() => setPendingReveal(null)}
        />
      )}

      {interventionOffer && (
        <InterventionPrompt
          gameId={state.game.id}
          token={token}
          offer={interventionOffer}
          onDone={() => setInterventionOffer(null)}
        />
      )}
      <div className="safe-top shrink-0">
        <StatusBar state={state} connected={connected} />
        {paused && (
          <p className="bg-ember-500/20 px-4 py-1.5 text-center text-xs font-semibold text-ember-400">
            Die Runde ist pausiert.
          </p>
        )}
        {finished && (
          <p className="bg-ink-700 px-4 py-1.5 text-center text-xs text-parchment/70">
            Die Runde ist beendet. Der Verlauf bleibt erhalten.
          </p>
        )}

        {/* Die Tonausgabe bleibt immer erreichbar und scrollt nicht mit dem
            Erzählstrang aus dem Bild. */}
        {tab === "story" && (
          <div className="border-b border-ink-700 bg-ink-900/95 px-4 py-2">
            <AudioControls
              gameId={state.game.id}
              token={token}
              isHost={state.is_host}
              playback={state.game.settings.audio_playback ?? "host"}
              enabled={state.game.settings.tts_enabled}
              audio={visibleAudio}
              latest={visibleLatestNarration}
              lastMessage={lastMessage}
            />
          </div>
        )}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {error && <ErrorNote>{error}</ErrorNote>}

        {tab === "story" && (
          <>
            <NarrationFeed
              narrations={visibleNarrations}
              rolls={visibleRolls}
              events={state.events}
              characterNames={characterNames}
            />
          </>
        )}

        {tab === "character" && (
          <>
            <CharacterSheet character={state.my_character} />
            <InventoryPanel character={state.my_character} />
            <PartyPanel
              players={state.players}
              characters={state.characters}
              submittedIds={state.turn?.submitted_player_ids ?? []}
              hostId={state.players.find((player) => player.role === "host")?.id ?? null}
            />
          </>
        )}

        {tab === "quests" && <QuestPanel quests={state.quests} />}

        {tab === "world" && (
          <WorldPanel
            locations={state.locations}
            entities={state.entities}
            facts={state.facts}
            knowledge={state.knowledge}
          />
        )}

        {tab === "log" && (
          <>
            <LogPanel events={state.events} />
            {state.is_host && (
              <Card title="Spielleitung">
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void run(() => api.resolveTurn(state.game.id, token))}
                  >
                    Zug aufloesen
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void run(() => api.renarrate(state.game.id, token))}
                  >
                    KI neu erzaehlen
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void run(() => api.skipScene(state.game.id, token))}
                  >
                    Szene ueberspringen
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void run(() => api.createSummary(state.game.id, token))}
                  >
                    Zusammenfassen
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void run(() => api.replayAudio(state.game.id, token))}
                  >
                    Audio wiederholen
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() =>
                      void run(() =>
                        paused
                          ? api.resume(state.game.id, token)
                          : api.pause(state.game.id, token),
                      )
                    }
                  >
                    {paused ? "Fortsetzen" : "Pausieren"}
                  </Button>
                </div>

                <div className="mt-3 space-y-1.5 border-t border-ink-700 pt-3">
                  {state.players
                    .filter((player) => player.is_active && player.role !== "host")
                    .map((player) => (
                      <div key={player.id} className="flex items-center justify-between gap-2">
                        <span className="text-sm">{player.name}</span>
                        <Button
                          variant="danger"
                          disabled={busy}
                          onClick={() => void run(() => api.kick(state.game.id, token, player.id))}
                        >
                          Entfernen
                        </Button>
                      </div>
                    ))}
                </div>

                {!finished && (
                  <Button
                    variant="danger"
                    className="mt-3 w-full"
                    disabled={busy}
                    onClick={() => void run(() => api.finish(state.game.id, token))}
                  >
                    Runde beenden
                  </Button>
                )}
              </Card>
            )}
            {state.is_host && state.active_location_turns && (
              <LocationOverviewPanel
                turns={state.active_location_turns}
                busy={busy}
                onResolve={(turnId) =>
                  void run(() => api.resolveTurn(state.game.id, token, turnId))
                }
              />
            )}
          </>
        )}
      </div>

      {tab === "story" && !finished && (
        <div className="max-h-[48dvh] shrink-0 overflow-y-auto border-t border-ink-700 bg-ink-900/95 px-4 py-3">
          <div className="mb-2 flex items-center justify-between text-xs text-parchment/50">
            <span>
              Zug {state.turn?.number ?? state.game.current_turn_number}
              {state.turn ? ` · ${state.turn.submitted_player_ids.length} bereit` : ""}
            </span>
            {paused && <Badge tone="warn">pausiert</Badge>}
          </div>
          <ActionBar
            character={state.my_character}
            hasSubmitted={hasSubmitted}
            disabled={busy || paused}
            onSubmit={async (payload) => {
              await run(() => api.submitAction(state.game.id, token, payload));
            }}
          />
        </div>
      )}

      <nav className="safe-bottom flex shrink-0 justify-between border-t border-ink-700 bg-ink-950/95">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            onClick={() => setTab(entry.id)}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] transition-colors ${
              tab === entry.id ? "text-ember-400" : "text-parchment/50"
            }`}
            aria-current={tab === entry.id ? "page" : undefined}
          >
            <span className="text-lg" aria-hidden>
              {entry.icon}
            </span>
            {entry.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
