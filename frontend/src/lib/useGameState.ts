/** Haelt den Spielzustand aktuell.
 *
 * Der Zustand kommt immer vollstaendig vom Server (die Datenbank ist die
 * einzige Wahrheit). Der WebSocket dient nur als Ausloeser: sobald ein
 * Ereignis eintrifft, wird der Zustand neu geladen. Faellt die Verbindung
 * aus, greift ein Abfrageintervall als Rueckfallebene.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api, websocketUrl } from "./api";
import type { GameState, RealtimeMessage } from "./types";

const POLL_INTERVAL_MS = 12_000;
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 15_000;

export interface UseGameStateResult {
  state: GameState | null;
  error: string | null;
  connected: boolean;
  loading: boolean;
  lastMessage: RealtimeMessage | null;
  refresh: () => Promise<void>;
}

export function useGameState(gameId: string | null, token: string | null): UseGameStateResult {
  const [state, setState] = useState<GameState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [lastMessage, setLastMessage] = useState<RealtimeMessage | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const attemptRef = useRef(0);
  const activeRef = useRef(true);

  const refresh = useCallback(async () => {
    if (!gameId || !token) return;
    try {
      const next = await api.getState(gameId, token);
      if (!activeRef.current) return;
      setState(next);
      setError(null);
    } catch (err) {
      if (!activeRef.current) return;
      setError(err instanceof ApiError ? err.message : "Verbindung zum Server fehlgeschlagen.");
    } finally {
      if (activeRef.current) setLoading(false);
    }
  }, [gameId, token]);

  // Erstes Laden und periodische Rueckfallabfrage.
  useEffect(() => {
    activeRef.current = true;
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => {
      activeRef.current = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  // WebSocket mit automatischem Wiederverbinden.
  useEffect(() => {
    if (!gameId || !token) return;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const socket = new WebSocket(websocketUrl(gameId, token));
      socketRef.current = socket;

      socket.onopen = () => {
        attemptRef.current = 0;
        setConnected(true);
      };

      socket.onmessage = (raw) => {
        try {
          const message = JSON.parse(raw.data as string) as RealtimeMessage;
          if (message.type === "ping") return;
          setLastMessage(message);
          void refresh();
        } catch {
          /* Nachricht ohne JSON ignorieren */
        }
      };

      socket.onclose = () => {
        setConnected(false);
        if (disposed) return;
        attemptRef.current += 1;
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** (attemptRef.current - 1), RECONNECT_MAX_MS);
        reconnectRef.current = window.setTimeout(connect, delay);
      };

      socket.onerror = () => socket.close();
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [gameId, token, refresh]);

  return { state, error, connected, loading, lastMessage, refresh };
}
