"""
FastAPI application: REST health/session endpoints + the /ws/chat
websocket. This module is intentionally thin -- it wires the
ConversationManager and LLMEngine together and translates between JSON
wire messages and their calls. No prompt logic or history logic lives
here (see conversation_manager.py / prompts.py).
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.conversation_manager import ConversationManager, Message, _qwen_tokenizer
from app.llm_engine import LLMEngine
from app.tools import user_profile
from app.turn import TurnTimings, run_turn
from app.voice import asr, tts, vad
from app.voice.speech_output import SpeechOutput
from app.voice.voice_session import VoiceSession, VoiceUnavailable
from rag import retriever
from app.schemas import (
    ClientMessage,
    ClientMessageType,
    DoneEvent,
    ErrorEvent,
    HealthResponse,
    NewSessionResponse,
    SessionEvent,
    TokenEvent,
    VoiceStateEvent,
)

logger = logging.getLogger("zor_assistant")
# Show our INFO logs (e.g. which sources were retrieved per turn) next to uvicorn's.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.conversation_manager = ConversationManager()
    app.state.llm_engine = LLMEngine()
    # Load the embedding model, the Chroma collection and the Qwen tokenizer ONCE, here,
    # (in a thread so startup doesn't block the loop) -- never per request. If this fails
    # the server still starts; each request then falls back to answering without documents.
    try:
        await asyncio.to_thread(retriever.load)
        await asyncio.to_thread(_qwen_tokenizer)
    except Exception:
        logger.exception("RAG components failed to load; continuing without retrieval")
    # Assignment 3: speech models, also loaded ONCE and in threads. If one fails, voice mode
    # reports "unavailable" when started, and text chat keeps working.
    if get_settings().voice_enabled:
        for name, loader in (("VAD", vad.load), ("ASR", asr.load), ("TTS", tts.load)):
            try:
                await asyncio.to_thread(loader)
            except Exception:
                logger.exception("%s failed to load; voice mode will be unavailable", name)
        # Load the LLM into GPU memory now, so the first member doesn't wait seconds for it.
        asyncio.create_task(app.state.llm_engine.warm_up())
    logger.info("Zor Fitness Assistant API starting up (model=%s)", get_settings().model_name)
    yield
    await app.state.llm_engine.aclose()


app = FastAPI(title="Zor Fitness Assistant API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _send(websocket: WebSocket, event: BaseModel) -> None:
    # exclude_none: an optional field that isn't set (DoneEvent.sources) is left out of the JSON.
    await websocket.send_json(event.model_dump(exclude_none=True))


WARM_UP_EVERY_S = 300  # Ollama keeps the model 30 min; re-warming more often is wasted work
_last_warm_up = 0.0


async def _warm_up(llm_engine: LLMEngine) -> None:
    """Load the LLM back into GPU memory and run one tiny ASR + TTS job (errors are ignored).
    Skipped if done in the last 5 minutes, so two members starting voice together don't both
    queue warm-up work in front of their real questions."""
    global _last_warm_up
    if time.monotonic() - _last_warm_up < WARM_UP_EVERY_S:
        return
    _last_warm_up = time.monotonic()
    await asyncio.gather(llm_engine.warm_up(), asr.warm_up_async(),
                         tts.synthesize_async("OK."), return_exceptions=True)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    llm_engine: LLMEngine = app.state.llm_engine
    conversation_manager: ConversationManager = app.state.conversation_manager
    ollama_ok = await llm_engine.check_health()
    return HealthResponse(
        status="ok" if ollama_ok else "degraded",
        model=get_settings().model_name,
        ollama_reachable=ollama_ok,
        active_sessions=conversation_manager.session_count(),
    )


@app.post("/session/new", response_model=NewSessionResponse)
async def new_session() -> NewSessionResponse:
    conversation_manager: ConversationManager = app.state.conversation_manager
    session = conversation_manager.create_session()
    return NewSessionResponse(session_id=session.session_id, stage=session.stage.value)


@app.websocket("/ws/chat")
async def ws_chat(
    websocket: WebSocket,
    session_id: str | None = Query(default=None),
    # Assignment 3, both optional (an A1/A2 client sends neither and sees no difference):
    #   extended=1  the client understands the new event types (tools, voice, latency)
    #   user_id     a stable id kept by the browser, for per-user data (workouts, profile)
    extended: bool = Query(default=False),
    user_id: str | None = Query(default=None, max_length=64),
) -> None:
    # conversation_manager is looked up once (it's a fixed, long-lived singleton), but
    # llm_engine is re-read from app.state on every message rather than cached in a local --
    # cheap lookup, and it keeps the engine hot-swappable (useful for tests, and for any
    # future admin action that reloads/replaces the model without restarting the server).
    conversation_manager: ConversationManager = websocket.app.state.conversation_manager

    await websocket.accept()

    session = conversation_manager.get_session(session_id) if session_id else None
    is_new_session = session is None
    if session is None:
        session = conversation_manager.create_session()
    session.user_id = user_id or session.session_id
    await _send(websocket, SessionEvent(session_id=session.session_id, stage=session.stage.value))

    async def send(event: BaseModel) -> None:
        await _send(websocket, event)

    async def send_extra(event: BaseModel) -> None:
        """New (Assignment 3) event types: only for clients that asked for them."""
        if extended:
            await _send(websocket, event)

    voice = VoiceSession(send_extra)  # microphone state of THIS connection (Assignment 3)
    greeting = None

    try:
        if user_id:
            profile = await user_profile.load(user_id)
            voice.member_name = profile.get("name")  # helps Whisper spell an unusual name
            # CRM bonus: a returning member (new session) is greeted by name with their last
            # request -- as a normal assistant message (token + done), kept in the history so a
            # reply like "yes, let's continue" makes sense. Spoken too, once, when voice starts.
            # (Inside the try: a tab closed right now is a normal disconnect, not a crash.)
            greeting = user_profile.greeting(profile) if extended and is_new_session else None
            if greeting:
                await send(TokenEvent(content=greeting))
                await send(DoneEvent(stage=session.stage.value))
                session.history.append(Message(role="assistant", content=greeting))

        while True:
            # receive() instead of receive_text(): the socket now also carries BINARY frames
            # (microphone audio). Text frames are handled exactly as before.
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            llm_engine: LLMEngine = websocket.app.state.llm_engine

            if message.get("bytes") is not None:
                utterance = await voice.feed(message["bytes"])
                if utterance:  # end of speech: the transcript is a normal user turn
                    text, timings = utterance
                    await send_extra(VoiceStateEvent(state="thinking"))
                    await run_turn(send, conversation_manager, llm_engine, session, text,
                                   send_extra=send_extra, speech=SpeechOutput(send_extra, timings),
                                   timings=timings)
                    # The member may have just told Nova their name: refresh it for the next turn.
                    voice.member_name = (await user_profile.load(session.user_id)).get("name")
                    await voice.listen_again()
                continue
            raw = message.get("text") or ""

            try:
                client_msg = ClientMessage.model_validate_json(raw)
            except ValidationError as e:
                # Same error event and code as Assignment 1; only the text is clearer when the
                # message is simply over the 2,000-character limit.
                too_long = any(err["type"] == "string_too_long" for err in e.errors())
                await _send(
                    websocket,
                    ErrorEvent(
                        message="That message is too long (the limit is 2,000 characters). "
                        "Please shorten it and ask again."
                        if too_long
                        else "Malformed request: could not parse that as a valid chat message.",
                        code="bad_request",
                    ),
                )
                continue

            if client_msg.type == ClientMessageType.RESET:
                session = conversation_manager.reset_session(session.session_id)
                session.user_id = user_id or session.session_id
                await _send(
                    websocket,
                    SessionEvent(session_id=session.session_id, stage=session.stage.value),
                )
                continue

            if client_msg.type == ClientMessageType.VOICE_START:
                try:
                    await voice.start()
                except VoiceUnavailable as e:
                    await send_extra(ErrorEvent(message=str(e), code="voice_unavailable"))
                    continue
                # After a long idle the LLM is unloaded and the GPU is cold (measured: the first
                # spoken turn took 9.2 s). Warm everything in the background while the member
                # is still starting to talk.
                asyncio.create_task(_warm_up(llm_engine))
                if greeting:  # speak the welcome-back greeting once (it is already on screen)
                    speech = SpeechOutput(send_extra, TurnTimings())
                    await speech.feed(greeting)
                    await speech.finish()
                    await speech.close()
                    greeting = None
                    # Speaking set the state to "speaking": switch back to "listening", or the
                    # browser keeps the mic closed (it only sends audio while the server listens).
                    await voice.listen_again()
                continue
            if client_msg.type == ClientMessageType.VOICE_STOP:
                await voice.stop()
                continue

            # --- type == MESSAGE ---
            user_text = (client_msg.content or "").strip()
            if not user_text:
                await _send(
                    websocket,
                    ErrorEvent(message="Message content cannot be empty.", code="bad_request"),
                )
                continue

            # The whole turn (classify || retrieve -> LLM stream -> optional tool -> done) lives
            # in turn.py, shared with spoken turns.
            await run_turn(send, conversation_manager, llm_engine, session, user_text,
                           send_extra=send_extra)

    except WebSocketDisconnect:
        logger.info("Client disconnected (session_id=%s)", session.session_id)
    except Exception:  # pragma: no cover - last-resort safety net
        logger.exception("Unexpected error in /ws/chat (session_id=%s)", session.session_id)
        try:
            await _send(
                websocket,
                ErrorEvent(message="Internal server error.", code="internal_error"),
            )
        except Exception:
            pass  # socket is already gone; nothing more we can do
