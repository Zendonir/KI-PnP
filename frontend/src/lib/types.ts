/** Datenvertraege der API. Spiegelt `app/schemas/api.py`. */

export type GameStatus = "lobby" | "active" | "paused" | "finished";

export interface GameSettings {
  genre: string;
  world: string;
  difficulty: string;
  duration: string;
  max_players: number;
  rule_complexity: string;
  play_style: string;
  tone: string;
  campaign_type: string;
  ruleset: string;
  language: string;
  tts_enabled: boolean;
  audio_targets: string[];
  /** host: nur das Gerät der Spielleitung gibt Ton aus. */
  audio_playback: "host" | "all" | "none";
  ai_provider?: string | null;
  ai_model?: string | null;
  debug_mode?: boolean;
}

export interface Game {
  id: string;
  code: string;
  name: string;
  status: GameStatus;
  current_turn_number: number;
  created_at: string;
  settings: GameSettings;
  /** Von der KI bei der Rundenerstellung erzeugte kurze Weltvorschau (2-4
   * Saetze). Kann fehlen, wenn der Aufruf misslang -- dann faellt die
   * Lobby auf `buildWorldTeaser(settings)` zurueck. */
  premise: string | null;
}

export interface Player {
  id: string;
  name: string;
  role: "host" | "player";
  is_active: boolean;
  is_connected: boolean;
}

export interface SessionResponse {
  game: Game;
  player: Player;
  token: string;
  join_url: string;
  qr_url: string;
}

export interface Stat {
  key: string;
  value: number;
  max_value: number | null;
}

export interface InventoryEntry {
  id: string;
  name: string;
  description: string;
  kind: string;
  quantity: number;
  equipped: boolean;
  slot: string | null;
}

export interface Character {
  id: string;
  player_id: string | null;
  name: string;
  race: string;
  class: string;
  background: string;
  avatar: string;
  level: number;
  experience: number;
  /** Erfahrung, die von der aktuellen Stufe zur naechsten noetig ist. */
  experience_to_next_level: number;
  is_alive: boolean;
  conditions: string[];
  location: string | null;
  stats: Stat[];
  abilities: string[];
  inventory: InventoryEntry[];
}

/** Feste Ressourcen-Pools -- keine waehlbaren Wuerfel-Attribute, auch wenn
 * sie technisch als Stat existieren (siehe app.domain.rules.RESOURCE_POOL_KEYS). */
export const RESOURCE_POOL_KEYS = new Set(["hp", "mana", "stamina"]);

/** Ressourcen-Pools plus die vier Grundattribute -- Namen, die beim
 * Verteilen frei benannter Skills nicht verwendet werden duerfen (siehe
 * app.services.character_service._RESERVED_STAT_KEYS). */
export const RESERVED_STAT_KEYS = new Set([
  ...RESOURCE_POOL_KEYS,
  "strength",
  "dexterity",
  "intelligence",
  "charisma",
]);

export const CORE_STAT_LABELS: Record<string, string> = {
  strength: "Stärke",
  dexterity: "Geschicklichkeit",
  intelligence: "Intelligenz",
  charisma: "Charisma",
};

export interface Suggestion {
  kind: string;
  label: string;
  hint: string;
}

export interface Turn {
  id: string;
  number: number;
  status: "collecting" | "resolving" | "completed";
  scene_title: string;
  location_id: string | null;
  location_name: string | null;
  submitted_player_ids: string[];
  my_suggestions: Suggestion[];
}

/** Aufdeckungs-Fortschritt des letzten abgeschlossenen Zugs am eigenen Ort.
 * Solange revealed false ist, haelt das Frontend Wuerfelergebnisse,
 * Erzaehlung und Ton dieses Zugs im Verlauf zurueck -- das Wuerfel-Popup
 * selbst zeigt die eigenen Ergebnisse trotzdem sofort. */
export interface PendingReveal {
  turn_id: string;
  revealed: boolean;
  acknowledged_player_ids: string[];
  expected_player_ids: string[];
}

/** Ein als Gruppenereignis markierter Vorschlag, auf den die eigene Person
 * noch nicht geantwortet hat. */
export interface GroupProposal {
  id: string;
  initiator_name: string;
  kind: string;
  text: string;
}

/** Ein gleichzeitig laufender Zug an einem Ort -- nur fuer die Spielleitung. */
export interface ActiveLocationTurn {
  turn_id: string;
  turn_number: number;
  status: "collecting" | "resolving" | "completed";
  location_id: string | null;
  location_name: string | null;
  character_names: string[];
  submitted_count: number;
  participant_count: number;
}

export interface Narration {
  id: string;
  turn_id: string | null;
  kind: "public" | "private";
  scene_title: string;
  text: string;
  audience_player_id: string | null;
  created_at: string;
}

export interface DiceRoll {
  id: string;
  turn_id: string | null;
  character_id: string | null;
  notation: string;
  rolls: number[];
  modifier: number;
  total: number;
  difficulty: number | null;
  success: boolean | null;
  degree: string;
  reason: string;
  created_at: string;
}

export interface Quest {
  id: string;
  title: string;
  description: string;
  status: string;
  is_main: boolean;
  /** Juengster Fortschrittsvermerk -- zeigt, wo die Gruppe in dieser Quest steht. */
  note: string;
  /** Zug, in dem dieser Stand zuletzt fortgeschrieben wurde. */
  turn_number: number;
}

export interface WorldLocation {
  id: string;
  name: string;
  description: string;
  is_discovered: boolean;
}

export interface WorldEntity {
  id: string;
  name: string;
  kind: string;
  description: string;
  is_alive: boolean;
}

export interface Fact {
  key: string;
  statement: string;
  visibility: string;
  turn_number: number;
}

export interface GameEvent {
  id: string;
  seq: number;
  type: string;
  summary: string;
  turn_number: number;
  visibility: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AudioJob {
  id: string;
  status: string;
  provider: string;
  target: string;
  url: string | null;
  text: string;
  voice: string;
  mime_type: string | null;
  narration_id: string | null;
  error: string | null;
}

export interface Summary {
  id: string;
  text: string;
  highlights: string[];
  turn_number: number;
  created_at: string;
}

export interface GameState {
  game: Game;
  players: Player[];
  characters: Character[];
  me: Player;
  my_character: Character | null;
  turn: Turn | null;
  pending_reveal: PendingReveal | null;
  pending_group_proposal: GroupProposal | null;
  narrations: Narration[];
  dice_rolls: DiceRoll[];
  quests: Quest[];
  locations: WorldLocation[];
  entities: WorldEntity[];
  facts: Fact[];
  knowledge: string[];
  events: GameEvent[];
  audio: AudioJob | null;
  is_host: boolean;
  active_location_turns: ActiveLocationTurn[] | null;
}

export interface RealtimeMessage {
  type: string;
  game_id: string;
  audience_player_id: string | null;
  payload: Record<string, unknown>;
}

/** Kurzfristiges Eingriffsangebot (Quick-Time-Event), payload von `intervention.offer`. */
export interface InterventionOffer {
  intervention_id: string;
  actor: string;
  action_text: string;
  timeout_seconds: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> };
}

/** Installationsweite Laufzeit-Einstellungen (Settings-Menue). Unabhaengig
 * von `GameSettings`, die pro Runde gelten. */
export interface RuntimeSettings {
  tts_voice: string;
  tts_speed: number;
  tts_provider: string;
  voice_source: "openai" | "custom";
  known_voices: string[];
  updated_at: string | null;
}
