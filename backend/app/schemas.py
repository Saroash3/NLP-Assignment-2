"""
Pydantic models for the REST and WebSocket JSON contracts. Centralizing
these gives main.py, the tests, and the frontend one unambiguous source of
truth for message shapes (mirrored in the README's API section).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

# --- Client -> server, over /ws/chat ---


class ClientMessageType(str, Enum):
    MESSAGE = "message"
    RESET = "reset"


class ClientMessage(BaseModel):
    type: ClientMessageType
    content: str | None = Field(default=None, max_length=2000)


# --- Server -> client, over /ws/chat ---


class ServerMessageType(str, Enum):
    SESSION = "session"  # sent once, right after connect or reset
    TOKEN = "token"  # one streamed text chunk
    DONE = "done"  # generation finished
    ERROR = "error"  # recoverable error; connection stays open


class SessionEvent(BaseModel):
    type: ServerMessageType = ServerMessageType.SESSION
    session_id: str
    stage: str


class TokenEvent(BaseModel):
    type: ServerMessageType = ServerMessageType.TOKEN
    content: str


class DoneEvent(BaseModel):
    type: ServerMessageType = ServerMessageType.DONE
    stage: str


class ErrorEvent(BaseModel):
    type: ServerMessageType = ServerMessageType.ERROR
    message: str
    code: str = "error"


# --- REST ---


class HealthResponse(BaseModel):
    status: str
    model: str
    ollama_reachable: bool
    active_sessions: int


class NewSessionResponse(BaseModel):
    session_id: str
    stage: str
