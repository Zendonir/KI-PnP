/** Beitrittsseite -- Ziel des QR-Codes. */

import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button, Card, ErrorNote, Field, Spinner, TextInput } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { saveSession } from "../lib/session";
import type { Game } from "../lib/types";

export function JoinPage() {
  const { code = "" } = useParams();
  const navigate = useNavigate();
  const [game, setGame] = useState<Game | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api
      .peekGame(code)
      .then((result) => active && setGame(result))
      .catch((err: unknown) =>
        active && setError(err instanceof ApiError ? err.message : "Runde nicht gefunden."),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [code]);

  const join = async () => {
    if (!name.trim()) {
      setError("Bitte gib deinen Namen an.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const session = await api.joinGame(code, name.trim());
      saveSession({
        gameId: session.game.id,
        gameCode: session.game.code,
        gameName: session.game.name,
        token: session.token,
        playerId: session.player.id,
        playerName: session.player.name,
        role: session.player.role,
      });
      navigate(`/game/${session.game.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Beitritt fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="safe-top safe-bottom mx-auto w-full max-w-md space-y-4 px-5 py-10">
      <Link to="/" className="text-sm text-parchment/50">
        ← Zurueck
      </Link>

      {loading ? (
        <Spinner label="Runde wird gesucht ..." />
      ) : (
        <>
          <header>
            <h1 className="font-serif text-2xl text-ember-400">
              {game ? game.name : "Runde beitreten"}
            </h1>
            {game && (
              <p className="mt-1 text-sm text-parchment/60">
                Code {game.code} · {game.settings.genre} · {game.settings.difficulty} ·{" "}
                {game.status === "lobby" ? "wartet auf Spieler" : "laeuft bereits"}
              </p>
            )}
          </header>

          {error && <ErrorNote>{error}</ErrorNote>}

          {game && (
            <Card title="Dein Name">
              <div className="space-y-3">
                <Field label="Name" hint="Mit demselben Namen kommst du spaeter zurueck.">
                  <TextInput
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="z. B. Tom"
                    autoComplete="nickname"
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void join();
                    }}
                  />
                </Field>
                <Button className="w-full" disabled={busy} onClick={() => void join()}>
                  {busy ? "Trete bei ..." : "Beitreten"}
                </Button>
              </div>
            </Card>
          )}
        </>
      )}
    </main>
  );
}
