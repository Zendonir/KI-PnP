/** Gruppenereignis: jemand schlaegt eine gemeinsame Handlung vor.
 *
 * Anders als das kurze Quick-Time-Event gibt es hier kein Zeitlimit -- der
 * Zug wartet echt auf eine Antwort von jeder betroffenen Person, das Banner
 * bleibt also stehen, bis "Mitmachen" oder "Eigene Handlung" gewaehlt wird.
 */

import { useState } from "react";

import { api } from "../lib/api";
import type { GroupProposal } from "../lib/types";
import { Button } from "./ui";

export function GroupProposalPrompt({
  gameId,
  token,
  proposal,
  onDone,
}: {
  gameId: string;
  token: string;
  proposal: GroupProposal;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);

  const respond = async (accepted: boolean) => {
    setBusy(true);
    try {
      await api.respondGroupProposal(gameId, token, proposal.id, accepted);
    } catch {
      /* Schon beantwortet oder der Zug ist inzwischen weiter -- das Banner
         schliesst sich ohnehin. */
    } finally {
      onDone();
    }
  };

  return (
    <div
      className="animate-pop-in fixed top-16 left-1/2 z-40 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2
        rounded-2xl border border-ember-500/60 bg-ink-900 p-4 shadow-2xl"
    >
      <p className="text-sm font-bold text-ember-400">Gruppenereignis</p>
      <p className="mt-1 text-sm text-parchment/80">
        {proposal.initiator_name} schl&auml;gt vor: &bdquo;{proposal.text}&ldquo;
      </p>
      <div className="mt-3 flex gap-2">
        <Button
          variant="ghost"
          className="flex-1"
          disabled={busy}
          onClick={() => void respond(false)}
        >
          Eigene Handlung
        </Button>
        <Button className="flex-1" disabled={busy} onClick={() => void respond(true)}>
          Mitmachen
        </Button>
      </div>
    </div>
  );
}
