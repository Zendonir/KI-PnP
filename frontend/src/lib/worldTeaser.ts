/** Baut einen kurzen Weltbild-Abriss aus den bei der Rundenerstellung
 * gewaehlten Einstellungen -- ohne zusaetzlichen KI-Aufruf, rein aus den
 * Werten, die der Gastgeber in `CreateGamePage` schon ausgewaehlt hat. So
 * wissen Spielende vor der Charaktererstellung, was sie erwartet, ohne dass
 * hier neue, unbelegte Lore erfunden wird. Labels spiegeln absichtlich die
 * Texte aus `CreateGamePage.tsx`. */

import type { GameSettings } from "./types";

const GENRE_LABELS: Record<string, string> = {
  fantasy: "Fantasy",
  scifi: "Science-Fiction",
  horror: "Horror",
  mystery: "Mystery",
  cyberpunk: "Cyberpunk",
  postapocalyptic: "Postapokalypse",
  western: "Western",
};

const DIFFICULTY_LABELS: Record<string, string> = {
  story: "erzaehlend, kaum Scheitern",
  easy: "leicht",
  normal: "normal",
  hard: "schwer",
  deadly: "toedlich",
};

const PLAY_STYLE_LABELS: Record<string, string> = {
  balanced: "eine ausgewogene Mischung aus allem",
  combat: "Kampf",
  exploration: "Erkundung",
  roleplay: "Rollenspiel",
  puzzle: "Raetsel",
};

const TONE_LABELS: Record<string, string> = {
  heroic: "heldenhaft",
  grim: "duester",
  humorous: "humorvoll",
  mysterious: "geheimnisvoll",
  epic: "episch",
};

export function buildWorldTeaser(settings: GameSettings): string {
  const genre = GENRE_LABELS[settings.genre] ?? settings.genre;
  const tone = TONE_LABELS[settings.tone] ?? settings.tone;
  const difficulty = DIFFICULTY_LABELS[settings.difficulty] ?? settings.difficulty;
  const playStyle = PLAY_STYLE_LABELS[settings.play_style] ?? settings.play_style;

  const worldSentence = settings.world.trim()
    ? `Ihr befindet euch in einer ${genre}-Welt: ${settings.world.trim()}`
    : `Ihr befindet euch in einer ${genre}-Welt, die sich die KI im Spielverlauf ausdenkt.`;

  return (
    `${worldSentence} Der Ton der Erzaehlung ist ${tone}, der Schwierigkeitsgrad ${difficulty}. ` +
    `Im Vordergrund steht ${playStyle}.`
  );
}
