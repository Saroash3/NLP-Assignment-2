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
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.conversation_manager import ConversationManager, _qwen_tokenizer
from app.llm_engine import LLMEngine, LLMEngineError
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
async def ws_chat(websocket: WebSocket, session_id: str | None = Query(default=None)) -> None:
    # conversation_manager is looked up once (it's a fixed, long-lived singleton), but
    # llm_engine is re-read from app.state on every message rather than cached in a local --
    # cheap lookup, and it keeps the engine hot-swappable (useful for tests, and for any
    # future admin action that reloads/replaces the model without restarting the server).
    conversation_manager: ConversationManager = websocket.app.state.conversation_manager

    await websocket.accept()

    session = conversation_manager.get_session(session_id) if session_id else None
    if session is None:
        session = conversation_manager.create_session()
    await _send(websocket, SessionEvent(session_id=session.session_id, stage=session.stage.value))

    try:
        while True:
            raw = await websocket.receive_text()
            llm_engine: LLMEngine = websocket.app.state.llm_engine

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
                await _send(
                    websocket,
                    SessionEvent(session_id=session.session_id, stage=session.stage.value),
                )
                continue

            # --- type == MESSAGE ---
            user_text = (client_msg.content or "").strip()
            if not user_text:
                await _send(
                    websocket,
                    ErrorEvent(message="Message content cannot be empty.", code="bad_request"),
                )
                continue

            # A session can be shared by more than one live connection (e.g. the same
            # session_id opened in two browser tabs). is_generating is what stops those
            # two connections from generating into the same history at the same time --
            # a single connection alone can never hit this, since receive_text() already
            # serializes messages on one socket.
            if session.is_generating:
                await _send(
                    websocket,
                    ErrorEvent(
                        message="Still working on the previous message -- please wait for it "
                        "to finish.",
                        code="busy",
                    ),
                )
                continue

            session.is_generating = True
            try:
                # Stage 1 of the two-stage pipeline (classify) runs IN PARALLEL with
                # retrieval: the classifier is an LLM call (a few hundred ms) and retrieval
                # runs in a worker thread (tens of ms), so retrieval adds ~0 ms to the wait.
                # If the message is off-topic, the retrieved chunks are simply unused.
                redirect, chunks = await asyncio.gather(
                    conversation_manager.classify_off_topic(llm_engine, user_text),
                    conversation_manager.retrieve_context(session, user_text),
                )
                # A strong document match overrides a (wrong) OFF_TOPIC verdict.
                redirect = conversation_manager.apply_retrieval_override(redirect, chunks)

                if redirect is not None:
                    # Off-topic: skip the real generation call entirely and "stream" the
                    # canned redirect as the same TokenEvent/DoneEvent sequence a real
                    # reply would produce, so the frontend can't tell the difference.
                    for word in redirect.split(" "):
                        await _send(websocket, TokenEvent(content=word + " "))
                    # Redirects are not kept in the model's history (no facts; they prime refusals).
                    conversation_manager.record_turn(session, user_text, redirect, remember=False)
                    await _send(websocket, DoneEvent(stage=session.stage.value))
                else:
                    prompt_messages, used_sources = conversation_manager.build_prompt(
                        session, user_text, chunks
                    )
                    reply_chunks: list[str] = []
                    async for token in llm_engine.stream_chat(prompt_messages):
                        reply_chunks.append(token)
                        await _send(websocket, TokenEvent(content=token))

                    full_reply = "".join(reply_chunks).strip()
                    if not full_reply:
                        full_reply = "Sorry, I didn't quite catch that -- could you rephrase?"

                    # Citations, only when the answer was grounded in sources: a final
                    # "Source: ..." line streamed as one more ordinary token, and the same list
                    # in the optional `sources` field of `done` (for the UI chips).
                    sources = conversation_manager.citations_for(used_sources, full_reply)
                    if sources:
                        await _send(websocket, TokenEvent(content=conversation_manager.source_line(sources)))
                    # History keeps the reply WITHOUT the source line: otherwise the model copies
                    # "Sources: ..." into its next answers and the line appears twice.
                    conversation_manager.record_turn(
                        session, user_text, full_reply,
                        remember=not conversation_manager.is_refusal(full_reply),
                    )
                    await _send(websocket, DoneEvent(stage=session.stage.value, sources=sources))
            except LLMEngineError as e:
                await _send(websocket, ErrorEvent(message=str(e), code="llm_error"))
            finally:
                session.is_generating = False

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
