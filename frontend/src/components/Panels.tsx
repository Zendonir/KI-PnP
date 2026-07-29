/** Ansichten fuer Charakter, Inventar, Quests, Gruppe und Welt. */

import type {
  Character,
  Fact,
  GameEvent,
  Player,
  Quest,
  WorldEntity,
  WorldLocation,
} from "../lib/types";
import { Badge, Card, StatBar } from "./ui";

const PRIMARY_STATS = ["hp", "mana", "stamina"];

/** Deutsche Bezeichner der gaengigen Attribute. */
const STAT_LABELS: Record<string, string> = {
  strength: "Staerke",
  dexterity: "Geschick",
  intelligence: "Verstand",
  charisma: "Ausstrahlung",
  constitution: "Konstitution",
  wisdom: "Weisheit",
  perception: "Wahrnehmung",
};

export function CharacterSheet({ character }: { character: Character | null }) {
  if (!character) {
    return (
      <Card title="Charakter">
        <p className="text-sm text-parchment/60">Noch kein Charakter erstellt.</p>
      </Card>
    );
  }

  const bars = character.stats.filter((stat) => PRIMARY_STATS.includes(stat.key));
  const attributes = character.stats.filter((stat) => !PRIMARY_STATS.includes(stat.key));

  return (
    <Card
      title="Charakter"
      action={
        character.is_alive ? (
          <Badge tone="good">handlungsfaehig</Badge>
        ) : (
          <Badge tone="bad">ausser Gefecht</Badge>
        )
      }
    >
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-ink-700 text-2xl">
          {character.avatar || "🎲"}
        </div>
        <div className="min-w-0">
          <p className="truncate font-serif text-lg text-parchment">{character.name}</p>
          <p className="truncate text-xs text-parchment/60">
            {[character.race, character.class].filter(Boolean).join(" · ")} · Stufe{" "}
            {character.level}
          </p>
        </div>
      </div>

      <div className="space-y-2">
        {bars.map((stat) => (
          <StatBar key={stat.key} stat={stat} />
        ))}
      </div>

      {attributes.length > 0 && (
        <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
          {attributes.map((stat) => (
            <div
              key={stat.key}
              className="flex justify-between rounded-lg bg-ink-900/60 px-2.5 py-1.5"
            >
              <dt className="text-parchment/60 capitalize">
                {STAT_LABELS[stat.key] ?? stat.key}
              </dt>
              <dd className="tabular-nums font-semibold">{stat.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {character.conditions.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {character.conditions.map((condition) => (
            <Badge key={condition} tone="warn">
              {condition}
            </Badge>
          ))}
        </div>
      )}

      {character.abilities.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-parchment/50">
            Faehigkeiten
          </p>
          <div className="flex flex-wrap gap-1.5">
            {character.abilities.map((ability) => (
              <Badge key={ability}>{ability}</Badge>
            ))}
          </div>
        </div>
      )}

      {character.background && (
        <p className="mt-4 border-t border-ink-700 pt-3 text-sm italic text-parchment/60">
          {character.background}
        </p>
      )}
    </Card>
  );
}

export function InventoryPanel({ character }: { character: Character | null }) {
  const entries = character?.inventory ?? [];
  return (
    <Card title={`Inventar (${entries.length})`}>
      {entries.length === 0 ? (
        <p className="text-sm text-parchment/60">Die Taschen sind leer.</p>
      ) : (
        <ul className="space-y-1.5">
          {entries.map((entry) => (
            <li
              key={entry.id}
              className="flex items-start justify-between gap-3 rounded-lg bg-ink-900/60 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {entry.name}
                  {entry.quantity > 1 && (
                    <span className="ml-1 text-parchment/50">x{entry.quantity}</span>
                  )}
                </p>
                {entry.description && (
                  <p className="truncate text-xs text-parchment/50">{entry.description}</p>
                )}
              </div>
              {entry.equipped && <Badge tone="good">angelegt</Badge>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

const QUEST_TONE: Record<string, "good" | "bad" | "warn" | "neutral"> = {
  completed: "good",
  failed: "bad",
  active: "warn",
  open: "neutral",
  hidden: "neutral",
};

export function QuestPanel({ quests }: { quests: Quest[] }) {
  const open = quests.filter((quest) => !["completed", "failed"].includes(quest.status));
  const closed = quests.filter((quest) => ["completed", "failed"].includes(quest.status));

  return (
    <Card title={`Quests (${open.length} offen)`}>
      {quests.length === 0 ? (
        <p className="text-sm text-parchment/60">Noch keine Auftraege.</p>
      ) : (
        <ul className="space-y-2">
          {[...open, ...closed].map((quest) => (
            <li key={quest.id} className="rounded-lg bg-ink-900/60 p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold">
                  {quest.is_main && <span className="mr-1 text-ember-400">★</span>}
                  {quest.title}
                </p>
                <Badge tone={QUEST_TONE[quest.status] ?? "neutral"}>{quest.status}</Badge>
              </div>
              {quest.description && (
                <p className="mt-1 text-xs text-parchment/60">{quest.description}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function PartyPanel({
  players,
  characters,
  submittedIds,
  hostId,
}: {
  players: Player[];
  characters: Character[];
  submittedIds: string[];
  hostId: string | null;
}) {
  return (
    <Card title="Gruppe">
      <ul className="space-y-2">
        {players
          .filter((player) => player.is_active)
          .map((player) => {
            const character = characters.find((item) => item.player_id === player.id);
            return (
              <li
                key={player.id}
                className="flex items-center gap-3 rounded-lg bg-ink-900/60 px-3 py-2"
              >
                <span className="text-xl" aria-hidden>
                  {character?.avatar || "👤"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {character?.name ?? player.name}
                    {player.id === hostId && (
                      <span className="ml-1.5 text-xs text-ember-400">(Leitung)</span>
                    )}
                  </p>
                  <p className="truncate text-xs text-parchment/50">
                    {character
                      ? `${character.class || "Abenteurer"} · ${player.name}`
                      : "erstellt noch einen Charakter"}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      player.is_connected ? "bg-moss-500" : "bg-ink-600"
                    }`}
                    title={player.is_connected ? "verbunden" : "offline"}
                  />
                  {submittedIds.includes(player.id) && <Badge tone="good">bereit</Badge>}
                </div>
              </li>
            );
          })}
      </ul>
    </Card>
  );
}

export function WorldPanel({
  locations,
  entities,
  facts,
  knowledge,
}: {
  locations: WorldLocation[];
  entities: WorldEntity[];
  facts: Fact[];
  knowledge: string[];
}) {
  return (
    <div className="space-y-4">
      <Card title={`Orte (${locations.length})`}>
        {locations.length === 0 ? (
          <p className="text-sm text-parchment/60">Noch nichts entdeckt.</p>
        ) : (
          <ul className="space-y-2">
            {locations.map((location) => (
              <li key={location.id} className="rounded-lg bg-ink-900/60 p-3">
                <p className="text-sm font-semibold">{location.name}</p>
                {location.description && (
                  <p className="mt-1 text-xs text-parchment/60">{location.description}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={`Begegnungen (${entities.length})`}>
        {entities.length === 0 ? (
          <p className="text-sm text-parchment/60">Noch niemandem begegnet.</p>
        ) : (
          <ul className="space-y-2">
            {entities.map((entity) => (
              <li key={entity.id} className="rounded-lg bg-ink-900/60 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold">{entity.name}</p>
                  {!entity.is_alive && <Badge tone="bad">tot</Badge>}
                </div>
                {entity.description && (
                  <p className="mt-1 text-xs text-parchment/60">{entity.description}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Was ihr wisst">
        {knowledge.length === 0 ? (
          <p className="text-sm text-parchment/60">Noch nichts erfahren.</p>
        ) : (
          <ul className="space-y-1.5 text-sm text-parchment/80">
            {knowledge.map((entry, index) => (
              <li key={index} className="flex gap-2">
                <span className="text-ember-400" aria-hidden>
                  •
                </span>
                <span>{entry}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={`Feststehende Fakten (${facts.length})`}>
        {facts.length === 0 ? (
          <p className="text-sm text-parchment/60">Die Welt ist noch unbeschrieben.</p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {facts.map((fact) => (
              <li key={fact.key} className="rounded-lg bg-ink-900/60 px-3 py-2">
                <p className="text-parchment/85">{fact.statement}</p>
                <p className="mt-0.5 text-[11px] text-parchment/40">
                  {fact.key} · Zug {fact.turn_number}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

export function LogPanel({ events }: { events: GameEvent[] }) {
  return (
    <Card title={`Spielverlauf (${events.length})`}>
      <ol className="space-y-1.5 text-sm">
        {events
          .filter((event) => event.summary)
          .slice()
          .reverse()
          .map((event) => (
            <li key={event.id} className="flex gap-2 rounded-lg bg-ink-900/50 px-3 py-1.5">
              <span className="shrink-0 tabular-nums text-xs text-parchment/35">#{event.seq}</span>
              <span className="text-parchment/80">{event.summary}</span>
            </li>
          ))}
      </ol>
    </Card>
  );
}
