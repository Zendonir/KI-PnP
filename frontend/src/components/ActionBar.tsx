/** Handlungsauswahl: Freitext, aufgeloest auf ein selbst gewaehltes Attribut. */

import { useEffect, useRef, useState } from "react";

import type { Character } from "../lib/types";
import { CORE_STAT_LABELS, RESOURCE_POOL_KEYS } from "../lib/types";
import { Button } from "./ui";

const SpeechRecognitionCtor =
  typeof window !== "undefined" ? window.SpeechRecognition ?? window.webkitSpeechRecognition : undefined;

export function ActionBar({
  character,
  hasSubmitted,
  disabled,
  onSubmit,
}: {
  character: Character | null;
  hasSubmitted: boolean;
  disabled: boolean;
  onSubmit: (payload: {
    kind: string;
    text: string;
    stat?: string;
    payload?: Record<string, unknown>;
    group_event?: boolean;
  }) => Promise<void>;
}) {
  const [freeText, setFreeText] = useState("");
  const [markedItem, setMarkedItem] = useState<string | null>(null);
  const [groupEvent, setGroupEvent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const dictationBaseRef = useRef("");

  useEffect(() => {
    return () => recognitionRef.current?.stop();
  }, []);

  useEffect(() => {
    if (hasSubmitted) recognitionRef.current?.stop();
  }, [hasSubmitted]);

  const toggleDictation = () => {
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    if (!SpeechRecognitionCtor) return;
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "de-DE";
    recognition.continuous = true;
    recognition.interimResults = true;
    dictationBaseRef.current = freeText.trim();
    recognition.onresult = (event) => {
      let transcript = "";
      for (let index = 0; index < event.results.length; index += 1) {
        transcript += event.results[index][0].transcript;
      }
      const combined = dictationBaseRef.current
        ? `${dictationBaseRef.current} ${transcript}`
        : transcript;
      setFreeText(combined.trim());
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  };

  if (!character) {
    return (
      <p className="text-sm text-parchment/60">
        Du brauchst einen Charakter, um handeln zu koennen.
      </p>
    );
  }

  if (!character.is_alive) {
    return (
      <p className="rounded-xl bg-blood-500/15 px-3 py-2 text-sm text-parchment">
        {character.name} ist nicht handlungsfaehig und setzt aus.
      </p>
    );
  }

  // Ressourcen-Pools (hp/mana/stamina) sind keine waehlbaren Attribute --
  // alles andere sind entweder die vier Grundattribute oder selbst benannte
  // Skills, beides gleichberechtigt waehlbar.
  const rollableStats = character.stats.filter((stat) => !RESOURCE_POOL_KEYS.has(stat.key));

  const send = async (kind: string, text: string, stat?: string) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      await onSubmit({
        kind,
        text: text.trim(),
        ...(stat ? { stat } : {}),
        ...(markedItem ? { payload: { item: markedItem } } : {}),
        ...(kind !== "wait" && groupEvent ? { group_event: true } : {}),
      });
      setFreeText("");
      setMarkedItem(null);
      setGroupEvent(false);
    } finally {
      setBusy(false);
    }
  };

  if (hasSubmitted) {
    return (
      <div className="flex items-center gap-2 text-sm text-parchment/70">
        <span className="rounded-full bg-moss-500/20 px-2 py-0.5 text-xs font-semibold text-moss-400">
          Eingereicht
        </span>
        <span>Warte auf die uebrigen Spieler ...</span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          value={freeText}
          onChange={(event) => setFreeText(event.target.value)}
          disabled={disabled || busy}
          placeholder="Was tust du?"
          className="min-h-11 flex-1 rounded-xl border border-ink-600 bg-ink-900 px-3 text-base outline-none focus:border-ember-500 disabled:opacity-50"
        />
        {SpeechRecognitionCtor && (
          <Button
            variant="ghost"
            disabled={disabled || busy}
            onClick={toggleDictation}
            title={listening ? "Aufnahme beenden" : "Diktieren"}
            aria-label={listening ? "Aufnahme beenden" : "Diktieren"}
            className={listening ? "animate-pulse !border-blood-500 !text-blood-400" : ""}
          >
            <span aria-hidden>{listening ? "⏹" : "🎤"}</span>
          </Button>
        )}
        <Button
          variant="ghost"
          disabled={disabled || busy}
          onClick={() => void send("wait", "Ich unternehme nichts und beobachte die Lage.")}
          title="Nichts tun"
          aria-label="Nichts tun"
        >
          <span aria-hidden>🧘</span>
        </Button>
      </div>

      {listening && (
        <p className="text-xs text-blood-400">
          🎤 Aufnahme laeuft -- sprich deine Handlung, der Text bleibt danach bearbeitbar, bevor
          du ihn abschickst.
        </p>
      )}

      <button
        type="button"
        disabled={disabled || busy}
        onClick={() => setGroupEvent((current) => !current)}
        className={`flex w-full items-center gap-2 rounded-xl border px-3 py-1.5 text-left text-xs font-semibold transition disabled:opacity-50 ${
          groupEvent
            ? "border-ember-500 bg-ember-500/20 text-ember-400"
            : "border-ink-700 bg-ink-800/60 text-parchment/70"
        }`}
      >
        <span aria-hidden>🤝</span>
        Als Gruppenereignis vorschlagen -- andere am Ort werden gefragt, ob sie mitmachen
      </button>

      {character.inventory.length > 0 && (
        <details className="rounded-xl border border-ink-700 bg-ink-800/60 px-3 py-2">
          <summary className="cursor-pointer text-xs font-semibold text-parchment/70">
            Gegenstand markieren
          </summary>
          <div className="mt-2 flex flex-wrap gap-2">
            {character.inventory.map((entry) => {
              const active = markedItem === entry.name;
              return (
                <button
                  key={entry.id}
                  type="button"
                  disabled={disabled || busy}
                  onClick={() => setMarkedItem(active ? null : entry.name)}
                  className={`rounded-full border px-3 py-1.5 text-sm transition disabled:opacity-50 ${
                    active
                      ? "border-ember-500 bg-ember-500/20 text-ember-400"
                      : "border-ink-600 bg-ink-800 text-parchment/80"
                  }`}
                >
                  {entry.name}
                  {entry.quantity > 1 ? ` x${entry.quantity}` : ""}
                </button>
              );
            })}
          </div>
        </details>
      )}

      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        <span className="shrink-0 text-xs text-parchment/50">Attribut:</span>
        {rollableStats.map((stat) => (
          <button
            key={stat.key}
            type="button"
            disabled={disabled || busy || !freeText.trim()}
            onClick={() => void send(markedItem ? "use_item" : "custom", freeText, stat.key)}
            className="min-h-9 shrink-0 whitespace-nowrap rounded-full border border-ink-600 bg-ink-800 px-3 py-1.5 text-sm font-semibold text-parchment transition active:scale-[0.98] disabled:opacity-50"
          >
            {CORE_STAT_LABELS[stat.key] ?? stat.key}
          </button>
        ))}
      </div>
    </div>
  );
}
