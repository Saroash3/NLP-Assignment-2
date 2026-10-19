"""
Conversation Manager: per-session dialogue state, history windowing, and a
lightweight stage tracker.

CONTEXT MEMORY MANAGEMENT STRATEGY -- read this before touching the window
logic. We use a SLIDING WINDOW over the last N exchanges (Settings.
max_history_turns), not a rolling LLM-generated summary. Chosen because:

  1. Latency is graded (Phase VI). A rolling-summary approach needs an
     extra LLM call every few turns just to compress history, which adds
     unpredictable latency and, on a small local model, risks a
     *hallucinated* summary that silently drops a detail the member
     already gave (e.g. quietly forgetting which plan they picked).
  2. Gym front-desk conversations are naturally short and transactional --
     a handful of turns to book a class or compare plans -- so they
     rarely approach the window size in practice.
  3. Domain knowledge (pricing, schedules, policies) is retrieved fresh
     from the documents on every turn (RAG), not carried in history, so
     trimming old turns never makes the assistant "forget" a fact -- only
     the specifics of small talk from many turns back.

RAG + CONTEXT BUDGET (Assignment 2) -- see retrieve_context() and
build_prompt_messages(). Every prompt must fit in num_ctx (4096 tokens):
  reply space (num_predict)  500   always reserved
  system prompt             ~1559  fixed
  scope reminder              ~92  fixed
  user message             actual  always kept
  sources (chunks)         <=1200  lowest-ranked chunk dropped first
  history              the rest    oldest messages dropped first
Tokens are counted with Qwen2.5's own tokenizer (+5 per message for the
chat template), which matched Ollama's prompt_eval_count within ~1%.

The `stage` field on a Session is a best-effort heuristic used ONLY to
drive a cosmetic "stage" badge in the frontend UI. It does not gate what
the model is allowed to say. Actual stage-appropriate behavior and
graceful handling of a mid-conversation topic change are the system
prompt's job (see prompts.py) -- per the assignment's requirement that all
of the assistant's real intelligence come from prompt design, not
hardcoded keyword logic.

OFF-TOPIC DETECTION IS A TWO-STAGE PIPELINE, NOT PURE PROMPT DESIGN -- see
prompts.py's module docstring for the full disclosure. classify_off_topic()
below makes a separate, cheap LLM call whose only job is a strict ON_TOPIC/
OFF_TOPIC verdict; main.py calls it BEFORE build_prompt_messages() and skips
the real generation call entirely when the verdict is OFF_TOPIC. This was a
deliberate, requested change after the single-prompt approach measured at
20-80% off-topic redirect reliability depending on model size (see the
README's Known Limitations) -- not an oversight of the "prompt design only"
guidance the rest of this module still follows.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache

from app.config import get_settings
from app.llm_engine import LLMEngine
from app.prompts import (
    OFF_TOPIC_REDIRECTS,
    SCOPE_REMINDER,
    build_classification_messages,
    build_context_message,
    build_system_prompt,
)
from rag import retriever

logger = logging.getLogger("zor_assistant")

SYSTEM_PROMPT = build_system_prompt()

# Tiny token budget and temperature 0 -- this call only ever needs to produce
# one of two words, so it should be both fast and as deterministic as possible.
CLASSIFIER_NUM_PREDICT = 10
CLASSIFIER_TEMPERATURE = 0.0

# --- RAG settings (see the module docstring for the full budget) ---
CHUNK_TOKEN_BUDGET = 1200  # max tokens for the SOURCES message (4 chunks usually cost 930-1180)
PER_MESSAGE_OVERHEAD = 5  # chat-template tokens Qwen adds around each message
# FOLLOW-UP RULE. "and for ladies?" means nothing on its own, so it is embedded together with
# the previous user message. But most short messages are complete questions ("What is the
# guest fee?", "Is there a pool at F-7?"); gluing them to an unrelated previous question
# retrieved the WRONG documents (measured: 50% failures when merged vs 12% alone). So a short
# message is merged only if it LOOKS like a follow-up: it starts with a connector, or refers
# back with a pronoun. Chunks found through a merged query never overrule the classifier.
FOLLOW_UP_MAX_WORDS = 6
FOLLOW_UP_STARTERS = ("and ", "or ", "also ", "what about", "how about", "for ", "but ", "so ",
                      "then ", "aur ", "or what", "same ")
FOLLOW_UP_PRONOUNS = re.compile(r"\b(it|its|that|this|these|those|they|them|he|she|him|one|ones|wahan|uska|uski)\b",
                                re.IGNORECASE)
# Replies that refused or redirected. They carry no facts, and keeping them in the model's
# history made it repeat the refusal for later, answerable questions (measured), so such
# exchanges are not kept in the history (see record_turn).
REFUSAL_REPLY = re.compile(r"(documents|sources) don.?t cover|can.?t look that up", re.IGNORECASE)
# Longest user message kept in the prompt (see truncate_user_message). With it, the fixed
# parts are at most 500 + ~1559 + ~92 + 1000 tokens, which still leaves ~900 for sources.
MAX_USER_TOKENS = 1000


@lru_cache(maxsize=1)
def _qwen_tokenizer():
    """Qwen2.5's own tokenizer (local after a one-time ~7 MB download). None if unavailable."""
    try:
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained("Qwen/Qwen2.5-3B-Instruct")
    except Exception:
        logger.warning("Qwen tokenizer unavailable; using a conservative length estimate")
        return None


def count_tokens(text: str) -> int:
    """Tokens one chat message will use in the prompt (content + template overhead)."""
    tokenizer = _qwen_tokenizer()
    content = len(tokenizer.encode(text)) if tokenizer else len(text) // 3  # fallback over-estimates
    return content + PER_MESSAGE_OVERHEAD


class Stage(str, Enum):
    GREETING = "greeting"
    INFORMATION_GATHERING = "information_gathering"
    ACTION = "action"
    CONFIRMATION = "confirmation"
    CLOSING = "closing"


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str
    ts: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    history: "deque[Message]"
    stage: Stage = Stage.GREETING
    is_generating: bool = False
    user_id: str = ""  # Assignment 3: whose workouts/profile the tools use (set by main.py)
    last_turn_on_topic: bool = False  # Assignment 3: was the previous turn answered (not redirected)?
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


# --- Cosmetic stage heuristics (UI badge only -- see module docstring) ---

_ACTION_PATTERNS = re.compile(
    r"\b(book|sign me up|reserve|freeze|pause|cancel|join|enroll)\b", re.IGNORECASE
)
_INFO_PATTERNS = re.compile(
    r"\b(price|plan|cost|schedule|class|trainer|hour|policy|membership)\b", re.IGNORECASE
)
_CONFIRM_PATTERNS = re.compile(
    r"\b(yes|yeah|confirm|correct|that works|sounds good|yep)\b", re.IGNORECASE
)
_CLOSING_PATTERNS = re.compile(
    r"\b(bye|goodbye|that'?s all|nothing else|thanks|thank you)\b", re.IGNORECASE
)


def _guess_stage(previous: Stage, user_text: str) -> Stage:
    """Best-effort stage guess for the UI badge only -- see module docstring."""
    text = user_text.strip()
    if _CLOSING_PATTERNS.search(text) and previous in (
        Stage.CONFIRMATION,
        Stage.ACTION,
        Stage.CLOSING,
    ):
        return Stage.CLOSING
    if _ACTION_PATTERNS.search(text):
        return Stage.ACTION
    if _CONFIRM_PATTERNS.search(text) and previous == Stage.ACTION:
        return Stage.CONFIRMATION
    if _INFO_PATTERNS.search(text):
        return Stage.INFORMATION_GATHERING
    if previous == Stage.GREETING:
        return Stage.INFORMATION_GATHERING
    return previous


class ConversationManager:
    """
    Owns all active sessions and is the single place that turns
    (session history + new user message) into the exact message list sent
    to the LLM engine. The FastAPI layer never touches history directly --
    it only calls build_prompt_messages() / record_turn() on this class.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._max_turns = get_settings().max_history_turns

    def create_session(self) -> Session:
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            # maxlen counts MESSAGES, not turns: 2 messages (user + assistant) per turn.
            history=deque(maxlen=self._max_turns * 2),
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def reset_session(self, session_id: str) -> Session:
        """Used by the 'reset' websocket message and POST /session/new."""
        self._sessions.pop(session_id, None)
        return self.create_session()

    async def classify_off_topic(self, llm_engine: LLMEngine, user_text: str) -> str | None:
        """
        Stage 1 of the two-stage pipeline. Returns a canned redirect string if
        `user_text` is judged off-topic, or None if on-topic (caller should
        proceed to build_prompt_messages() + a real generation call as normal).

        Classification verdicts that don't parse as a clean single word
        default to None -- i.e. fail OPEN, not closed. Two reasons: (1) the
        main persona prompt's own scope rules are still a second line of
        defense even when this gate misses something, so failing open doesn't
        remove all protection; (2) failing closed on every ambiguous verdict
        would risk refusing legitimate requests whenever the classifier
        hiccups, which is the same over-refusal failure mode observed during
        manual testing of the single-prompt approach (see docs/TESTING.md).
        """
        messages = build_classification_messages(user_text)
        raw, _ = await llm_engine.generate_with_stats(
            messages, num_predict=CLASSIFIER_NUM_PREDICT, temperature=CLASSIFIER_TEMPERATURE
        )
        verdict = raw.strip().upper()
        if "OFF_TOPIC" in verdict and "ON_TOPIC" not in verdict:
            return random.choice(OFF_TOPIC_REDIRECTS)
        return None

    # --- RAG: retrieval ---

    @staticmethod
    def looks_like_follow_up(user_text: str) -> bool:
        """Short AND (starts with a connector OR refers back with a pronoun)."""
        text = user_text.strip().lower()
        if len(text.split()) > FOLLOW_UP_MAX_WORDS:
            return False
        return text.startswith(FOLLOW_UP_STARTERS) or bool(FOLLOW_UP_PRONOUNS.search(text))

    @staticmethod
    def is_vague_follow_up(user_text: str) -> bool:
        """Assignment 3, for the OFF-TOPIC gate only (retrieval keeps the rule above): a short
        message that only makes sense with the previous turn -- "Okay, so what is that specific
        times?", "and when do the males go?". The classifier sees one message alone and rejected
        these in a live test. Fillers like "okay," are skipped; up to 8 words."""
        text = re.sub(r"^(okay|ok|alright|so|and|um+|hmm+)[,.]?\s+", "", user_text.strip().lower())
        if len(text.split()) > 8:
            return False
        return text.startswith(FOLLOW_UP_STARTERS + ("when ", "what about", "how about")) or bool(
            FOLLOW_UP_PRONOUNS.search(text))

    def previous_user_message(self, session: Session) -> str | None:
        return next((m.content for m in reversed(session.history) if m.role == "user"), None)

    def retrieval_query(self, session: Session, user_text: str) -> str:
        """The text to embed: a follow-up gets the previous user message prepended;
        everything else (including short complete questions) is embedded alone."""
        previous = self.previous_user_message(session)
        if previous and self.looks_like_follow_up(user_text):
            return f"{previous} {user_text}"
        return user_text

    async def retrieve_context(self, session: Session, user_text: str) -> list[dict] | None:
        """
        Retrieve the top-k chunks for this message and keep only those above the
        similarity threshold. Embedding + vector search are CPU-bound, so they run in
        a worker thread (asyncio.to_thread) and never block the event loop.
        Returns:
          [chunks...]  relevant chunks found
          []           retrieval worked, but nothing passed the threshold (no match)
          None         retrieval FAILED (index missing/corrupted/empty, embedding error,
                       or slower than retrieval_timeout_s). The error is logged and the
                       reply continues with the "retrieval unavailable" note -- the chat
                       never crashes or hangs because of retrieval.
        """
        settings = get_settings()

        async def search(query: str) -> list[dict]:
            start = time.perf_counter()
            chunks = await asyncio.wait_for(
                asyncio.to_thread(retriever.retrieve, query), timeout=settings.retrieval_timeout_s
            )
            logger.info("Retrieval %.0f ms, query=%r -> %s", (time.perf_counter() - start) * 1000,
                        query, [(c["source"], c["score"]) for c in chunks])
            return [c for c in chunks if c["score"] >= settings.similarity_threshold]

        query = self.retrieval_query(session, user_text)
        try:
            relevant = await search(query)
            # (No "retry merged if nothing found" fallback: it gave greetings and off-topic
            # messages the PREVIOUS question's documents and chips.)
            if query != user_text:
                # Chunks found with the help of the PREVIOUS message. They may answer a real
                # follow-up, but they say nothing about whether THIS message is on-topic, so
                # apply_retrieval_override ignores them ("Who won the cricket World Cup?" after
                # a guest question must still be redirected).
                relevant = [{**c, "merged": True} for c in relevant]
        except Exception as e:  # includes TimeoutError from wait_for
            logger.warning("Retrieval unavailable (%s: %s); replying without documents",
                           type(e).__name__, e)
            return None
        return relevant

    def apply_retrieval_override(self, redirect: str | None, chunks: list[dict]) -> str | None:
        """
        The classifier sometimes rejects real gym questions (e.g. anything mentioning
        "Bahria" or a trainer's name). If it said OFF_TOPIC (redirect is not None) but a
        document matches strongly, trust the documents: return None = answer normally.
        """
        # Only the message's OWN retrieval may overrule the classifier, never chunks that were
        # found by merging it with the previous message.
        if redirect is not None and chunks and not chunks[0].get("merged"):
            best = chunks[0]["score"]
            if best >= get_settings().classifier_override_score:
                logger.info("Classifier said OFF_TOPIC, but %s matched at %.3f; answering "
                            "from sources", chunks[0]["source"], best)
                return None
        return redirect

    # --- Prompt assembly with the token budget ---

    def select_chunks(self, chunks: list[dict], budget: int) -> list[dict]:
        """Keep chunks best-first while the SOURCES message fits the budget; the
        lowest-ranked chunks are the ones dropped."""
        kept: list[dict] = []
        for chunk in chunks:
            if count_tokens(build_context_message(kept + [chunk])) > budget:
                break
            kept.append(chunk)
        return kept

    def truncate_user_message(self, user_text: str) -> str:
        """
        The API already caps messages at 2,000 characters, but Urdu script (and other
        non-Latin text) costs far more tokens per character than English. Rule: a message
        is capped at MAX_USER_TOKENS -- the beginning is kept (that's usually where the
        question is) and a clear marker tells the model the rest was cut.
        """
        tokenizer = _qwen_tokenizer()
        if count_tokens(user_text) <= MAX_USER_TOKENS:
            return user_text
        if tokenizer:
            kept = tokenizer.decode(tokenizer.encode(user_text)[: MAX_USER_TOKENS - 20])
        else:
            kept = user_text[: MAX_USER_TOKENS * 3]
        logger.info("User message truncated to %d tokens", MAX_USER_TOKENS)
        return kept + " …[message truncated: it was too long]"

    def build_prompt_messages(
        self, session: Session, user_text: str, chunks: list[dict] | None = ()
    ) -> list[dict[str, str]]:
        """The prompt only (see build_prompt, which also returns the sources used)."""
        return self.build_prompt(session, user_text, chunks)[0]

    @staticmethod
    def citations_for(sources: list[str], reply: str) -> list[str] | None:
        """
        Citations for the `done` event (bonus): the deduplicated source files that were in
        the prompt -- or None (no citations) if there were none, or if the reply itself says
        the documents don't cover the question (the phrase our prompts tell the model to use),
        e.g. "Do you offer MMA?", where the retrieved chunks were only related, not answers.
        """
        if not sources or re.search(r"(documents|sources) don.t cover", reply, re.IGNORECASE):
            return None
        return sources

    @staticmethod
    def source_line(sources: list[str]) -> str:
        """The short line appended (as one final token) to every grounded answer. Added by
        the server, not the model, because the 3B model put it at the start, the end, or
        nowhere; this way it is ALWAYS at the end and always matches the citation chips."""
        return f"\n\n{'Source' if len(sources) == 1 else 'Sources'}: {', '.join(sources)}"

    def build_prompt(
        self, session: Session, user_text: str, chunks: list[dict] | None = (),
        extra_system: list[str] = (), context_note: str | None = None,
    ) -> tuple[list[dict[str, str]], list[str]]:
        """
        Assemble the exact message list to send to the LLM:
          [system prompt] + [history, oldest trimmed to fit] + [SOURCES or no-match note]
          + [scope reminder] + [extra_system: tool result / member profile, Assignment 3]
          + [user message]
        The static system prompt + history come first so they form the same prefix every
        turn (Ollama can reuse its cache); the per-turn sources come last, right next to
        the question. The new message is NOT written into session.history here -- callers
        append the real user/assistant pair only after a successful generation (see
        main.py), so a failed generation never corrupts history.
        """
        settings = get_settings()
        user_text = self.truncate_user_message(user_text)
        # Tokens left for sources + history after the parts that are always included.
        # The system prompt is counted FIRST and always kept whole -- it is never what gets cut.
        available = (
            settings.num_ctx
            - settings.num_predict  # reply space
            - count_tokens(SYSTEM_PROMPT)
            - count_tokens(SCOPE_REMINDER)
            - count_tokens(user_text)
            # Assignment 3: tool result / member profile messages are always kept, like the user text.
            - sum(count_tokens(text) for text in extra_system)
        )

        # Step 1: sources. Drop the lowest-ranked chunks until they fit their own budget
        # (and whatever space is really left, in case the user message was huge).
        kept: list[dict] = []
        if context_note is not None:  # Assignment 3: a tool answers this turn (see turn.py)
            context = context_note
        elif chunks is None:  # retrieval failed: send the "unavailable" note, not "no match"
            context = build_context_message(None)
        else:
            kept = self.select_chunks(chunks, min(CHUNK_TOKEN_BUDGET, available))
            context = build_context_message(kept)
        available -= count_tokens(context)

        # Step 2: history. Walk newest -> oldest and stop when the next message won't fit,
        # so the OLDEST messages are the ones trimmed.
        history: list[dict[str, str]] = []
        for m in reversed(session.history):
            cost = count_tokens(m.content)
            if cost > available:
                break
            history.insert(0, {"role": m.role, "content": m.content})
            available -= cost

        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        messages.append({"role": "system", "content": context})
        # "Sandwiching": repeat the scope rule as a system message immediately before the
        # final user turn -- the last instruction the small model sees before generating.
        messages.append({"role": "system", "content": SCOPE_REMINDER})
        # Assignment 3: tool result / profile go AFTER the reminder, so the reminder's "refuse
        # math" rule doesn't override a BMI result (measured: the model recomputed it wrongly).
        messages.extend({"role": "system", "content": text} for text in extra_system)
        messages.append({"role": "user", "content": user_text})
        # Source files actually in the prompt (after the budget), deduplicated, best first.
        sources = list(dict.fromkeys(c["source"] for c in kept))
        return messages, sources

    @staticmethod
    def is_refusal(reply: str) -> bool:
        """True for "our documents don't cover that" / "can't look that up" replies."""
        return bool(REFUSAL_REPLY.search(reply))

    def record_turn(
        self, session: Session, user_text: str, assistant_text: str, remember: bool = True
    ) -> None:
        """
        Update the stage guess and append the exchange to history. remember=False (used for
        refusals and off-topic redirects) skips the history: those exchanges carry no facts,
        and keeping them made the small model repeat the refusal for later, answerable
        questions (measured: e.g. a guest-rule question went from answered to refused 3/3).
        """
        session.stage = _guess_stage(session.stage, user_text)
        if remember:
            session.history.append(Message(role="user", content=user_text))
            session.history.append(Message(role="assistant", content=assistant_text))
        session.last_active = time.time()

    def session_count(self) -> int:
        return len(self._sessions)
