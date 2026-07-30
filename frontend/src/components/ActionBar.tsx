/** Handlungsauswahl: Freitext, aufgeloest auf ein selbst gewaehltes Attribut. */

import { useState } from "react";

import type { Character } from "../lib/types";
import { CORE_STAT_LABELS, RESOURCE_POOL_KEYS } from "../lib/types";
import { Button } from "./ui";

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
  }) => Promise<void>;
}) {
  const [freeText, setFreeText] = useState("");
  const [markedItem, setMarkedItem] = useState<string | null>(null);
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
      });
      setFreeText("");
      setMarkedItem(null);
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
    <div className="space-y-3">
      <Button
        variant="ghost"
        className="w-full"
        disabled={disabled || busy}
        onClick={() => void send("wait", "Ich unternehme nichts und beobachte die Lage.")}
      >
        <span className="mr-1.5" aria-hidden>
          🧘
        </span>
        Nichts tun
      </Button>

      <input
        value={freeText}
        onChange={(event) => setFreeText(event.target.value)}
        disabled={disabled || busy}
        placeholder="Was tust du?"
        className="min-h-11 w-full rounded-xl border border-ink-600 bg-ink-900 px-3 text-base outline-none focus:border-ember-500 disabled:opacity-50"
      />

      {character.inventory.length > 0 && (
        <details className="rounded-xl border border-ink-700 bg-ink-800/60 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-parchment/80">
            Gegenstand markieren
          </summary>
          <p className="mt-1 text-xs text-parchment/50">
            Markiert den Gegenstand fuer die naechste Handlung -- sendet noch nichts ab.
          </p>
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

      <div>
        <p className="mb-1.5 text-xs text-parchment/50">
          Worauf wuerfelt diese Handlung? Die KI bewertet, ob die Wahl passt.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {rollableStats.map((stat) => (
            <button
              key={stat.key}
              type="button"
              disabled={disabled || busy || !freeText.trim()}
              onClick={() => void send(markedItem ? "use_item" : "custom", freeText, stat.key)}
              className="rounded-xl border border-ink-600 bg-ink-800 px-3 py-2 text-left text-sm font-semibold text-parchment transition active:scale-[0.98] disabled:opacity-50"
            >
              {CORE_STAT_LABELS[stat.key] ?? stat.key}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
