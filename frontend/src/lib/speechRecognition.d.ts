/** Minimale Ambient-Typen fuer die Web Speech API (Diktierfunktion in
 * `ActionBar`). Nicht Teil von TypeScript's DOM-lib, nur bei Chrome/Edge
 * unter dem `webkit`-Praefix verfuegbar -- daher per Feature-Detection
 * genutzt, nie vorausgesetzt. */

interface SpeechRecognitionResultLike {
  readonly [index: number]: { readonly transcript: string };
}

interface SpeechRecognitionEventLike extends Event {
  readonly resultIndex: number;
  readonly results: ArrayLike<SpeechRecognitionResultLike>;
}

interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: ((event: Event) => void) | null;
  start(): void;
  stop(): void;
}

interface Window {
  SpeechRecognition?: new () => SpeechRecognitionLike;
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
}
