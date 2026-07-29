/** Erzaehlstrang: oeffentliche Narration, private Hinweise und Wuerfelergebnisse. */

import { useEffect, useRef } from "react";

import type { DiceRoll, GameEvent, Narration } from "../lib/types";
import { Badge } from "./ui";

const DEGREE_LABEL: Record<string, { text: string; tone: "good" | "bad" | "warn" | "neutral" }> = {
  critical_success: { text: "Kritischer Erfolg", tone: "good" },
  success: { text: "Erfolg", tone: "good" },
  partial: { text: "Teilerfolg", tone: "warn" },
  failure: { text: "Fehlschlag", tone: "bad" },
  critical_failure: { text: "Patzer", tone: "bad" },
};

interface FeedItem {
  key: string;
  at: number;
  node: React.ReactNode;
}

export function NarrationFeed({
  narrations,
  rolls,
  events,
  characterNames,
}: {
  narrations: Narration[];
  rolls: DiceRoll[];
  events: GameEvent[];
  characterNames: Record<string, string>;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [narrations.length, rolls.length]);

  const items: FeedItem[] = [];

  for (const narration of narrations) {
    items.push({
      key: `n-${narration.id}`,
      at: Date.parse(narration.created_at),
      node: (
        <article
          className={`animate-enter rounded-2xl border p-4 ${
            narration.kind === "private"
              ? "border-ember-500/40 bg-ember-500/5"
              : "border-ink-700 bg-ink-800/70"
          }`}
        >
          {narration.kind === "private" && (
            <p className="mb-2 text-[11px] font-bold uppercase tracking-widest text-ember-400">
              Nur fuer dich
            </p>
          )}
          {narration.scene_title && narration.kind === "public" && (
            <h3 className="mb-2 font-serif text-lg text-ember-400">{narration.scene_title}</h3>
          )}
          <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-parchment/90">
            {narration.text}
          </p>
        </article>
      ),
    });
  }

  for (const roll of rolls) {
    const degree = DEGREE_LABEL[roll.degree] ?? { text: roll.degree, tone: "neutral" as const };
    items.push({
      key: `d-${roll.id}`,
      at: Date.parse(roll.created_at),
      node: (
        <div className="animate-enter flex flex-wrap items-center gap-2 rounded-xl border border-ink-700 bg-ink-900/60 px-3 py-2 text-sm">
          <span className="text-lg" aria-hidden>
            🎲
          </span>
          <span className="font-semibold text-parchment">
            {roll.character_id ? (characterNames[roll.character_id] ?? "Jemand") : "Probe"}
          </span>
          <span className="text-parchment/60">
            {roll.notation}
            {roll.modifier !== 0 && (roll.modifier > 0 ? ` +${roll.modifier}` : ` ${roll.modifier}`)}
          </span>
          <span className="tabular-nums font-bold text-ember-400">{roll.total}</span>
          {roll.difficulty !== null && (
            <span className="text-parchment/50">gegen {roll.difficulty}</span>
          )}
          <Badge tone={degree.tone}>{degree.text}</Badge>
          <span className="basis-full text-xs text-parchment/40">
            Wuerfe: {roll.rolls.join(", ")}
            {roll.reason ? ` - ${roll.reason}` : ""}
          </span>
        </div>
      ),
    });
  }

  for (const event of events.filter((item) => item.type === "action.rejected")) {
    items.push({
      key: `e-${event.id}`,
      at: Date.parse(event.created_at),
      node: (
        <div className="animate-enter rounded-xl border border-blood-500/40 bg-blood-500/10 px-3 py-2 text-sm text-parchment/90">
          {event.summary}
        </div>
      ),
    });
  }

  items.sort((a, b) => a.at - b.at);

  if (items.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-ink-600 p-6 text-center text-sm text-parchment/50">
        Die Geschichte hat noch nicht begonnen.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.key}>{item.node}</div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
