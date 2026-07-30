/** Audio-Steuerung.
 *
 * Am Spieltisch soll genau ein Gerät sprechen — voreingestellt das der
 * Spielleitung. Zwei Quellen sind möglich: eine serverseitig erzeugte
 * Aufnahme (OpenAI oder ein lokales Modell) oder die Stimme des Browsers.
 * Liegt eine Aufnahme vor, hat sie Vorrang; sonst wird vorgelesen.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../lib/api";
import { audioSink, loadSinkPreferences, saveSinkPreferences } from "../lib/audioSink";
import { listVoices, speak, speechSupported, stopSpeaking } from "../lib/speech";
import type { AudioJob, Narration, RealtimeMessage } from "../lib/types";
import { Button } from "./ui";

const VOICE_KEY = "kipnp.audio.voice.v1";

export function AudioControls({
  gameId,
  token,
  isHost,
  playback,
  enabled,
  audio,
  latest,
  lastMessage,
}: {
  gameId: string;
  token: string;
  isHost: boolean;
  /** Vorgabe der Runde: host | all | none */
  playback: string;
  /** Wurde für diese Runde überhaupt Sprachausgabe gewünscht? */
  enabled: boolean;
  /** Jüngster Sprachauftrag des Servers. */
  audio: AudioJob | null;
  /** Jüngste Narration — Grundlage für das Vorlesen im Browser. */
  latest: Narration | null;
  lastMessage: RealtimeMessage | null;
}) {
  const [preferences, setPreferences] = useState(() => loadSinkPreferences(isHost));
  const [voiceName, setVoiceName] = useState(
    () => window.localStorage.getItem(VOICE_KEY) ?? "",
  );
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [status, setStatus] = useState<string>("");
  const spokenRef = useRef<string | null>(null);
  const blobsRef = useRef<string[]>([]);

  const allowedByGame =
    enabled && playback !== "none" && (playback === "all" || isHost || preferences.isSpeaker);
  const active = preferences.isSpeaker && allowedByGame;

  // Liegt eine Aufnahme des Servers vor oder ist eine unterwegs? Nur dann
  // schweigt das Gerät. Ein fehlgeschlagener Auftrag darf die Runde nicht
  // stumm lassen — dann liest der Browser vor.
  const serverPending = audio?.status === "pending" || audio?.status === "running";
  const serverReady = audio?.status === "ready" && Boolean(audio.url);
  // „skipped" heißt: es war bewusst nichts zu sprechen — etwa bei
  // TTS_PROVIDER=none oder leerem Text. Dann liest auch das Gerät nicht vor.
  const serverSkipped = audio?.status === "skipped";

  useEffect(() => saveSinkPreferences(preferences), [preferences]);

  // Sobald tatsächlich Ton läuft, ist die Freischaltung erledigt.
  useEffect(() => {
    audioSink.onStarted = () =>
      setPreferences((previous) =>
        previous.unlocked ? previous : { ...previous, unlocked: true },
      );
    return () => {
      audioSink.onStarted = null;
    };
  }, []);
  useEffect(() => window.localStorage.setItem(VOICE_KEY, voiceName), [voiceName]);

  useEffect(() => {
    if (!speechSupported()) return;
    const update = () => setVoices(listVoices("de"));
    update();
    window.speechSynthesis.addEventListener("voiceschanged", update);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", update);
  }, []);

  // Blob-Adressen wieder freigeben, wenn die Ansicht verschwindet.
  useEffect(
    () => () => {
      blobsRef.current.forEach((url) => URL.revokeObjectURL(url));
      blobsRef.current = [];
    },
    [],
  );

  const playServerAudio = useCallback(
    async (job: AudioJob, immediate = false) => {
      try {
        const url = await api.fetchAudioUrl(gameId, token, job.id);
        blobsRef.current.push(url);
        if (immediate) await audioSink.playNow(url);
        else audioSink.enqueue(url, job.id);
        setStatus("");
      } catch {
        setStatus("Aufnahme konnte nicht geladen werden.");
      }
    },
    [gameId, token],
  );

  // Neue Aufnahme oder neue Narration abspielen — jede nur einmal.
  useEffect(() => {
    if (!active) return;

    if (serverReady && audio) {
      if (spokenRef.current === audio.id) return;
      spokenRef.current = audio.id;
      void playServerAudio(audio);
      return;
    }

    if (serverPending) {
      setStatus("Aufnahme wird erzeugt ...");
      return;
    }
    if (serverSkipped) return;

    // Keine Aufnahme zu erwarten — sei es, weil keine angefordert wurde, oder
    // weil die Vertonung scheiterte. In beiden Fällen liest der Browser vor,
    // damit am Tisch niemand auf die Erzählung wartet.
    if (audio?.status === "failed") {
      setStatus("Serverstimme nicht erreichbar — das Gerät liest vor.");
    }
    if (latest) {
      if (spokenRef.current === latest.id) return;
      spokenRef.current = latest.id;
      speak(latest.text, { voiceName: voiceName || undefined });
    }
  }, [active, audio, serverPending, serverReady, serverSkipped, latest, voiceName, playServerAudio]);

  // Der Spielleiter kann die Wiedergabe für alle erneut auslösen.
  useEffect(() => {
    if (!active || !lastMessage || lastMessage.type !== "audio.replay") return;
    const payload = lastMessage.payload as { audio_id?: string; text?: string };
    if (payload.audio_id && audio && payload.audio_id === audio.id && serverReady) {
      void playServerAudio(audio, true);
    } else if (payload.text) {
      speak(payload.text, { voiceName: voiceName || undefined });
    }
  }, [active, lastMessage, audio, serverReady, voiceName, playServerAudio]);

  const toggleSpeaker = async () => {
    // Ist dieses Gerät schon als Lautsprecher gewählt, aber noch nicht
    // freigeschaltet, dient die Berührung genau dieser Freischaltung. Würde
    // sie stattdessen stumm schalten, bräuchte es auf dem iPhone zwei
    // Berührungen — und die erste bewirkte das Gegenteil des Gewünschten.
    if (preferences.isSpeaker && !preferences.unlocked) {
      const unlocked = await audioSink.unlock();
      setPreferences({ isSpeaker: true, unlocked });
      // Eine wartende Aufnahme in derselben Berührung nachholen. Gelingt das,
      // ist die Freischaltung ohnehin erledigt — audioSink meldet es über
      // onStarted. Damit genügt ein Antippen, selbst wenn der Browser die
      // tonlose Datei ablehnt.
      if (serverReady && audio) void playServerAudio(audio, true);
      else audioSink.resume();
      setStatus(unlocked ? "" : "Der Browser gibt den Ton nicht frei. Bitte erneut antippen.");
      return;
    }

    if (preferences.isSpeaker) {
      audioSink.stop();
      stopSpeaking();
      setPreferences({ ...preferences, isSpeaker: false });
      return;
    }

    // Aus der Nutzeraktion heraus freischalten — iOS verlangt das.
    const unlocked = await audioSink.unlock();
    setPreferences({ isSpeaker: true, unlocked });
    if (!unlocked) setStatus("Zum Freischalten des Tons noch einmal antippen.");
    else {
      setStatus("");
      audioSink.resume();
    }
  };

  const repeat = () => {
    if (serverReady && audio) void playServerAudio(audio, true);
    else if (latest) speak(latest.text, { voiceName: voiceName || undefined });
  };

  // „Serverstimme" nur behaupten, wenn tatsächlich eine Aufnahme vorliegt oder
  // unterwegs ist — nach einem Fehlschlag spricht das Gerät selbst.
  const serverSide = serverPending || serverReady;

  // Gewählt, aber noch nicht freigeschaltet: dann ist die Berührung zum
  // Freischalten gemeint und nicht zum Stummschalten.
  const needsUnlock = active && !preferences.unlocked;

  // Ohne Sprachausgabe für diese Runde gibt es nichts zu bedienen.
  if (!enabled) {
    return (
      <p className="text-xs text-parchment/45">
        Für diese Runde ist die Sprachausgabe abgeschaltet.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Button
          variant={active ? "primary" : "ghost"}
          className="px-3"
          onClick={() => void toggleSpeaker()}
          title={
            needsUnlock
              ? "Ton freischalten — der Browser verlangt eine Berührung"
              : active
                ? "Dieses Gerät gibt Ton aus"
                : "Dieses Gerät ist stumm"
          }
        >
          {needsUnlock ? "🔊 Freischalten" : active ? "🔊 Ton hier" : "🔇 Stumm"}
        </Button>

        <Button
          variant="ghost"
          className="px-3"
          disabled={!latest && !audio}
          onClick={repeat}
          title="Zuletzt Erzähltes erneut abspielen"
        >
          ↻
        </Button>

        <Button
          variant="subtle"
          className="px-2"
          onClick={() => {
            audioSink.stop();
            stopSpeaking();
          }}
        >
          Stopp
        </Button>

        <span className="ml-auto text-[11px] text-parchment/45">
          {serverSide ? "Serverstimme" : speechSupported() ? "Gerätestimme" : "kein Ton"}
        </span>
      </div>

      {/* Die Stimmenauswahl gilt nur für das Vorlesen im Browser. */}
      {active && !serverSide && voices.length > 0 && (
        <select
          value={voiceName}
          onChange={(event) => setVoiceName(event.target.value)}
          className="min-h-11 w-full rounded-xl border border-ink-600 bg-ink-900 px-2 text-sm"
          aria-label="Stimme"
        >
          <option value="">Standardstimme des Geräts</option>
          {voices.map((voice) => (
            <option key={voice.name} value={voice.name}>
              {voice.name}
            </option>
          ))}
        </select>
      )}

      {needsUnlock && (
        <p className="text-xs text-ember-400">
          Safari braucht eine Berührung: einmal auf „Freischalten" tippen, danach
          spielt jede Aufnahme von selbst.
        </p>
      )}

      {status && <p className="text-xs text-parchment/55">{status}</p>}

      {!active && playback === "host" && !isHost && (
        <p className="text-xs text-parchment/45">
          Der Ton läuft über das Gerät der Spielleitung. Zum Mithören hier auf
          „Stumm" tippen.
        </p>
      )}
    </div>
  );
}
