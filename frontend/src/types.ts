export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  isError?: boolean;
  /** Source documents the answer was grounded in (citations bonus); absent if not grounded. */
  sources?: string[];
  /** Assignment 3: this entry is an inline tool-call card instead of a text bubble. */
  tool?: ToolCallInfo;
  /** Assignment 3: the user said this (voice) instead of typing it. */
  spoken?: boolean;
}

export type ConnectionStatus = "connecting" | "open" | "closed" | "error";

// --- Assignment 3 ---

export interface ToolCallInfo {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  status: "running" | "ok" | "error";
  result?: Record<string, unknown> | string;
}

export type VoiceState = "idle" | "listening" | "transcribing" | "thinking" | "speaking";

/** Per-turn timings in ms; voice-only fields are absent for typed turns. */
export interface LatencyStats {
  asr_ms?: number;
  retrieval_ms?: number;
  tool_ms?: number;
  llm_first_token_ms?: number;
  tts_first_audio_ms?: number;
  total_ms?: number;
}

// Mirrors backend/app/schemas.py -- keep these two in sync.
export type ServerEvent =
  | { type: "session"; session_id: string; stage: string }
  | { type: "token"; content: string }
  | { type: "done"; stage: string; sources?: string[] } // `sources`: optional, Assignment 2
  | { type: "error"; message: string; code: string }
  // Assignment 3 (only sent because we connect with ?extended=1):
  | { type: "tool_call"; id: string; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; ok: boolean; result: Record<string, unknown> | string }
  | { type: "voice_state"; state: VoiceState }
  | { type: "transcript"; text: string; final: boolean }
  | { type: "audio"; seq: number; sample_rate: number; data: string } // base64 16-bit mono PCM
  | { type: "audio_end" }
  | ({ type: "latency" } & LatencyStats);

export type ClientEvent =
  | { type: "message"; content: string }
  | { type: "reset" }
  | { type: "voice_start" } // Assignment 3; mic audio itself goes as binary frames
  | { type: "voice_stop" };
