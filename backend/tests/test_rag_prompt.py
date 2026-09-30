"""
Phase II tests: retrieval query for follow-ups, similarity threshold, prompt
format with source labels, and the context budget (drop lowest-ranked chunks
first, then oldest history; never exceed num_ctx). The retriever is faked, so
no model or index is needed.
"""
from app import conversation_manager as cm_module
from app.config import get_settings
from app.conversation_manager import CHUNK_TOKEN_BUDGET, ConversationManager, count_tokens
from app.prompts import NO_MATCH_NOTE


def chunk(source, score, words=20):
    return {"source": source, "section": "", "score": score, "text": f"{source} " + "fact " * words}


def test_short_follow_up_is_embedded_with_previous_user_message():
    cm = ConversationManager()
    session = cm.create_session()
    cm.record_turn(session, "What are the timings at the Bahria branch?", "…")
    assert cm.retrieval_query(session, "and for ladies?") == \
        "What are the timings at the Bahria branch? and for ladies?"


def test_long_new_question_is_embedded_alone():
    cm = ConversationManager()
    session = cm.create_session()
    cm.record_turn(session, "What are the Ramadan timings?", "…")
    question = "Is there a sauna at the Bahria branch please?"
    assert cm.retrieval_query(session, question) == question


async def test_chunks_below_threshold_are_dropped(monkeypatch):
    fake = [chunk("good.md", 0.62), chunk("weak.md", 0.20)]
    monkeypatch.setattr(cm_module.retriever, "retrieve", lambda q: fake)
    cm = ConversationManager()
    result = await cm.retrieve_context(cm.create_session(), "How much is Plus?")
    assert [c["source"] for c in result] == ["good.md"]


def test_sources_are_labelled_and_placed_right_before_the_question():
    cm = ConversationManager()
    session = cm.create_session()
    messages = cm.build_prompt_messages(session, "How much is Plus?", [chunk("plan_plus.md", 0.6)])
    context = messages[-3]["content"]
    assert "[Source 1: plan_plus.md]" in context
    assert messages[-1] == {"role": "user", "content": "How much is Plus?"}


def test_no_chunks_gives_the_no_match_note():
    cm = ConversationManager()
    messages = cm.build_prompt_messages(cm.create_session(), "Do you offer MMA?", [])
    assert messages[-3]["content"] == NO_MATCH_NOTE


def test_lowest_ranked_chunks_are_dropped_to_fit_the_chunk_budget():
    cm = ConversationManager()
    big = [chunk(f"doc{i}.md", 0.9 - i * 0.1, words=300) for i in range(4)]  # ~4 x 300+ tokens
    kept = cm.select_chunks(big, CHUNK_TOKEN_BUDGET)
    assert 0 < len(kept) < 4
    assert [c["source"] for c in kept] == [f"doc{i}.md" for i in range(len(kept))]  # best first


def test_oldest_history_is_trimmed_and_prompt_fits_num_ctx():
    settings = get_settings()
    cm = ConversationManager()
    session = cm.create_session()
    for i in range(6):  # 6 long exchanges: far more than the history budget
        cm.record_turn(session, f"question {i} " + "word " * 150, f"answer {i} " + "word " * 150)
    chunks = [chunk(f"doc{i}.md", 0.8, words=120) for i in range(4)]

    messages = cm.build_prompt_messages(session, "What about Elite?", chunks)
    total = sum(count_tokens(m["content"]) for m in messages)
    assert total <= settings.num_ctx - settings.num_predict

    history = [m["content"] for m in messages[1:-3]]
    assert len(history) < 12  # some history was trimmed...
    assert history[-1].startswith("answer 5")  # ...and the newest turn survived (oldest went first)
