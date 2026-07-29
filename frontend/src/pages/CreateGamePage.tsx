/** Assistent zum Erstellen einer Runde. */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button, Card, ErrorNote, Field, Select, TextInput } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { saveSession } from "../lib/session";

const GENRES = [
  { value: "fantasy", label: "Fantasy" },
  { value: "scifi", label: "Science-Fiction" },
  { value: "horror", label: "Horror" },
  { value: "mystery", label: "Mystery" },
  { value: "cyberpunk", label: "Cyberpunk" },
  { value: "postapocalyptic", label: "Postapokalypse" },
  { value: "western", label: "Western" },
];

const DIFFICULTIES = [
  { value: "story", label: "Erzaehlend (kaum Scheitern)" },
  { value: "easy", label: "Leicht" },
  { value: "normal", label: "Normal" },
  { value: "hard", label: "Schwer" },
  { value: "deadly", label: "Toedlich" },
];

const DURATIONS = [
  { value: "oneshot", label: "One-Shot (ein Abend)" },
  { value: "short", label: "Kurz (2-3 Abende)" },
  { value: "medium", label: "Mittel" },
  { value: "long", label: "Lang" },
  { value: "campaign", label: "Kampagne ueber viele Abende" },
];

const COMPLEXITIES = [
  { value: "narrative", label: "Erzaehlerisch (wenig Regeln)" },
  { value: "light", label: "Leicht" },
  { value: "crunchy", label: "Regellastig" },
];

const STYLES = [
  { value: "balanced", label: "Ausgewogen" },
  { value: "combat", label: "Kampf" },
  { value: "exploration", label: "Erkundung" },
  { value: "roleplay", label: "Rollenspiel" },
  { value: "puzzle", label: "Raetsel" },
];

export function CreateGamePage() {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "Neue Runde",
    host_name: "",
    genre: "fantasy",
    world: "",
    difficulty: "normal",
    duration: "medium",
    max_players: 6,
    rule_complexity: "light",
    play_style: "balanced",
    tone: "heroic",
    campaign_type: "free",
    ruleset: "classic",
    tts_enabled: true,
  });

  const update = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((previous) => ({ ...previous, [key]: value }));

  const submit = async () => {
    if (!form.host_name.trim()) {
      setError("Bitte gib deinen Namen an.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const session = await api.createGame({
        name: form.name.trim() || "Neue Runde",
        host_name: form.host_name.trim(),
        settings: {
          genre: form.genre,
          world: form.world.trim(),
          difficulty: form.difficulty,
          duration: form.duration,
          max_players: Number(form.max_players),
          rule_complexity: form.rule_complexity,
          play_style: form.play_style,
          tone: form.tone,
          campaign_type: form.campaign_type,
          ruleset: form.ruleset,
          tts_enabled: form.tts_enabled,
          audio_targets: ["browser"],
        },
      });
      saveSession({
        gameId: session.game.id,
        gameCode: session.game.code,
        gameName: session.game.name,
        token: session.token,
        playerId: session.player.id,
        playerName: session.player.name,
        role: "host",
      });
      navigate(`/game/${session.game.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Die Runde konnte nicht erstellt werden.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="safe-top safe-bottom mx-auto w-full max-w-md space-y-4 px-5 py-8">
      <Link to="/" className="text-sm text-parchment/50">
        ← Zurueck
      </Link>
      <h1 className="font-serif text-2xl text-ember-400">Neue Runde</h1>

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card title="Grundlagen">
        <div className="space-y-3">
          <Field label="Dein Name">
            <TextInput
              value={form.host_name}
              onChange={(event) => update("host_name", event.target.value)}
              placeholder="Spielleitung"
              autoComplete="nickname"
            />
          </Field>
          <Field label="Name der Runde">
            <TextInput
              value={form.name}
              onChange={(event) => update("name", event.target.value)}
            />
          </Field>
          <Field label="Spieleranzahl (Maximum)">
            <TextInput
              type="number"
              min={1}
              max={32}
              value={form.max_players}
              onChange={(event) => update("max_players", Number(event.target.value))}
            />
          </Field>
        </div>
      </Card>

      <Card title="Welt">
        <div className="space-y-3">
          <Field label="Genre">
            <Select value={form.genre} onChange={(event) => update("genre", event.target.value)}>
              {GENRES.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Spielwelt" hint="Optional. Leer lassen, damit die KI sie erfindet.">
            <TextInput
              value={form.world}
              onChange={(event) => update("world", event.target.value)}
              placeholder="z. B. Die Grenzlande von Aschenfurt"
            />
          </Field>
          <Field label="Stimmung">
            <Select value={form.tone} onChange={(event) => update("tone", event.target.value)}>
              <option value="heroic">Heldenhaft</option>
              <option value="grim">Duester</option>
              <option value="humorous">Humorvoll</option>
              <option value="mysterious">Geheimnisvoll</option>
              <option value="epic">Episch</option>
            </Select>
          </Field>
        </div>
      </Card>

      <Card title="Spielweise">
        <div className="space-y-3">
          <Field label="Schwierigkeitsgrad">
            <Select
              value={form.difficulty}
              onChange={(event) => update("difficulty", event.target.value)}
            >
              {DIFFICULTIES.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Gewuenschte Dauer">
            <Select
              value={form.duration}
              onChange={(event) => update("duration", event.target.value)}
            >
              {DURATIONS.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Regelkomplexitaet">
            <Select
              value={form.rule_complexity}
              onChange={(event) => update("rule_complexity", event.target.value)}
            >
              {COMPLEXITIES.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Spielstil">
            <Select
              value={form.play_style}
              onChange={(event) => update("play_style", event.target.value)}
            >
              {STYLES.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Kampagnenform">
            <Select
              value={form.campaign_type}
              onChange={(event) => update("campaign_type", event.target.value)}
            >
              <option value="free">Frei (die KI fuehrt)</option>
              <option value="structured">Regelbasiert (feste Struktur)</option>
            </Select>
          </Field>
          <Field label="Regelwerk">
            <Select
              value={form.ruleset}
              onChange={(event) => update("ruleset", event.target.value)}
            >
              <option value="classic">Klassisch (d20, systemneutral)</option>
              <option value="grit">Hart (Horror, wenig Puffer)</option>
            </Select>
          </Field>
          <label className="flex items-center gap-3 rounded-xl bg-ink-900/60 px-3 py-3">
            <input
              type="checkbox"
              checked={form.tts_enabled}
              onChange={(event) => update("tts_enabled", event.target.checked)}
              className="h-5 w-5 accent-[var(--color-ember-500)]"
            />
            <span className="text-sm">Sprachausgabe vorbereiten</span>
          </label>
        </div>
      </Card>

      <Button className="w-full" disabled={busy} onClick={() => void submit()}>
        {busy ? "Runde wird erstellt ..." : "Runde erstellen"}
      </Button>
    </main>
  );
}
