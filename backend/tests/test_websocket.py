"""
Integration tests for the /ws/chat endpoint and REST routes, run against
the real FastAPI app via Starlette's TestClient. app.state.llm_engine is
swapped for a fake in-process engine so these tests never require Ollama
or a real model -- they verify OUR protocol/error-handling code, which is
what Phase VI ("break it on purpose") asks for:
  - malformed messages get a clean error, not a crash
  - a model error gets a clean error and the socket stays usable
  - a mid-stream disconnect does not take the server down
  - concurrent sessions stay isolated from each other
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.llm_engine import GenerationStats, LLMEngineError
from app.main import app

# generate_with_stats is what ConversationManager.classify_off_topic calls for the
# classification step, which now runs before every message. Every fake engine below
# needs it -- returning "ON_TOPIC" by default so tests written before the two-stage
# pipeline existed keep exercising the same main-generation path they always did.
_ON_TOPIC_STATS = GenerationStats(time_to_first_token_s=0.001, total_time_s=0.001, completion_tokens=1)


class FakeLLMEngine:
    """Yields a canned reply word-by-word; optional delay simulates streaming latency."""

    def __init__(self, reply: str = "Welcome to Zor Fitness Club! How can I help?", delay: float = 0.0):
        self.reply = reply
        self.delay = delay

    async def stream_chat(self, messages):
        for word in self.reply.split(" "):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield word + " "

    async def generate_with_stats(self, messages, **kwargs):
        # Classification should be fast regardless of `delay` -- it's only the main
        # reply (stream_chat) that simulates slow generation in these tests.
        return "ON_TOPIC", _ON_TOPIC_STATS

    async def check_health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class FailingLLMEngine:
    """Simulates Ollama being unreachable/erroring on every request."""

    async def stream_chat(self, messages):
        if False:  # pragma: no cover - forces async-generator semantics
            yield ""
        raise LLMEngineError("Could not reach the local Ollama server. Is `ollama serve` running?")

    async def generate_with_stats(self, messages, **kwargs):
        raise LLMEngineError("Could not reach the local Ollama server. Is `ollama serve` running?")

    async def check_health(self) -> bool:
        return False

    async def aclose(self) -> None:
        return None


class OffTopicFakeLLMEngine:
    """
    Always classifies as OFF_TOPIC, and fails the test loudly if stream_chat is ever
    called -- proving the two-stage pipeline actually skips the main generation call
    rather than merely trusting main.py's control flow to do so.
    """

    async def generate_with_stats(self, messages, **kwargs):
        return "OFF_TOPIC", _ON_TOPIC_STATS

    async def stream_chat(self, messages):
        if False:  # pragma: no cover - forces async-generator semantics
            yield ""
        raise AssertionError("stream_chat should never be called for an OFF_TOPIC verdict")

    async def check_health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


def _drain_until_done(ws):
    """Read events until 'done', failing loudly on any unexpected 'error'."""
    while True:
        event = ws.receive_json()
        if event["type"] == "done":
            return event
        if event["type"] == "error":
            raise AssertionError(f"unexpected error event: {event}")


# --- REST endpoints ---


def test_health_endpoint():
    with TestClient(app) as client:
        app.state.llm_engine = FakeLLMEngine()
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["ollama_reachable"] is True
        assert "model" in body


def test_new_session_rest_endpoint():
    with TestClient(app) as client:
        response = client.post("/session/new")
        assert response.status_code == 200
        body = response.json()
        assert body["stage"] == "greeting"
        assert len(body["session_id"]) > 0


# --- Happy path ---


def test_full_message_roundtrip_streams_tokens_then_done():
    with TestClient(app) as client:
        app.state.llm_engine = FakeLLMEngine(reply="Hi! How can I help you today?")
        with client.websocket_connect("/ws/chat") as ws:
            session_event = ws.receive_json()
            assert session_event["type"] == "session"
            assert session_event["stage"] == "greeting"

            ws.send_json({"type": "message", "content": "Hi there"})

            tokens = []
            while True:
                event = ws.receive_json()
                if event["type"] == "token":
                    tokens.append(event["content"])
                elif event["type"] == "done":
                    break
                else:
                    pytest.fail(f"unexpected event: {event}")

            assert "".join(tokens).strip() == "Hi! How can I help you today?"


def test_off_topic_classification_skips_main_generation_call():
    """
    The core guarantee of the two-stage pipeline: when classification says
    OFF_TOPIC, the real generation call (stream_chat) must never run. If it
    were called, OffTopicFakeLLMEngine raises AssertionError, which main.py's
    generic except-Exception handler turns into an 'internal_error' event --
    so a passing test here proves the skip actually happens, not just that
    main.py's code *looks* like it should skip it.
    """
    with TestClient(app) as client:
        app.state.llm_engine = OffTopicFakeLLMEngine()
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "who is Taylor Swift"})
            done_event = _drain_until_done(ws)
            assert done_event["type"] == "done"


def test_reset_message_clears_history_and_issues_new_session_id():
    with TestClient(app) as client:
        app.state.llm_engine = FakeLLMEngine()
        with client.websocket_connect("/ws/chat") as ws:
            first_session = ws.receive_json()

            ws.send_json({"type": "message", "content": "Book me into a spin class"})
            _drain_until_done(ws)

            ws.send_json({"type": "reset"})
            reset_event = ws.receive_json()

            assert reset_event["type"] == "session"
            assert reset_event["session_id"] != first_session["session_id"]
            assert reset_event["stage"] == "greeting"


# --- Failure handling (Phase VI) ---


def test_malformed_json_returns_clean_error_and_keeps_socket_open():
    with TestClient(app) as client:
        app.state.llm_engine = FakeLLMEngine()
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()  # initial session event

            ws.send_text("this is not valid JSON at all {{{")
            error_event = ws.receive_json()
            assert error_event["type"] == "error"
            assert error_event["code"] == "bad_request"

            # the connection must still work after a malformed message
            ws.send_json({"type": "message", "content": "hello again"})
            next_event = ws.receive_json()
            assert next_event["type"] == "token"


def test_unknown_message_shape_returns_clean_error():
    with TestClient(app) as client:
        app.state.llm_engine = FakeLLMEngine()
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
            ws.send_json({"type": "not_a_real_type", "content": "hi"})
            event = ws.receive_json()
            assert event["type"] == "error"
            assert event["code"] == "bad_request"


def test_empty_message_content_returns_error():
    with TestClient(app) as client:
        app.state.llm_engine = FakeLLMEngine()
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "   "})
            event = ws.receive_json()
            assert event["type"] == "error"
            assert event["code"] == "bad_request"


def test_overlong_message_content_returns_error_not_crash():
    with TestClient(app) as client:
        app.state.llm_engine = FakeLLMEngine()
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "x" * 5000})  # over the 2000-char cap
            event = ws.receive_json()
            assert event["type"] == "error"
            assert event["code"] == "bad_request"

            # socket must still be usable afterward
            ws.send_json({"type": "message", "content": "hello"})
            next_event = ws.receive_json()
            assert next_event["type"] == "token"


def test_llm_engine_failure_returns_clean_error_and_socket_survives():
    with TestClient(app) as client:
        app.state.llm_engine = FailingLLMEngine()
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "hi"})
            event = ws.receive_json()
            assert event["type"] == "error"
            assert event["code"] == "llm_error"

            # swap in a healthy engine and confirm the SAME socket keeps working
            app.state.llm_engine = FakeLLMEngine()
            ws.send_json({"type": "message", "content": "hi again"})
            event2 = ws.receive_json()
            assert event2["type"] == "token"


def test_mid_stream_disconnect_does_not_crash_server():
    with TestClient(app) as client:
        app.state.llm_engine = FakeLLMEngine(
            reply="This is a longer reply so we can disconnect partway through it",
            delay=0.02,
        )
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "tell me about your classes"})
            ws.receive_json()  # read exactly one token, then...
        # ...the `with` block exits here, closing the connection mid-stream.

        # The server process must still be alive and able to serve a fresh connection.
        with client.websocket_connect("/ws/chat") as ws2:
            event = ws2.receive_json()
            assert event["type"] == "session"
            ws2.send_json({"type": "message", "content": "hi"})
            token_event = ws2.receive_json()
            assert token_event["type"] == "token"


# --- Concurrency ---


def test_two_independent_sessions_do_not_interfere():
    with TestClient(app) as client:
        app.state.llm_engine = FakeLLMEngine(reply="Sure, I can help with that!")
        with client.websocket_connect("/ws/chat") as ws_a, client.websocket_connect(
            "/ws/chat"
        ) as ws_b:
            session_a = ws_a.receive_json()
            session_b = ws_b.receive_json()
            assert session_a["session_id"] != session_b["session_id"]

            ws_a.send_json({"type": "message", "content": "Book me into HIIT Blast"})
            ws_b.send_json({"type": "message", "content": "What do you charge for Premium?"})

            _drain_until_done(ws_a)
            _drain_until_done(ws_b)


def test_shared_session_id_across_two_connections_rejects_overlap():
    """
    Two connections opened against the SAME session_id (e.g. the same chat
    open in two browser tabs) must not be allowed to generate at the same
    time into shared history -- the second one gets a clean 'busy' error
    instead of corrupting the session.
    """
    with TestClient(app) as client:
        new_session = client.post("/session/new").json()
        sid = new_session["session_id"]

        app.state.llm_engine = FakeLLMEngine(
            reply="This reply is intentionally slow to create a race window",
            delay=0.1,
        )
        with client.websocket_connect(f"/ws/chat?session_id={sid}") as ws1, client.websocket_connect(
            f"/ws/chat?session_id={sid}"
        ) as ws2:
            assert ws1.receive_json()["session_id"] == sid
            assert ws2.receive_json()["session_id"] == sid

            ws1.send_json({"type": "message", "content": "Book me a trial session"})
            ws1.receive_json()  # make sure ws1's generation has actually started

            ws2.send_json({"type": "message", "content": "Freeze my membership"})
            busy_event = ws2.receive_json()
            assert busy_event["type"] == "error"
            assert busy_event["code"] == "busy"

            # ws1's own generation should still complete normally
            _drain_until_done(ws1)
