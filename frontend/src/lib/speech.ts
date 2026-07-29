/** Sprachausgabe im Browser (Web-Speech-API).
 *
 * Bewusst als eigenes Modul: soll die Ausgabe spaeter ueber Sonos,
 * Chromecast oder Home Assistant laufen, wird hier ein anderer Kanal
 * eingehaengt, ohne dass die Oberflaeche sich aendert.
 */

export interface SpeakOptions {
  voiceName?: string;
  rate?: number;
  pitch?: number;
  lang?: string;
}

export function speechSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function speak(text: string, options: SpeakOptions = {}): void {
  if (!speechSupported() || !text.trim()) return;
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = options.lang ?? "de-DE";
  utterance.rate = options.rate ?? 0.97;
  utterance.pitch = options.pitch ?? 0.95;

  if (options.voiceName) {
    const voice = window.speechSynthesis.getVoices().find((item) => item.name === options.voiceName);
    if (voice) utterance.voice = voice;
  }
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (speechSupported()) window.speechSynthesis.cancel();
}

export function listVoices(lang = "de"): SpeechSynthesisVoice[] {
  if (!speechSupported()) return [];
  return window.speechSynthesis.getVoices().filter((voice) => voice.lang.startsWith(lang));
}
