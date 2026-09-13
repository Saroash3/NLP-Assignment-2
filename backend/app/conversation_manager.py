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
  3. All static domain knowledge (pricing, schedules, policies) already
     lives in the system prompt, not in history, so trimming old turns
     never makes the assistant "forget" a fact -- only the specifics of
     small talk from many turns back, which is an acceptable tradeoff.

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

import random
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from app.config import get_settings
from app.llm_engine import LLMEngine
from app.prompts import (
    OFF_TOPIC_REDIRECTS,
    SCOPE_REMINDER,
    build_classification_messages,
    build_system_prompt,
)

SYSTEM_PROMPT = build_system_prompt()

# Tiny token budget and temperature 0 -- this call only ever needs to produce
# one of two words, so it should be both fast and as deterministic as possible.
CLASSIFIER_NUM_PREDICT = 10
CLASSIFIER_TEMPERATURE = 0.0


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

    def build_prompt_messages(self, session: Session, user_text: str) -> list[dict[str, str]]:
        """
        Assemble the exact message list to send to the LLM: system prompt +
        sliding window of prior turns + the new user message. The new
        message is NOT written into session.history here -- callers append
        the real user/assistant pair only after a successful generation
        (see main.py), so a failed generation never corrupts history.
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend({"role": m.role, "content": m.content} for m in session.history)
        # "Sandwiching": repeat the scope rule as a second system message immediately
        # before the final user turn, not just once at the top of a long system prompt.
        # This is a fixed structural technique applied identically on every turn -- it
        # never inspects what the user said, so it's still pure prompt orchestration --
        # but it noticeably improves a small model's odds of catching the scope rule,
        # since it's the last instruction the model sees before generating.
        messages.append({"role": "system", "content": SCOPE_REMINDER})
        messages.append({"role": "user", "content": user_text})
        return messages

    def record_turn(self, session: Session, user_text: str, assistant_text: str) -> None:
        """Append a completed exchange to history and update the stage guess."""
        session.stage = _guess_stage(session.stage, user_text)
        session.history.append(Message(role="user", content=user_text))
        session.history.append(Message(role="assistant", content=assistant_text))
        session.last_active = time.time()

    def session_count(self) -> int:
        return len(self._sessions)
