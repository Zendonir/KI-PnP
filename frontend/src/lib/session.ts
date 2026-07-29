/** Speichert die Zugangsdaten einer Runde lokal im Browser.
 *
 * So bleibt ein Spieler nach dem Schliessen des Tabs oder einem
 * Verbindungsabbruch in seiner Runde angemeldet.
 */

const KEY = "kipnp.session.v1";

export interface StoredSession {
  gameId: string;
  gameCode: string;
  gameName: string;
  token: string;
  playerId: string;
  playerName: string;
  role: "host" | "player";
}

export function loadSession(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSession;
    return parsed.token && parsed.gameId ? parsed : null;
  } catch {
    return null;
  }
}

export function saveSession(session: StoredSession): void {
  window.localStorage.setItem(KEY, JSON.stringify(session));
}

export function clearSession(): void {
  window.localStorage.removeItem(KEY);
}
