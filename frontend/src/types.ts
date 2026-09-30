export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  isError?: boolean;
  /** Source documents the answer was grounded in (citations bonus); absent if not grounded. */
  sources?: string[];
}

export type ConnectionStatus = "connecting" | "open" | "closed" | "error";

// Mirrors backend/app/schemas.py -- keep these two in sync.
export type ServerEvent =
  | { type: "session"; session_id: string; stage: string }
  | { type: "token"; content: string }
  | { type: "done"; stage: string; sources?: string[] } // `sources`: optional, Assignment 2
  | { type: "error"; message: string; code: string };

export type ClientEvent = { type: "message"; content: string } | { type: "reset" };
