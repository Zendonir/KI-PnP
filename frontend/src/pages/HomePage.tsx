/** Startseite: neue Runde eroeffnen, beitreten oder fortsetzen. */

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button, Card, Field, TextInput } from "../components/ui";
import { clearSession, loadSession, type StoredSession } from "../lib/session";

export function HomePage() {
  const navigate = useNavigate();
  const [session, setSession] = useState<StoredSession | null>(null);
  const [code, setCode] = useState("");

  useEffect(() => setSession(loadSession()), []);

  return (
    <main className="safe-top safe-bottom mx-auto flex min-h-full w-full max-w-md flex-col gap-6 px-5 py-10">
      <header className="text-center">
        <p className="text-5xl" aria-hidden>
          🎲
        </p>
        <h1 className="mt-3 font-serif text-3xl text-ember-400">KI-PnP</h1>
        <p className="mt-2 text-sm text-parchment/65">
          Pen &amp; Paper mit KI-Spielleiter. Alle spielen im Browser, die Welt bleibt dauerhaft
          gespeichert.
        </p>
      </header>

      {session && (
        <Card title="Laufende Runde">
          <p className="text-sm text-parchment/80">
            {session.gameName} <span className="text-parchment/50">({session.gameCode})</span>
          </p>
          <p className="mt-0.5 text-xs text-parchment/50">als {session.playerName}</p>
          <div className="mt-3 flex gap-2">
            <Button className="flex-1" onClick={() => navigate(`/game/${session.gameId}`)}>
              Fortsetzen
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                clearSession();
                setSession(null);
              }}
            >
              Verlassen
            </Button>
          </div>
        </Card>
      )}

      <Card title="Runde beitreten">
        <div className="space-y-3">
          <Field label="Beitrittscode" hint="Sechs Zeichen vom Spielleiter oder per QR-Code.">
            <TextInput
              value={code}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
              placeholder="z. B. K7QW2M"
              maxLength={12}
              autoCapitalize="characters"
              autoCorrect="off"
              inputMode="text"
            />
          </Field>
          <Button
            className="w-full"
            disabled={code.trim().length < 4}
            onClick={() => navigate(`/join/${code.trim()}`)}
          >
            Weiter
          </Button>
        </div>
      </Card>

      <Card title="Neue Runde">
        <p className="mb-3 text-sm text-parchment/65">
          Genre, Welt, Schwierigkeit und Spielstil festlegen -- die KI erzeugt daraus Welt, NSC und
          die erste Szene.
        </p>
        <Link to="/create">
          <Button className="w-full">Runde erstellen</Button>
        </Link>
      </Card>

      <footer className="mt-auto text-center text-xs text-parchment/35">
        Die Datenbank ist die einzige Wahrheit. Jede Handlung wird dauerhaft protokolliert.
      </footer>
    </main>
  );
}
