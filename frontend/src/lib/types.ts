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
  is_alive: boolean;
  conditions: string[];
  location: string | null;
  stats: Stat[];
  abilities: string[];
  inventory: InventoryEntry[];
}

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
  submitted_player_ids: string[];
  my_suggestions: Suggestion[];
}

export interface Narration {
  id: string;
  kind: "public" | "private";
  scene_title: string;
  text: string;
  audience_player_id: string | null;
  created_at: string;
}

export interface DiceRoll {
  id: string;
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
}

export interface RealtimeMessage {
  type: string;
  game_id: string;
  audience_player_id: string | null;
  payload: Record<string, unknown>;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> };
}
