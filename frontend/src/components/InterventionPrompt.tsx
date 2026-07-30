/** Quick-Time-Event: kurzes Angebot, jetzt einzugreifen und zu helfen.
 *
 * Erscheint nur fuer die eine, zufaellig ausgewaehlte Person und nur selten
 * -- daher bewusst als ploetzlich auftauchendes Banner statt als weiterer
 * Dialog, der den Bildschirm blockiert. Reagiert niemand rechtzeitig, laeuft
 * das Zeitfenster serverseitig ohnehin ab; hier wird nur mitgezaehlt.
 *
 * "Nichts unternehmen" ist bewusst ein eigener, fest oben mittig
 * verankerter Knopf -- unabhaengig von der Karte darunter, sodass sich das
 * Angebot immer an derselben Stelle wegtippen laesst, ohne erst die Karte
 * lesen zu muessen.
 */

import { useEffect, useState } from "react";

import { api } from "../lib/api";
import type { InterventionOffer } from "../lib/types";
import { Button } from "./ui";

export function InterventionPrompt({
  gameId,
  token,
  offer,
  onDone,
}: {
  gameId: string;
  token: string;
  offer: InterventionOffer;
  onDone: () => void;
}) {
  const [remaining, setRemaining] = useState(offer.timeout_seconds);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const start = Date.now();
    setRemaining(offer.timeout_seconds);
    const interval = window.setInterval(() => {
      const left = offer.timeout_seconds - (Date.now() - start) / 1000;
      if (left <= 0) {
        window.clearInterval(interval);
        setRemaining(0);
        onDone();
        return;
      }
      setRemaining(left);
    }, 100);
    return () => window.clearInterval(interval);
    // Nur bei einem neuen Angebot neu starten.
  }, [offer.intervention_id, offer.timeout_seconds, onDone]);

  const respond = async (accepted: boolean) => {
    setBusy(true);
    try {
      await api.respondIntervention(gameId, token, offer.intervention_id, accepted);
    } catch {
      /* Zu spaet oder schon beantwortet -- das Fenster schliesst sich ohnehin. */
    } finally {
      onDone();
    }
  };

  const ratio = Math.max(0, Math.min(1, remaining / offer.timeout_seconds));

  return (
    <>
      {/* Immer an derselben Stelle -- oben mittig, fest -- unabhaengig vom
          Text der Karte darunter. */}
      <button
        type="button"
        disabled={busy}
        onClick={() => void respond(false)}
        className="fixed top-4 left-1/2 z-50 -translate-x-1/2 rounded-full border border-ink-600
          bg-ink-900/95 px-4 py-1.5 text-xs font-semibold text-parchment/70 shadow-lg backdrop-blur
          transition-colors hover:text-parchment disabled:opacity-50"
      >
        Nichts unternehmen
      </button>

      <div
        className="animate-pop-in fixed top-16 left-1/2 z-40 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2
          rounded-2xl border border-ember-500/60 bg-ink-900 p-4 shadow-2xl"
      >
        <p className="text-sm font-bold text-ember-400">Jetzt eingreifen?</p>
        <p className="mt-1 text-sm text-parchment/80">
          {offer.actor} k&ouml;nnte Hilfe gebrauchen bei: &bdquo;{offer.action_text}&ldquo;
        </p>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-ink-700">
          <div
            className="h-full rounded-full bg-ember-500 transition-[width] duration-100 ease-linear"
            style={{ width: `${ratio * 100}%` }}
          />
        </div>
        <Button className="mt-3 w-full" disabled={busy} onClick={() => void respond(true)}>
          Eingreifen!
        </Button>
      </div>
    </>
  );
}
