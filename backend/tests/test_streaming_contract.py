"""
Phase III: the WebSocket streaming contract must be EXACTLY what Assignment 1
sent, whatever RAG does behind it:
  session {type, session_id, stage}  ->  token {type, content} x N  ->  done {type, stage}
with one token event per chunk the model yields, in order, and nothing else.
Checked for the three RAG paths: grounded answer, no-match, and classifier override.
The LLM and the retriever are faked, so no Ollama or index is needed.
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


@pytest.mark.parametrize(
    "path, verdict, score",
    [
        ("grounded", "ON_TOPIC", 0.62),  # chunks above the threshold
        ("no-match", "ON_TOPIC", 0.10),  # nothing passes the threshold
        ("override", "OFF_TOPIC", 0.70),  # classifier wrong, strong document match
    ],
)
def test_stream_matches_assignment_1_contract(monkeypatch, path, verdict, score):
    monkeypatch.setattr(cm_module.retriever, "retrieve", fake_chunks(score))
    with TestClient(app) as client:
        app.state.llm_engine = ScriptedEngine(verdict)
        events = run_one_message(client, "How much is the Plus plan?")

    types = [e["type"] for e in events]
    assert types == ["session"] + ["token"] * len(CHUNKS) + ["done"], f"{path}: {types}"
    for event in events:
        assert set(event) == A1_KEYS[event["type"]], f"{path}: extra/missing keys in {event}"
    # Token-by-token: each chunk from the model is forwarded as its own event, in order.
    assert [e["content"] for e in events if e["type"] == "token"] == CHUNKS
