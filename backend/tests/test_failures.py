"""
Phase IV: failure handling. One explicit test per failure case:
  1. no relevant match (unrelated + gym-adjacent question)
  2. retrieval failure: Chroma folder missing, folder corrupted, embedding model error,
     retrieval timeout, empty index -- each must return "unavailable" (None) quickly,
     be logged, and lead to the "retrieval unavailable" note, never a crash or a hang
  3. context overflow: huge history + largest chunks + a 3,000-word / Urdu message
  4. extras: empty/whitespace message, Roman Urdu + Urdu script, and one client's
     failure not affecting another connected client
"""
import time

import pytest
from fastapi.testclient import TestClient

from app import conversation_manager as cm_module
from app.config import get_settings
from app.conversation_manager import (
    MAX_USER_TOKENS,
    SYSTEM_PROMPT,
    ConversationManager,
    count_tokens,
)
from app.llm_engine import GenerationStats, LLMEngineError
from app.main import app
from app.prompts import NO_MATCH_NOTE, RETRIEVAL_UNAVAILABLE_NOTE
from rag import retriever
from rag.index import run_index
from rag.store import DB_DIR, get_collection

_STATS = GenerationStats(time_to_first_token_s=0.0, total_time_s=0.0, completion_tokens=1)


@pytest.fixture
def real_retriever():
    """Model loaded up front (like the server's startup), and the retriever is always
    pointed back at the real index afterwards."""
    retriever.load(DB_DIR)
    retriever.clear_cache()
    yield
    retriever.clear_cache()
    retriever.load(DB_DIR)


async def context_for(text: str):
    cm = ConversationManager()
    return await cm.retrieve_context(cm.create_session(), text)


# ---------------------------------------------------------------- 1. no relevant match

@pytest.mark.parametrize("question", [
    "Who won the cricket World Cup?",      # clearly unrelated (top score ~0.17)
    "Do you have a basketball court?",     # gym-adjacent but not in the documents (~0.29)
])
async def test_no_match_returns_empty_list_and_no_match_note(real_retriever, question):
    chunks = await context_for(question)
    assert chunks == []  # retrieval WORKED, nothing relevant -> [] (not None)
    cm = ConversationManager()
    assert cm.build_prompt_messages(cm.create_session(), question, chunks)[-3]["content"] == NO_MATCH_NOTE


# ---------------------------------------------------------------- 2. retrieval failures

async def assert_unavailable(caplog, text="How much is the Plus plan?"):
    start = time.perf_counter()
    chunks = await context_for(text)
    assert chunks is None, "a failure must be reported as unavailable (None), not as no-match"
    assert time.perf_counter() - start < get_settings().retrieval_timeout_s + 1  # never hangs
    assert "Retrieval unavailable" in caplog.text  # the failure is logged


async def test_chroma_folder_missing(real_retriever, tmp_path, caplog):
    retriever._db_dir, retriever._collection = tmp_path / "does_not_exist", None
    await assert_unavailable(caplog)  # opens as an empty index -> RetrievalUnavailable


async def test_chroma_folder_corrupted(real_retriever, tmp_path, caplog):
    broken = tmp_path / "broken_db"
    broken.mkdir()
    (broken / "chroma.sqlite3").write_bytes(b"this is not a sqlite database" * 100)
    retriever._db_dir, retriever._collection = broken, None
    await assert_unavailable(caplog)


async def test_embedding_model_error(real_retriever, monkeypatch, caplog):
    def broken_embed(text):
        raise RuntimeError("embedding model crashed")
    monkeypatch.setattr(retriever, "_embed_query", broken_embed)
    await assert_unavailable(caplog)


async def test_retrieval_timeout(monkeypatch, caplog):
    monkeypatch.setattr(cm_module.retriever, "retrieve", lambda q: time.sleep(5))  # a stuck search
    await assert_unavailable(caplog)  # gives up after retrieval_timeout_s (2 s), doesn't wait 5 s


async def test_empty_index(real_retriever, tmp_path, caplog):
    docs, db = tmp_path / "docs", tmp_path / "db"
    docs.mkdir()
    run_index(docs, db)  # builds an index with 0 chunks
    retriever._db_dir, retriever._collection = db, None
    await assert_unavailable(caplog)


def test_failed_retrieval_uses_the_unavailable_note():
    cm = ConversationManager()
    messages = cm.build_prompt_messages(cm.create_session(), "How much is Plus?", None)
    assert messages[-3]["content"] == RETRIEVAL_UNAVAILABLE_NOTE
    assert "051-111-967-348" in RETRIEVAL_UNAVAILABLE_NOTE and "0333-5550967" in RETRIEVAL_UNAVAILABLE_NOTE


# ---------------------------------------------------------------- 3. context overflow

def largest_real_chunks(n=4):
    data = get_collection().get(include=["documents", "metadatas"])
    rows = sorted(zip(data["documents"], data["metadatas"]), key=lambda r: -len(r[0].split()))
    return [{"source": m["source"], "section": m["section"], "text": d, "score": 0.9} for d, m in rows[:n]]


@pytest.mark.parametrize("user_text", [
    "How do I freeze my plan? " + "Please explain everything in detail. " * 500,  # ~3,000 words
    "پلس پلان کی فیس کتنی ہے؟ " * 150,  # ~3,600 characters of Urdu script
], ids=["3000_english_words", "urdu_script"])
def test_overflow_never_exceeds_budget_and_keeps_system_prompt(user_text):
    settings = get_settings()
    cm = ConversationManager()
    session = cm.create_session()
    for i in range(6):  # the full sliding window, every message ~400 words
        cm.record_turn(session, f"question {i} " + "word " * 400, f"answer {i} " + "word " * 400)

    messages = cm.build_prompt_messages(session, user_text, largest_real_chunks())

    total = sum(count_tokens(m["content"]) for m in messages)
    assert total <= settings.num_ctx - settings.num_predict  # room for the reply is always left
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}  # never cut
    last = messages[-1]["content"]
    assert last.startswith(user_text[:20])  # the beginning of the question is kept...
    assert last.endswith("[message truncated: it was too long]")  # ...with a clear marker
    assert count_tokens(last) <= MAX_USER_TOKENS + 20


def test_largest_chunk_alone_fits_and_lower_ranked_are_dropped():
    cm = ConversationManager()
    chunks = largest_real_chunks()
    messages = cm.build_prompt_messages(cm.create_session(), "Tell me about discounts", chunks)
    context = messages[-3]["content"]
    assert f"[Source 1: {chunks[0]['source']}]" in context  # the best chunk always survives
    assert count_tokens(context) <= cm_module.CHUNK_TOKEN_BUDGET


# ---------------------------------------------------------------- 4. extras (WebSocket level)

class Engine:
    """Fake LLM: streams a fixed reply; raises for prompts containing 'CRASH'."""

    def __init__(self):
        self.prompts = []

    async def generate_with_stats(self, messages, **kwargs):
        return "ON_TOPIC", _STATS

    async def stream_chat(self, messages):
        self.prompts.append(messages)
        if "CRASH" in messages[-1]["content"]:
            raise LLMEngineError("model crashed for this request")
        for word in ("All ", "good."):
            yield word

    async def check_health(self):
        return True

    async def aclose(self):
        return None


def exchange(ws, text):
    ws.send_json({"type": "message", "content": text})
    events = []
    while True:
        events.append(ws.receive_json())
        if events[-1]["type"] in ("done", "error"):
            return events


@pytest.mark.parametrize("text", ["", "   ", "\n\t  "], ids=["empty", "spaces", "newline_tab"])
def test_empty_or_whitespace_message_gets_clean_error_and_socket_survives(text):
    with TestClient(app) as client:
        app.state.llm_engine = Engine()
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
            events = exchange(ws, text)
            assert events == [{"type": "error", "message": "Message content cannot be empty.",
                               "code": "bad_request"}]
            assert exchange(ws, "hello")[-1]["type"] == "done"  # still usable


def test_3000_word_message_gets_clear_too_long_error_and_socket_survives():
    with TestClient(app) as client:
        app.state.llm_engine = Engine()
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
            events = exchange(ws, "word " * 3000)
            assert events[-1]["type"] == "error" and events[-1]["code"] == "bad_request"
            assert "too long" in events[-1]["message"]
            assert exchange(ws, "hello")[-1]["type"] == "done"


@pytest.mark.parametrize("text", ["Plus plan ki fees kitni hai?", "پلس پلان کی فیس کتنی ہے؟"],
                         ids=["roman_urdu", "urdu_script"])
def test_roman_urdu_and_urdu_script_work_end_to_end(text):
    with TestClient(app) as client:
        app.state.llm_engine = engine = Engine()
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
            events = exchange(ws, text)
    assert [e["type"] for e in events] == ["token", "token", "done"]
    assert engine.prompts[-1][-1]["content"] == text  # the text reaches the model unchanged


def test_one_clients_failure_does_not_affect_another_client(monkeypatch):
    real_retrieve = retriever.retrieve

    def retrieve(query):  # retrieval breaks only for client A's message
        if "BOOM" in query:
            raise RuntimeError("vector store exploded")
        return real_retrieve(query)

    monkeypatch.setattr(cm_module.retriever, "retrieve", retrieve)
    with TestClient(app) as client:
        app.state.llm_engine = Engine()
        with client.websocket_connect("/ws/chat") as a, client.websocket_connect("/ws/chat") as b:
            a.receive_json()
            b.receive_json()
            # A: retrieval fails -> still a normal streamed answer (unavailable note in the prompt)
            assert exchange(a, "BOOM how much is Plus?")[-1]["type"] == "done"
            # A: the LLM fails -> a clean error event, the socket stays open
            assert exchange(a, "CRASH please")[-1]["type"] == "error"
            # B is completely unaffected and gets the normal stream
            assert [e["type"] for e in exchange(b, "How much is the Plus plan?")] == ["token", "token", "done"]
            # and A can carry on afterwards
            assert exchange(a, "hello again")[-1]["type"] == "done"
