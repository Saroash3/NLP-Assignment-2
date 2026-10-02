"""
Phase II tests: retrieval query for follow-ups, similarity threshold, prompt
format with source labels, and the context budget (drop lowest-ranked chunks
first, then oldest history; never exceed num_ctx). The retriever is faked, so
no model or index is needed.
"""
import pytest

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


@pytest.mark.parametrize("question", [
    "What is the guest fee?", "Is there a pool at F-7?", "Can students get a discount?",
    "How much is the Plus plan?", "Do you accept JazzCash?", "Who teaches Zumba?",
])
def test_short_complete_questions_are_embedded_alone(question):
    # Regression test for the live bug: short but COMPLETE questions were glued to the
    # previous, unrelated question and retrieved the wrong documents.
    cm = ConversationManager()
    session = cm.create_session()
    cm.record_turn(session, "Can I freeze my monthly plan for a week?", "…")
    assert cm.retrieval_query(session, question) == question


@pytest.mark.parametrize("follow_up", ["and for ladies?", "what about the Plus plan?", "who teaches it?",
                                       "for how many days?", "aur ladies ke liye?", "how much is that?"])
def test_real_follow_ups_are_still_merged(follow_up):
    cm = ConversationManager()
    session = cm.create_session()
    cm.record_turn(session, "What are the timings at the Bahria branch?", "…")
    assert cm.retrieval_query(session, follow_up).startswith("What are the timings at the Bahria branch?")


async def test_unrelated_message_never_borrows_the_previous_questions_documents(monkeypatch):
    # Regression test: "Who won the cricket World Cup?" right after a guest question must NOT be
    # answered with the guest policy (an earlier "retry merged" fallback did exactly that).
    queries = []

    def fake_retrieve(query):
        queries.append(query)
        score = 0.77 if "guest" in query else 0.17
        return [{"source": "policy_guest.md", "section": "", "text": "x", "score": score}]

    monkeypatch.setattr(cm_module.retriever, "retrieve", fake_retrieve)
    cm = ConversationManager()
    session = cm.create_session()
    cm.record_turn(session, "Can I bring a guest to G-11 on a weekday evening?", "No -- ...")
    for text in ("Who won the cricket World Cup?", "hi", "thanks!"):
        assert await cm.retrieve_context(session, text) == []  # embedded alone -> no match
    assert queries == ["Who won the cricket World Cup?", "hi", "thanks!"]


async def test_merged_retrieval_never_overrides_the_off_topic_classifier(monkeypatch):
    # A real follow-up form ("and ...") is merged for retrieval, but chunks found that way say
    # nothing about whether THIS message is on-topic, so they can't overrule the classifier.
    def fake_retrieve(query):
        score = 0.77 if "guest" in query else 0.17
        return [{"source": "policy_guest.md", "section": "", "text": "x", "score": score}]

    monkeypatch.setattr(cm_module.retriever, "retrieve", fake_retrieve)
    cm = ConversationManager()
    session = cm.create_session()
    cm.record_turn(session, "Can I bring a guest to G-11 on a weekday evening?", "No -- ...")
    chunks = await cm.retrieve_context(session, "and who won the World Cup?")
    assert chunks and chunks[0]["merged"]
    assert cm.apply_retrieval_override("redirect text", chunks) == "redirect text"  # stays off-topic
    own = [{"source": "branch_bahria_rawalpindi.md", "section": "", "text": "x", "score": 0.64}]
    assert cm.apply_retrieval_override("redirect text", own) is None  # its OWN strong match still overrides


def test_refusals_and_redirects_are_not_kept_in_history():
    cm = ConversationManager()
    session = cm.create_session()
    reply = "Our documents don't cover that. Please contact the front desk on WhatsApp."
    cm.record_turn(session, "Do you have a rig?", reply, remember=not cm.is_refusal(reply))
    cm.record_turn(session, "Who won the World Cup?", "That's outside my lane!", remember=False)
    assert len(session.history) == 0  # neither exchange is kept
    cm.record_turn(session, "How much is Plus?", "PKR 16,000 per month.",
                   remember=not cm.is_refusal("PKR 16,000 per month."))
    assert [m.content for m in session.history] == ["How much is Plus?", "PKR 16,000 per month."]


def test_prompt_tells_model_to_answer_no_with_reason_not_refuse():
    cm = ConversationManager()
    messages = cm.build_prompt_messages(cm.create_session(), "Can I get 25% off Elite?", [chunk("offer_student.md", 0.6)])
    context = messages[-3]["content"]
    assert 'answer "No"' in context and "ONLY if these sources are about something else entirely" in context


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
