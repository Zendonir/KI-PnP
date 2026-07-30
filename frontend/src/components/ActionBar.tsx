/** Handlungsauswahl: Vorschlaege der KI plus freie Eingabe. */

import { useState } from "react";

import type { Character, Suggestion, Turn } from "../lib/types";
import { Badge, Button } from "./ui";

const KIND_ICONS: Record<string, string> = {
  attack: "⚔️",
  investigate: "🔍",
  talk: "💬",
  sneak: "🥷",
  cast: "✨",
  use_item: "🎒",
  flee: "🏃",
  wait: "🧘",
  custom: "✍️",
};

const FALLBACK: Suggestion[] = [
  { kind: "investigate", label: "Umgebung untersuchen", hint: "" },
  { kind: "talk", label: "Gespraech suchen", hint: "" },
  { kind: "sneak", label: "Vorsichtig vorgehen", hint: "" },
  { kind: "attack", label: "Angreifen", hint: "" },
];

export function ActionBar({
  turn,
  character,
  hasSubmitted,
  disabled,
  onSubmit,
}: {
  turn: Turn | null;
  character: Character | null;
  hasSubmitted: boolean;
  disabled: boolean;
  onSubmit: (payload: { kind: string; text: string; payload?: Record<string, unknown> }) => Promise<void>;
}) {
  const [freeText, setFreeText] = useState("");
  const [busy, setBusy] = useState(false);

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

  const suggestions = turn?.my_suggestions?.length ? turn.my_suggestions : FALLBACK;

  const send = async (kind: string, text: string, extra?: Record<string, unknown>) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      await onSubmit({ kind, text: text.trim(), payload: extra });
      setFreeText("");
    } finally {
      setBusy(false);
    }
  };

  if (hasSubmitted) {
    return (
      <div className="flex items-center gap-2 text-sm text-parchment/70">
        <Badge tone="good">Eingereicht</Badge>
        <span>Warte auf die uebrigen Spieler ...</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        {suggestions.map((suggestion, index) => (
          <button
            key={`${suggestion.kind}-${index}`}
            type="button"
            disabled={disabled || busy}
            onClick={() => void send(suggestion.kind, suggestion.label)}
            className="flex min-h-16 flex-col items-start gap-1 rounded-xl border border-ink-600 bg-ink-800 p-3 text-left transition active:scale-[0.98] disabled:opacity-50"
          >
            <span className="text-sm font-semibold text-parchment">
              <span className="mr-1.5" aria-hidden>
                {KIND_ICONS[suggestion.kind] ?? "•"}
              </span>
              {suggestion.label}
            </span>
            {suggestion.hint && (
              <span className="text-xs text-parchment/50">{suggestion.hint}</span>
            )}
          </button>
        ))}
      </div>

      <Button
        variant="ghost"
        className="w-full"
        disabled={disabled || busy}
        onClick={() => void send("wait", "Ich unternehme nichts und beobachte die Lage.")}
      >
        <span className="mr-1.5" aria-hidden>
          {KIND_ICONS.wait}
        </span>
        Nichts tun
      </Button>

      <div className="flex gap-2">
        <input
          value={freeText}
          onChange={(event) => setFreeText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void send("custom", freeText);
          }}
          disabled={disabled || busy}
          placeholder="Eigene Handlung ..."
          className="min-h-11 flex-1 rounded-xl border border-ink-600 bg-ink-900 px-3 text-base outline-none focus:border-ember-500 disabled:opacity-50"
        />
        <Button
          onClick={() => void send("custom", freeText)}
          disabled={disabled || busy || !freeText.trim()}
        >
          {busy ? "..." : "Los"}
        </Button>
      </div>

      {character.inventory.length > 0 && (
        <details className="rounded-xl border border-ink-700 bg-ink-800/60 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-parchment/80">
            Gegenstand einsetzen
          </summary>
          <div className="mt-2 flex flex-wrap gap-2">
            {character.inventory.map((entry) => (
              <Button
                key={entry.id}
                variant="ghost"
                disabled={disabled || busy}
                onClick={() =>
                  void send("use_item", `Ich benutze ${entry.name}.`, { item: entry.name })
                }
              >
                {entry.name}
                {entry.quantity > 1 ? ` x${entry.quantity}` : ""}
              </Button>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
