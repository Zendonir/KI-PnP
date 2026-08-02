/** Installationsweites, passwortgeschuetztes Einstellungen-Menue.
 *
 * Unabhaengig von einzelnen Runden: hier lassen sich die aktive
 * TTS-Stimme und -Geschwindigkeit fuer die ganze Installation aendern,
 * ohne Neustart -- eine laufende Runde uebernimmt die Aenderung bei der
 * naechsten Erzaehlung.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Button, Card, ErrorNote, Field, Select, Spinner, TextInput } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { clearAdminSession, loadAdminSession, saveAdminSession } from "../lib/adminSession";
import type { RuntimeSettings } from "../lib/types";

export function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);

  const [password, setPassword] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  const [voice, setVoice] = useState("");
  const [speed, setSpeed] = useState(1.0);
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .adminStatus()
      .then((status) => active && setEnabled(status.enabled))
      .catch(() => active && setEnabled(false))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const loadSettings = async (currentToken: string) => {
    try {
      const result = await api.getAdminSettings(currentToken);
      setSettings(result);
      setVoice(result.tts_voice);
      setSpeed(result.tts_speed);
      setToken(currentToken);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearAdminSession();
        setToken(null);
      } else {
        setLoginError(err instanceof ApiError ? err.message : "Laden fehlgeschlagen.");
      }
    }
  };

  useEffect(() => {
    if (!enabled) return;
    const stored = loadAdminSession();
    if (stored) void loadSettings(stored.token);
  }, [enabled]);

  const login = async () => {
    if (!password.trim()) return;
    setLoginBusy(true);
    setLoginError(null);
    try {
      const result = await api.adminLogin(password);
      saveAdminSession({ token: result.token, expiresAt: result.expires_at });
      setPassword("");
      await loadSettings(result.token);
    } catch (err) {
      setLoginError(err instanceof ApiError ? err.message : "Anmeldung fehlgeschlagen.");
    } finally {
      setLoginBusy(false);
    }
  };

  const save = async () => {
    if (!token) return;
    setSaveBusy(true);
    setSaveError(null);
    setSaved(false);
    try {
      const result = await api.updateAdminSettings(token, {
        tts_voice: voice.trim() || null,
        tts_speed: speed,
      });
      setSettings(result);
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearAdminSession();
        setToken(null);
      } else {
        setSaveError(err instanceof ApiError ? err.message : "Speichern fehlgeschlagen.");
      }
    } finally {
      setSaveBusy(false);
    }
  };

  return (
    <main className="safe-top safe-bottom mx-auto w-full max-w-md space-y-4 px-5 py-10">
      <Link to="/" className="text-sm text-parchment/50">
        ← Zurueck
      </Link>
      <h1 className="font-serif text-2xl text-ember-400">Einstellungen</h1>

      {loading && <Spinner label="Wird geladen ..." />}

      {!loading && !enabled && (
        <Card>
          <p className="text-sm text-parchment/70">
            Der Einstellungsbereich ist auf diesem Server nicht aktiviert.
          </p>
        </Card>
      )}

      {!loading && enabled && !token && (
        <Card title="Anmeldung">
          <div className="space-y-3">
            {loginError && <ErrorNote>{loginError}</ErrorNote>}
            <Field label="Kennwort">
              <TextInput
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                onKeyDown={(event) => {
                  if (event.key === "Enter") void login();
                }}
              />
            </Field>
            <Button className="w-full" disabled={loginBusy} onClick={() => void login()}>
              {loginBusy ? "Meldet an ..." : "Anmelden"}
            </Button>
          </div>
        </Card>
      )}

      {!loading && enabled && token && settings && (
        <Card title="Sprachausgabe">
          <div className="space-y-3">
            <p className="text-xs text-parchment/50">
              Aktiver Anbieter: {settings.tts_provider}
              {settings.tts_provider !== "openai" &&
                " -- Stimme/Geschwindigkeit wirken erst nach Umstellung auf 'openai'."}
            </p>

            {saveError && <ErrorNote>{saveError}</ErrorNote>}

            {settings.voice_source === "openai" ? (
              <Field label="Stimme">
                <Select value={voice} onChange={(event) => setVoice(event.target.value)}>
                  {settings.known_voices.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : (
              <Field label="Stimme" hint="Stimmenname des lokalen Dienstes.">
                <TextInput value={voice} onChange={(event) => setVoice(event.target.value)} />
              </Field>
            )}

            <Field label="Geschwindigkeit" hint="0,25 (langsam) bis 4,0 (schnell), normal = 1,0.">
              <TextInput
                type="number"
                min={0.25}
                max={4}
                step={0.05}
                value={speed}
                onChange={(event) => setSpeed(Number(event.target.value))}
              />
            </Field>

            <Button className="w-full" disabled={saveBusy} onClick={() => void save()}>
              {saveBusy ? "Speichert ..." : "Speichern"}
            </Button>
            {saved && (
              <p className="text-xs text-moss-500">
                Gespeichert — gilt ab der naechsten Erzaehlung.
              </p>
            )}
          </div>
        </Card>
      )}
    </main>
  );
}
