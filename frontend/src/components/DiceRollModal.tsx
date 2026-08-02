/** Wuerfel-Popup: zeigt das Ergebnis eines Zuges mit einer kurzen
 * Rollanimation, bevor die schon fertige Erzaehlung (samt Sprachausgabe)
 * sichtbar wird.
 *
 * Die KI und die Sprachaufnahme entstehen bereits im Hintergrund, waehrend
 * dieses Popup laeuft -- das Backend wartet nicht auf einen Klick. Erst
 * "Weiter" blendet das schon fertige Ergebnis ein und gibt den Ton frei;
 * das ist rein lokal, ohne weiteren Netzwerkaufruf.
 */

import { useEffect, useState } from "react";

import type { DiceRoll } from "../lib/types";
import { DEGREE_LABEL } from "./NarrationFeed";
import { Badge, Button, Modal } from "./ui";

const REVEAL_DELAY_MS = 850;

export function DiceRollModal({
  rolls,
  characterNames,
  onDismiss,
}: {
  rolls: DiceRoll[];
  characterNames: Record<string, string>;
  onDismiss: () => void;
}) {
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    setRevealed(false);
    const timer = window.setTimeout(() => setRevealed(true), REVEAL_DELAY_MS);
    return () => window.clearTimeout(timer);
    // Nur beim Erscheinen eines neuen Zuges neu starten, nicht bei jedem
    // Re-Render (rolls ist pro Zug stabil, aber ein neues Array-Objekt).
  }, [rolls.map((roll) => roll.id).join(",")]);

  return (
    <Modal>
      <h2 className="mb-4 text-center font-serif text-xl text-ember-400">
        {rolls.length > 1 ? "Die Wuerfel sind gefallen" : "Der Wuerfel ist gefallen"}
      </h2>

      <div className="space-y-3">
        {rolls.map((roll, index) => {
          const degree = DEGREE_LABEL[roll.degree] ?? {
            text: roll.degree,
            tone: "neutral" as const,
          };
          const critical = roll.degree === "critical_success" || roll.degree === "critical_failure";
          return (
            <div
              key={roll.id}
              className="rounded-xl border border-ink-600 bg-ink-900/70 p-3 text-center"
              style={{ animationDelay: `${index * 120}ms` }}
            >
              <p className="text-xs font-semibold uppercase tracking-wider text-parchment/50">
                {roll.character_id ? (characterNames[roll.character_id] ?? "Jemand") : "Probe"}
              </p>
              <p
                className={`my-1 text-4xl font-black tabular-nums text-parchment ${
                  revealed ? "" : "animate-dice-tumble"
                }`}
              >
                {revealed ? roll.total : "?"}
              </p>
              {roll.difficulty !== null && (
                <p className="text-xs text-parchment/50">gegen {roll.difficulty}</p>
              )}
              {revealed && (
                <div className={critical ? "animate-shake" : "animate-pop-in"}>
                  <Badge tone={degree.tone}>{degree.text}</Badge>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Button className="mt-5 w-full" disabled={!revealed} onClick={onDismiss}>
        Weiter
      </Button>
    </Modal>
  );
}
