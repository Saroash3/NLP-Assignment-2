"""
One conversation turn -- the SAME pipeline for a typed message and a spoken one.

  classify (off-topic gate) || retrieve (RAG) || route (tool router)   <- all three in parallel
  -> run the tool, if the router chose one (its result becomes a system message)
  -> build prompt (history + sources + tool result) -> stream the LLM reply
  -> citations, history, done

The only difference for a voice turn is `speech`: every reply token is also fed to it, and it
turns the tokens into sentences and audio (see voice/speech_output.py).

This logic was moved out of main.py. For typed text the event sequence is exactly Assignment 2's
(session/token/done/error). The NEW event types (tool_call, tool_result, latency and the voice
ones) go through `send_extra`, which is a no-op unless the client connected with ?extended=1 --
an Assignment 1/2 client sees exactly the old stream, nothing more.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

from pydantic import BaseModel

from app import orchestrator
from app.conversation_manager import ConversationManager, Session
from app.llm_engine import LLMEngine, LLMEngineError
from app.schemas import DoneEvent, ErrorEvent, LatencyEvent, TokenEvent, ToolCallEvent, ToolResultEvent
from app.tools import user_profile
from app.prompts import TOOL_TURN_NOTE
from app.tools.base import ToolContext

logger = logging.getLogger("zor_assistant")

Send = Callable[[BaseModel], Awaitable[None]]


@dataclass
class TurnTimings:
    """Latency of one turn, in milliseconds (None = that step didn't happen)."""

    asr_ms: float | None = None
    retrieval_ms: float | None = None  # classify || retrieve || route: the wait before the tool/LLM
    tool_ms: float | None = None
    llm_first_token_ms: float | None = None
    tts_first_audio_ms: float | None = None
    total_ms: float | None = None  # end of speech -> first audio chunk sent (voice only)
    end_of_speech_at: float | None = None  # perf_counter() when the VAD detected end of speech

    def event(self) -> LatencyEvent:
        fields = ("asr_ms", "retrieval_ms", "tool_ms", "llm_first_token_ms", "tts_first_audio_ms", "total_ms")
        return LatencyEvent(**{f: round(v) for f in fields if (v := getattr(self, f)) is not None})


async def _use_tool(call: dict, ctx: ToolContext, send_extra: Send, timings: TurnTimings) -> str:
    """Run the routed tool, show it as a card (tool_call -> tool_result) and return the system
    message that hands the result to the main model."""
    call_id = uuid.uuid4().hex[:8]
    await send_extra(ToolCallEvent(id=call_id, name=call["tool"], arguments=call["arguments"]))
    start = time.perf_counter()
    ok, result = await orchestrator.run_tool(call["tool"], call["arguments"], ctx)
    timings.tool_ms = (time.perf_counter() - start) * 1000
    logger.info("Tool %s(%s) -> ok=%s %s", call["tool"], call["arguments"], ok, result)
    await send_extra(ToolResultEvent(id=call_id, name=call["tool"], ok=ok, result=result))
    return orchestrator.tool_result_message(call["tool"], ok, result)


async def run_turn(send: Send, conversation_manager: ConversationManager, llm_engine: LLMEngine,
                   session: Session, user_text: str, *, send_extra: Send, speech=None,
                   timings: TurnTimings | None = None) -> None:
    timings = timings or TurnTimings()

    # A session can be shared by more than one live connection (e.g. the same session_id
    # opened in two browser tabs). is_generating stops those connections from generating
    # into the same history at the same time.
    if session.is_generating:
        await send(ErrorEvent(message="Still working on the previous message -- please wait for it "
                              "to finish.", code="busy"))
        return

    async def emit(text: str) -> None:
        """One chunk of the reply: to the chat, and (voice turns) to the speech pipeline."""
        await send(TokenEvent(content=text))
        if speech is not None:
            await speech.feed(text)

    session.is_generating = True
    try:
        # Three independent steps IN PARALLEL: the off-topic classifier (LLM call), retrieval
        # (worker thread) and the tool router (LLM call). The turn waits for the slowest one.
        start = time.perf_counter()
        # A browser-provided user_id (not the session-id fallback) means a returning member
        # can be remembered: their CRM profile is loaded in the same gather (file read, thread).
        known_user = session.user_id not in ("", session.session_id)
        redirect, chunks, call, profile = await asyncio.gather(
            conversation_manager.classify_off_topic(llm_engine, user_text),
            conversation_manager.retrieve_context(session, user_text),
            orchestrator.route(llm_engine, [], user_text),
            user_profile.load(session.user_id) if known_user else asyncio.sleep(0, {}),
        )
        # The router sees ONLY the latest message: with earlier turns in its context the 3B
        # model answered or re-used the previous question (measured: "carbs in rice" looked up
        # egg). Only a vague follow-up with no tool found ("what about chicken?") gets one retry
        # with the previous message attached.
        previous = conversation_manager.previous_user_message(session)
        if call is None and previous and conversation_manager.is_vague_follow_up(user_text):
            call = await orchestrator.route(llm_engine, [], f"{previous} {user_text}")
        timings.retrieval_ms = (time.perf_counter() - start) * 1000
        # A strong document match overrides a (wrong) OFF_TOPIC verdict, and so does a tool
        # call: "what's my BMI" is the member's own fitness, which the classifier can't know.
        redirect = None if call else conversation_manager.apply_retrieval_override(redirect, chunks)
        # A vague follow-up ("Okay, so what is that specific times?") to an answered, on-topic
        # turn stays on topic: the classifier sees it without its context and wrongly rejects it.
        # A clear off-topic question ("Who won the World Cup?") is not vague, so it is still gated.
        if redirect is not None and session.last_turn_on_topic and conversation_manager.is_vague_follow_up(user_text):
            logger.info("Classifier said OFF_TOPIC, but %r follows an on-topic turn; answering", user_text)
            redirect = None
        session.last_turn_on_topic = redirect is None

        if redirect is not None:
            # Off-topic: "stream" the canned redirect as ordinary tokens; not kept in history.
            for word in redirect.split(" "):
                await emit(word + " ")
            conversation_manager.record_turn(session, user_text, redirect, remember=False)
            await send(DoneEvent(stage=session.stage.value))
        else:
            ctx = ToolContext(user_id=session.user_id or session.session_id, spoken=speech is not None)
            note = user_profile.profile_note(profile)
            extra = [note] if note else []
            if call:
                call = orchestrator.apply_unit_hints(call, user_text)  # feet/pounds read by code
                extra.append(await _use_tool(call, ctx, send_extra, timings))  # tool result goes last
            prompt_messages, used_sources = conversation_manager.build_prompt(
                session, user_text, chunks, extra_system=extra,
                # A tool answers this one: "no matching documents" made the model reply "our
                # documents don't cover that" despite a correct tool result (live test, rice).
                context_note=TOOL_TURN_NOTE if call and not chunks else None,
            )
            reply_chunks: list[str] = []
            llm_start = time.perf_counter()
            async for token in llm_engine.stream_chat(prompt_messages):
                if timings.llm_first_token_ms is None:
                    timings.llm_first_token_ms = (time.perf_counter() - llm_start) * 1000
                reply_chunks.append(token)
                await emit(token)
            full_reply = "".join(reply_chunks).strip() or "Sorry, I didn't quite catch that -- could you rephrase?"

            # Citations only when the answer came from documents (not from a tool result).
            # The source line goes to the chat only -- it is never spoken.
            sources = None if call else conversation_manager.citations_for(used_sources, full_reply)
            if sources:
                await send(TokenEvent(content=conversation_manager.source_line(sources)))
            # History keeps the reply WITHOUT the source line (else the model starts copying it).
            conversation_manager.record_turn(
                session, user_text, full_reply, remember=not conversation_manager.is_refusal(full_reply)
            )
            await send(DoneEvent(stage=session.stage.value, sources=sources))

        if known_user and redirect is None:  # off-topic requests aren't worth remembering
            await user_profile.record_interaction(session.user_id, user_text)
        if speech is not None:
            await speech.finish()  # speak whatever is left, then audio_end
        logger.info("Turn latency %s", timings.event().model_dump(exclude={"type"}, exclude_none=True))
        await send_extra(timings.event())
    except LLMEngineError as e:
        await send(ErrorEvent(message=str(e), code="llm_error"))
    finally:
        if speech is not None:
            await speech.close()
        session.is_generating = False
