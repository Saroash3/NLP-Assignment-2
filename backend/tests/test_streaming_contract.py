"""
Phase III: the WebSocket streaming contract must be EXACTLY what Assignment 1
sent, whatever RAG does behind it:
  session {type, session_id, stage}  ->  token {type, content} x N  ->  done {type, stage}
with one token event per chunk the model yields, in order, and nothing else.
The ONLY addition allowed is the optional `sources` list on `done` (citations bonus),
present only when the answer was grounded.
Checked for the RAG paths: grounded answer, no-match, classifier override, retrieval
failure and off-topic redirect. The LLM and the retriever are faked, so no Ollama or
index is needed.
"""
import pytest
from fastapi.testclient import TestClient

from app import conversation_manager as cm_module
from app.llm_engine import GenerationStats
from app.main import app

# The exact key sets Assignment 1 sent (see app/schemas.py at the Assignment 1 commit).
A1_KEYS = {
    "session": {"type", "session_id", "stage"},
    "token": {"type", "content"},
    "done": {"type", "stage"},
}
CHUNKS = ["The ", "Plus ", "plan ", "is ", "PKR ", "16,000 ", "per ", "month."]
_STATS = GenerationStats(time_to_first_token_s=0.0, total_time_s=0.0, completion_tokens=1)


class ScriptedEngine:
    """Yields a fixed list of chunks; classifier verdict is configurable."""

    def __init__(self, verdict: str = "ON_TOPIC"):
        self.verdict = verdict

    async def generate_with_stats(self, messages, **kwargs):
        return self.verdict, _STATS

    async def stream_chat(self, messages):
        for chunk in CHUNKS:
            yield chunk

    async def check_health(self):
        return True

    async def aclose(self):
        return None


def fake_chunks(score: float):
    return lambda query: [{"source": "plan_plus.md", "section": "", "text": "Plus: PKR 16,000", "score": score}]


def run_one_message(client, text: str) -> list[dict]:
    """Connect, send one message, return every event received (session ... done)."""
    events = []
    with client.websocket_connect("/ws/chat") as ws:
        events.append(ws.receive_json())
        ws.send_json({"type": "message", "content": text})
        while True:
            events.append(ws.receive_json())
            if events[-1]["type"] in ("done", "error"):
                return events


def failing_retrieve(query):
    raise RuntimeError("vector store down")


@pytest.mark.parametrize(
    "path, verdict, retrieve, expected_sources",
    [
        ("grounded", "ON_TOPIC", fake_chunks(0.62), ["plan_plus.md"]),  # above the threshold
        ("override", "OFF_TOPIC", fake_chunks(0.70), ["plan_plus.md"]),  # strong doc match wins
        ("no-match", "ON_TOPIC", fake_chunks(0.10), None),  # nothing passes the threshold
        ("retrieval failed", "ON_TOPIC", failing_retrieve, None),  # unavailable note, no sources
    ],
)
def test_stream_matches_assignment_1_contract(monkeypatch, path, verdict, retrieve, expected_sources):
    monkeypatch.setattr(cm_module.retriever, "retrieve", retrieve)
    with TestClient(app) as client:
        app.state.llm_engine = ScriptedEngine(verdict)
        events = run_one_message(client, "How much is the Plus plan?")

    # Grounded answers end with ONE extra ordinary token: the server-added "Source: ..." line.
    expected_tokens = CHUNKS + (["\n\nSource: plan_plus.md"] if expected_sources else [])
    types = [e["type"] for e in events]
    assert types == ["session"] + ["token"] * len(expected_tokens) + ["done"], f"{path}: {types}"
    for event in events[:-1]:
        assert set(event) == A1_KEYS[event["type"]], f"{path}: extra/missing keys in {event}"
    done = events[-1]
    # `done` is Assignment 1's event plus, only when grounded, the one optional `sources` field.
    assert set(done) - {"sources"} == A1_KEYS["done"], f"{path}: unexpected keys in {done}"
    assert done.get("sources") == expected_sources, f"{path}: {done}"
    # Token-by-token: each chunk from the model is forwarded as its own event, in order.
    assert [e["content"] for e in events if e["type"] == "token"] == expected_tokens


def test_off_topic_redirect_has_no_sources(monkeypatch):
    monkeypatch.setattr(cm_module.retriever, "retrieve", fake_chunks(0.20))  # weak: no override
    with TestClient(app) as client:
        app.state.llm_engine = ScriptedEngine("OFF_TOPIC")
        done = run_one_message(client, "Who won the cricket World Cup?")[-1]
    assert done["type"] == "done" and "sources" not in done


def test_citations_are_deduplicated_and_dropped_when_reply_says_not_covered():
    from app.conversation_manager import ConversationManager

    cm = ConversationManager()
    chunks = [{"source": s, "section": "", "text": "x", "score": 0.6}
              for s in ("plan_plus.md", "plan_plus.md", "plan_comparison.md")]
    _, used = cm.build_prompt(cm.create_session(), "How much is Plus?", chunks)
    assert used == ["plan_plus.md", "plan_comparison.md"]  # deduplicated, best first
    assert cm.citations_for(used, "Plus is PKR 16,000.\nSource: plan_plus.md") == used
    assert cm.citations_for(used, "Our documents don't cover that. Try WhatsApp.") is None
    assert cm.citations_for([], "anything") is None
