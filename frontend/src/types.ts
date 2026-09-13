export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  isError?: boolean;
}

export type ConnectionStatus = "connecting" | "open" | "closed" | "error";

// Mirrors backend/app/schemas.py -- keep these two in sync.
export type ServerEvent =
  | { type: "session"; session_id: string; stage: string }
  | { type: "token"; content: string }
  | { type: "done"; stage: string }
  | { type: "error"; message: string; code: string };

export type ClientEvent = { type: "message"; content: string } | { type: "reset" };
