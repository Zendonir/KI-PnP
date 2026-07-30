/** Speichert das Zugangstoken des installationsweiten Settings-Menues.
 *
 * Bewusst ein eigener Speicherort (anderer Schluessel als `session.ts`),
 * damit sich eine Spieler- und eine Settings-Sitzung im selben Browser nie
 * in die Quere kommen.
 */

const KEY = "kipnp.settings.token.v1";

export interface StoredAdminSession {
  token: string;
  expiresAt: string;
}

export function loadAdminSession(): StoredAdminSession | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredAdminSession;
    return parsed.token ? parsed : null;
  } catch {
    return null;
  }
}

export function saveAdminSession(session: StoredAdminSession): void {
  window.localStorage.setItem(KEY, JSON.stringify(session));
}

export function clearAdminSession(): void {
  window.localStorage.removeItem(KEY);
}
