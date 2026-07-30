/** Tonausgabe am Spieltisch.
 *
 * Ziel ist ein einzelnes Gerät als Tischlautsprecher — in der Regel das
 * iPhone der Spielleitung. Alle anderen Geräte bleiben stumm, sonst hallt
 * die Erzählung mehrfach versetzt durch den Raum.
 *
 * Zwei Eigenheiten mobiler Browser bestimmen den Aufbau:
 *
 * 1. **Safari auf iOS spielt nichts ohne Berührung.** Ein `play()` ohne
 *    vorangehende Nutzeraktion wird abgewiesen. Deshalb wird genau ein
 *    `<audio>`-Element angelegt und beim ersten Antippen freigeschaltet;
 *    danach darf dasselbe Element beliebig oft von selbst starten.
 * 2. **Das Element muss erhalten bleiben.** Ein neues Element pro Aufnahme
 *    verliert die Freischaltung wieder.
 */

const SINK_KEY = "kipnp.audio.sink.v1";

export interface SinkPreferences {
  /** Gibt dieses Gerät Ton aus? */
  isSpeaker: boolean;
  /** Wurde die Wiedergabe durch eine Nutzeraktion freigeschaltet? */
  unlocked: boolean;
}

/** Eine tonlose, gültige MP3-Datei — dient nur der Freischaltung. */
const SILENT_MP3 =
  "data:audio/mpeg;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQxAADB8AhSmxhIIEVCSiJrDCBKKw0oag" +
  "AQmYWGhAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB" +
  "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB";

export function loadSinkPreferences(isHost: boolean): SinkPreferences {
  try {
    const raw = window.localStorage.getItem(SINK_KEY);
    if (raw) return JSON.parse(raw) as SinkPreferences;
  } catch {
    /* Voreinstellung verwenden */
  }
  // Ohne eigene Wahl übernimmt das Gerät der Spielleitung die Ausgabe.
  return { isSpeaker: isHost, unlocked: false };
}

export function saveSinkPreferences(preferences: SinkPreferences): void {
  window.localStorage.setItem(SINK_KEY, JSON.stringify(preferences));
}

/** Verwaltet das eine, dauerhaft bestehende Audio-Element. */
export class AudioSink {
  /** Wird gerufen, sobald tatsächlich Ton läuft — dann ist die Freischaltung
   *  erledigt und ein Hinweis darauf erübrigt sich. */
  onStarted: (() => void) | null = null;

  private element: HTMLAudioElement | null = null;
  private queue: string[] = [];
  private playing = false;
  private played = new Set<string>();

  private ensureElement(): HTMLAudioElement {
    if (this.element) return this.element;
    const element = new Audio();
    element.preload = "auto";
    // Verhindert, dass iOS die Wiedergabe in den Vollbildmodus zwingt.
    element.setAttribute("playsinline", "true");
    element.addEventListener("ended", () => {
      this.playing = false;
      void this.drain();
    });
    element.addEventListener("error", () => {
      this.playing = false;
      void this.drain();
    });
    this.element = element;
    return element;
  }

  /** Muss aus einem Klick- oder Tipp-Ereignis heraus aufgerufen werden. */
  async unlock(): Promise<boolean> {
    const element = this.ensureElement();
    try {
      element.src = SILENT_MP3;
      element.muted = true;
      await element.play();
      element.pause();
      element.currentTime = 0;
      element.muted = false;
      return true;
    } catch {
      element.muted = false;
      return false;
    }
  }

  /** Stellt eine Aufnahme in die Warteschlange. Doppelte werden verworfen. */
  enqueue(url: string, key?: string): void {
    const identity = key ?? url;
    if (this.played.has(identity)) return;
    this.played.add(identity);
    this.queue.push(url);
    void this.drain();
  }

  /** Spielt eine Aufnahme sofort, unabhängig von der Warteschlange. */
  async playNow(url: string): Promise<void> {
    const element = this.ensureElement();
    this.queue = [];
    element.pause();
    element.src = url;
    this.playing = true;
    try {
      await element.play();
      this.onStarted?.();
    } catch {
      this.playing = false;
    }
  }

  stop(): void {
    this.queue = [];
    this.playing = false;
    this.element?.pause();
  }

  private async drain(): Promise<void> {
    if (this.playing) return;
    const next = this.queue.shift();
    if (!next) return;
    const element = this.ensureElement();
    element.src = next;
    this.playing = true;
    try {
      await element.play();
      this.onStarted?.();
    } catch {
      // Meist fehlende Freischaltung: Aufnahme zurücklegen und warten,
      // bis der Nutzer die Ausgabe erlaubt.
      this.playing = false;
      this.queue.unshift(next);
    }
  }
}

/** Eine Instanz für die gesamte Anwendung. */
export const audioSink = new AudioSink();
