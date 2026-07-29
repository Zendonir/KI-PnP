/** Audio-Steuerung: liest die Narration vor und merkt sich die Einstellung. */

import { useEffect, useRef, useState } from "react";

import { listVoices, speak, speechSupported, stopSpeaking } from "../lib/speech";
import type { Narration } from "../lib/types";
import { Button } from "./ui";

const STORAGE_KEY = "kipnp.audio.v1";

interface AudioPreferences {
  enabled: boolean;
  voiceName: string;
}

function loadPreferences(): AudioPreferences {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as AudioPreferences;
  } catch {
    /* Voreinstellung verwenden */
  }
  return { enabled: false, voiceName: "" };
}

export function AudioControls({ latest }: { latest: Narration | null }) {
  const [preferences, setPreferences] = useState<AudioPreferences>(loadPreferences);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const spokenRef = useRef<string | null>(null);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  }, [preferences]);

  useEffect(() => {
    if (!speechSupported()) return;
    const update = () => setVoices(listVoices("de"));
    update();
    window.speechSynthesis.addEventListener("voiceschanged", update);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", update);
  }, []);

  // Neue Narration automatisch vorlesen, jede aber nur einmal.
  useEffect(() => {
    if (!preferences.enabled || !latest) return;
    if (spokenRef.current === latest.id) return;
    spokenRef.current = latest.id;
    speak(latest.text, { voiceName: preferences.voiceName || undefined });
  }, [latest, preferences]);

  if (!speechSupported()) {
    return (
      <p className="text-xs text-parchment/50">
        Dieser Browser unterstuetzt keine Sprachausgabe.
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant={preferences.enabled ? "primary" : "ghost"}
        onClick={() => {
          const enabled = !preferences.enabled;
          if (!enabled) stopSpeaking();
          setPreferences({ ...preferences, enabled });
        }}
      >
        {preferences.enabled ? "🔊 Vorlesen an" : "🔇 Vorlesen aus"}
      </Button>

      <Button
        variant="ghost"
        disabled={!latest}
        onClick={() =>
          latest && speak(latest.text, { voiceName: preferences.voiceName || undefined })
        }
      >
        ↻ Wiederholen
      </Button>

      <Button variant="subtle" onClick={stopSpeaking}>
        Stopp
      </Button>

      {voices.length > 0 && (
        <select
          value={preferences.voiceName}
          onChange={(event) => setPreferences({ ...preferences, voiceName: event.target.value })}
          className="min-h-11 rounded-xl border border-ink-600 bg-ink-900 px-2 text-sm"
          aria-label="Stimme"
        >
          <option value="">Standardstimme</option>
          {voices.map((voice) => (
            <option key={voice.name} value={voice.name}>
              {voice.name}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
