/** Typisierter Zugriff auf die Backend-API. */

import type {
  ApiErrorBody,
  Character,
  Game,
  GameSettings,
  GameState,
  RuntimeSettings,
  SessionResponse,
  Summary,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string | null } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers.Authorization = `Bearer ${options.token}`;

  const response = await fetch(`${BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    let code = "http_error";
    let message = `Fehler ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorBody & { detail?: unknown };
      if (body.error) {
        code = body.error.code;
        message = body.error.message;
      } else if (body.detail) {
        message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* Antwort ohne JSON-Koerper */
    }
    throw new ApiError(response.status, code, message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface CreateGamePayload {
  name: string;
  host_name: string;
  settings: Partial<GameSettings>;
}

export const api = {
  createGame: (payload: CreateGamePayload) =>
    request<SessionResponse>("/games", { method: "POST", body: payload }),

  peekGame: (code: string) => request<Game>(`/games/code/${code}`),

  joinGame: (code: string, playerName: string) =>
    request<SessionResponse>(`/games/code/${code}/join`, {
      method: "POST",
      body: { player_name: playerName },
    }),

  qrUrl: (code: string) => `${BASE}/games/code/${code}/qr.svg`,

  getState: (gameId: string, token: string) =>
    request<GameState>(`/games/${gameId}/state`, { token }),

  createCharacter: (
    gameId: string,
    token: string,
    payload: {
      name?: string;
      race?: string;
      class?: string;
      background?: string;
      avatar?: string;
      randomize?: boolean;
    },
  ) => request<Character>(`/games/${gameId}/characters`, { method: "POST", body: payload, token }),

  startGame: (gameId: string, token: string) =>
    request<GameState>(`/games/${gameId}/start`, { method: "POST", token }),

  submitAction: (
    gameId: string,
    token: string,
    payload: { kind: string; text: string; target_ref?: string; payload?: Record<string, unknown> },
  ) => request<unknown>(`/games/${gameId}/actions`, { method: "POST", body: payload, token }),

  resolveTurn: (gameId: string, token: string, turnId?: string) =>
    request<unknown>(
      `/games/${gameId}/resolve${turnId ? `?turn_id=${turnId}` : ""}`,
      { method: "POST", token },
    ),

  continueTurn: (gameId: string, token: string, turnId?: string) =>
    request<unknown>(
      `/games/${gameId}/continue${turnId ? `?turn_id=${turnId}` : ""}`,
      { method: "POST", token },
    ),

  respondIntervention: (gameId: string, token: string, interventionId: string, accepted: boolean) =>
    request<unknown>(`/games/${gameId}/interventions/${interventionId}/respond`, {
      method: "POST",
      body: { accepted },
      token,
    }),

  renarrate: (gameId: string, token: string) =>
    request<unknown>(`/games/${gameId}/renarrate`, { method: "POST", token }),

  skipScene: (gameId: string, token: string) =>
    request<GameState>(`/games/${gameId}/skip`, { method: "POST", token }),

  pause: (gameId: string, token: string) =>
    request<Game>(`/games/${gameId}/pause`, { method: "POST", token }),

  resume: (gameId: string, token: string) =>
    request<Game>(`/games/${gameId}/resume`, { method: "POST", token }),

  finish: (gameId: string, token: string) =>
    request<Game>(`/games/${gameId}/finish`, { method: "POST", token }),

  kick: (gameId: string, token: string, playerId: string) =>
    request<unknown>(`/games/${gameId}/players/${playerId}`, { method: "DELETE", token }),

  createSummary: (gameId: string, token: string) =>
    request<Summary>(`/games/${gameId}/summary`, { method: "POST", token }),

  listSummaries: (gameId: string, token: string) =>
    request<Summary[]>(`/games/${gameId}/summaries`, { token }),

  replayAudio: (gameId: string, token: string) =>
    request<unknown>(`/games/${gameId}/audio/replay`, { method: "POST", token }),

  /** Lädt eine serverseitig erzeugte Aufnahme.
   *
   * Der Endpunkt verlangt das Spieler-Token im Header, das ein
   * `<audio src=...>` nicht mitschicken kann. Deshalb wird die Datei geholt
   * und als Blob-Adresse an das Audio-Element gegeben.
   */
  fetchAudioUrl: async (gameId: string, token: string, audioId: string): Promise<string> => {
    const response = await fetch(`${BASE}/games/${gameId}/audio/${audioId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      throw new ApiError(response.status, "audio_unavailable", "Aufnahme nicht verfügbar.");
    }
    return URL.createObjectURL(await response.blob());
  },

  adminStatus: () => request<{ enabled: boolean }>("/settings/status"),

  adminLogin: (password: string) =>
    request<{ token: string; expires_at: string }>("/settings/login", {
      method: "POST",
      body: { password },
    }),

  getAdminSettings: (token: string) => request<RuntimeSettings>("/settings", { token }),

  updateAdminSettings: (
    token: string,
    payload: { tts_voice?: string | null; tts_speed?: number | null },
  ) => request<RuntimeSettings>("/settings", { method: "PUT", body: payload, token }),
};

/** WebSocket-Adresse fuer die Echtzeit-Synchronisation. */
export function websocketUrl(gameId: string, token: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const base = BASE.startsWith("http")
    ? BASE.replace(/^https?:/, protocol)
    : `${protocol}//${window.location.host}${BASE}`;
  return `${base}/ws/games/${gameId}?token=${encodeURIComponent(token)}`;
}
