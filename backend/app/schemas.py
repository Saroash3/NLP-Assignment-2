"""
Pydantic models for the REST and WebSocket JSON contracts. Centralizing
these gives main.py, the tests, and the frontend one unambiguous source of
truth for message shapes (mirrored in the README's API section).
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# --- Client -> server, over /ws/chat ---


class ClientMessageType(str, Enum):
    MESSAGE = "message"
    RESET = "reset"
    # Assignment 3 (voice), additive: start/stop listening. The microphone audio itself is sent
    # as BINARY frames (16 kHz mono 16-bit PCM) on the same socket.
    VOICE_START = "voice_start"
    VOICE_STOP = "voice_stop"
    # Tap-to-talk: everything between these two is ONE utterance (no automatic end-of-speech).
    RECORD_START = "record_start"
    RECORD_STOP = "record_stop"


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
    # Assignment 2 (citations bonus), OPTIONAL and backward-compatible: the source files the
    # answer was grounded in (deduplicated, best match first). Omitted entirely -- not sent as
    # null or [] -- when the answer wasn't grounded, so the event is then exactly Assignment 1's.
    sources: list[str] | None = None


class ErrorEvent(BaseModel):
    type: ServerMessageType = ServerMessageType.ERROR
    message: str
    code: str = "error"


# --- Assignment 3: NEW server -> client events, sent alongside the four above. ---
# A client that only knows session/token/done/error can ignore them (the A1/A2 frontend did).


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    id: str
    name: str
    ok: bool
    result: dict | str


class VoiceStateEvent(BaseModel):
    type: Literal["voice_state"] = "voice_state"
    state: Literal["idle", "listening", "transcribing", "thinking", "speaking"]


class TranscriptEvent(BaseModel):
    """Live ASR text. final=False: partial (may change); final=True: sent to the assistant."""

    type: Literal["transcript"] = "transcript"
    text: str
    final: bool


class AudioEvent(BaseModel):
    """One synthesized sentence: base64 16-bit mono PCM. Play in `seq` order."""

    type: Literal["audio"] = "audio"
    seq: int
    sample_rate: int
    data: str


class AudioEndEvent(BaseModel):
    """No more audio for this turn."""

    type: Literal["audio_end"] = "audio_end"


class LatencyEvent(BaseModel):
    """Per-turn timings in ms. Voice-only fields are omitted for typed turns."""

    type: Literal["latency"] = "latency"
    asr_ms: float | None = None
    retrieval_ms: float | None = None
    tool_ms: float | None = None
    llm_first_token_ms: float | None = None
    tts_first_audio_ms: float | None = None
    total_ms: float | None = None


# --- REST ---


class HealthResponse(BaseModel):
    status: str
    model: str
    ollama_reachable: bool
    active_sessions: int


class NewSessionResponse(BaseModel):
    session_id: str
    stage: str
