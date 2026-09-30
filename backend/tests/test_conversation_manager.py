"""
Unit tests for the conversation manager: session lifecycle, the sliding
context window, the cosmetic stage tracker, and the off-topic classification
gate. None of this needs Ollama running -- classify_off_topic() takes an
LLM engine as a parameter, so a fake stands in for it here exactly like the
websocket tests do.
"""
from collections import deque

import pytest

from app.conversation_manager import ConversationManager, Session, Stage
from app.llm_engine import GenerationStats
from app.prompts import OFF_TOPIC_REDIRECTS


def test_create_session_returns_unique_ids():
    cm = ConversationManager()
    s1 = cm.create_session()
    s2 = cm.create_session()
    assert s1.session_id != s2.session_id
    assert cm.session_count() == 2


def test_new_session_starts_at_greeting_with_empty_history():
    cm = ConversationManager()
    session = cm.create_session()
    assert session.stage == Stage.GREETING
    assert len(session.history) == 0


def test_prompt_messages_always_start_with_system_prompt():
    cm = ConversationManager()
    session = cm.create_session()
    messages = cm.build_prompt_messages(session, "Hi, what classes do you have?")
    assert messages[0]["role"] == "system"
    assert "Zor Fitness Club" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "Hi, what classes do you have?"}


def test_build_prompt_messages_does_not_mutate_history():
    # build_prompt_messages() must NOT write to history -- only record_turn()
    # should, so a failed generation never corrupts session state.
    cm = ConversationManager()
    session = cm.create_session()
    cm.build_prompt_messages(session, "hello")
    assert len(session.history) == 0


def test_record_turn_appends_user_and_assistant_messages():
    cm = ConversationManager()
    session = cm.create_session()
    cm.record_turn(session, "Hi there", "Welcome to Zor Fitness Club!")
    assert len(session.history) == 2
    assert session.history[0].role == "user"
    assert session.history[0].content == "Hi there"
    assert session.history[1].role == "assistant"


def test_sliding_window_drops_oldest_messages_once_full():
    # Directly construct a Session with a tiny window (2 turns = 4 messages)
    # instead of going through settings, so the test doesn't depend on the
    # configured MAX_HISTORY_TURNS.
    cm = ConversationManager()
    session = Session(session_id="test-session", history=deque(maxlen=4))

    for i in range(5):
        cm.record_turn(session, f"user message {i}", f"assistant reply {i}")

    assert len(session.history) == 4  # never exceeds the window
    contents = [m.content for m in session.history]
    assert "user message 0" not in contents  # oldest exchange fell off
    assert "user message 4" in contents  # most recent is kept
    assert "assistant reply 4" in contents


def test_reset_session_clears_history_and_issues_new_id():
    cm = ConversationManager()
    session = cm.create_session()
    old_id = session.session_id
    cm.record_turn(session, "hello", "hi!")

    new_session = cm.reset_session(old_id)

    assert new_session.session_id != old_id
    assert cm.get_session(old_id) is None
    assert len(new_session.history) == 0
    assert new_session.stage == Stage.GREETING


def test_stage_moves_to_action_on_booking_intent():
    cm = ConversationManager()
    session = cm.create_session()
    cm.record_turn(session, "I'd like to book the Yoga Flow class on Friday", "Sure thing!")
    assert session.stage == Stage.ACTION


def test_stage_moves_to_information_gathering_on_pricing_question():
    cm = ConversationManager()
    session = cm.create_session()
    cm.record_turn(session, "What are your membership plans and prices?", "We have three tiers...")
    assert session.stage == Stage.INFORMATION_GATHERING


def test_stage_moves_to_confirmation_after_yes_following_action():
    cm = ConversationManager()
    session = cm.create_session()
    session.stage = Stage.ACTION
    cm.record_turn(session, "Yes that works, please confirm", "You're all booked in!")
    assert session.stage == Stage.CONFIRMATION


class _FakeClassifierEngine:
    """Returns a fixed verdict string, as if it were the classification call's output."""

    def __init__(self, verdict_text: str):
        self._verdict_text = verdict_text

    async def generate_with_stats(self, messages, **kwargs):
        stats = GenerationStats(time_to_first_token_s=0.001, total_time_s=0.001, completion_tokens=1)
        return self._verdict_text, stats


@pytest.mark.asyncio
async def test_classify_off_topic_returns_none_for_on_topic_verdict():
    cm = ConversationManager()
    engine = _FakeClassifierEngine("ON_TOPIC")
    result = await cm.classify_off_topic(engine, "What classes do you have on Tuesdays?")
    assert result is None


@pytest.mark.asyncio
async def test_classify_off_topic_returns_a_known_redirect_for_off_topic_verdict():
    cm = ConversationManager()
    engine = _FakeClassifierEngine("OFF_TOPIC")
    result = await cm.classify_off_topic(engine, "Who is Taylor Swift?")
    assert result in OFF_TOPIC_REDIRECTS


@pytest.mark.asyncio
async def test_classify_off_topic_is_case_insensitive_and_tolerates_whitespace():
    cm = ConversationManager()
    engine = _FakeClassifierEngine("  off_topic\n")
    result = await cm.classify_off_topic(engine, "write me a script")
    assert result in OFF_TOPIC_REDIRECTS


@pytest.mark.asyncio
async def test_classify_off_topic_fails_open_on_an_unparseable_verdict():
    # Fails OPEN (returns None, i.e. "treat as on-topic") rather than closed -- see
    # the docstring on classify_off_topic for why over-refusing on a garbled
    # verdict is the worse failure mode here.
    cm = ConversationManager()
    engine = _FakeClassifierEngine("sure, I can help with that!")
    result = await cm.classify_off_topic(engine, "hello")
    assert result is None
