# Zor Fitness Club — Nova Assistant (Assignment 2: RAG)

Nova is a fully local, streaming AI front-desk assistant for **Zor Fitness Club**, a fictional
gym with three branches in Islamabad and Rawalpindi. Assignment 1 built the conversational core
(FastAPI + WebSocket streaming + a local `qwen2.5:3b` via Ollama). **Assignment 2 adds
Retrieval-Augmented Generation (RAG):** before answering, Nova looks up the most relevant parts
of 80 gym documents and answers from them, citing the source file.

- **Local and CPU-friendly retrieval:** `all-MiniLM-L6-v2` embeddings on the CPU, Chroma on disk. No cloud APIs.
- **RAG only:** no tools or agents. One retrieval step per message, nothing else.
- **WebSocket contract unchanged** from Assignment 1 (proved by an automated test, see §7.4). The
  only addition is one **optional** `sources` field on `done`, for the visible-citations bonus (§5.5).
- The Assignment 1 README (use case, conversation stages, model selection) is kept in
  [docs/ASSIGNMENT1_README.md](docs/ASSIGNMENT1_README.md).

---

## Contents

1. [Quick start](#1-quick-start)
2. [Architecture](#2-architecture)
3. [Document collection](#3-document-collection)
4. [Indexing pipeline: chunking, embeddings, vector store](#4-indexing-pipeline)
5. [Retrieval, grounding and visible citations (bonus)](#5-retrieval-and-grounding)
6. [Context budget](#6-context-budget)
7. [Real-time behaviour: latency, caching, concurrency, streaming](#7-real-time-behaviour)
8. [Failure handling](#8-failure-handling)
9. [Evaluation](#9-evaluation)
10. [API reference](#10-api-reference)
11. [Testing](#11-testing)
12. [Known limitations](#12-known-limitations)
13. [Project structure](#13-project-structure)

---

## 1. Quick start

### Prerequisites
- **Python 3.11+** (developed on 3.14), **Node.js 18+**, and **[Ollama](https://ollama.com)**
- About 3 GB of disk space for the LLM, the embedding model and the Python packages

### 1.1 The LLM
```bash
ollama pull qwen2.5:3b
```

### 1.2 Backend + index
```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash;  .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                 # optional: every value has a default

python -m rag.index                  # build the vector index from ../documents (~25 s first time)
uvicorn app.main:app --port 8000
```
The first run downloads `all-MiniLM-L6-v2` (~90 MB) and the Qwen2.5 tokenizer (~7 MB) from
Hugging Face. After that everything runs offline.

### 1.3 Frontend
```bash
cd frontend
npm install
npm run dev                          # open http://localhost:5173
```

### 1.4 Updating the documents
Edit, add or delete files in `documents/`, then run `python -m rag.index` again from `backend/`.
Only changed files are re-embedded (see §4.4). A running server picks up the new index
automatically: its result cache is invalidated (§7.2), so no restart is needed.

### 1.5 Optional environment variables
| Variable | Where | Effect |
|---|---|---|
| `HF_HUB_OFFLINE=1` | backend shell | Skips Hugging Face's online update checks once the models are downloaded. Model + tokenizer loading went from **7.4 s to 0.8 s** on the test machine. Not hardcoded, because the first run needs the download. |
| `OLLAMA_NUM_PARALLEL=4` | Ollama's environment (Windows: `setx OLLAMA_NUM_PARALLEL 4`, then quit and restart Ollama) | Lets Ollama serve 4 requests at once instead of queueing them. It roughly halves the wait under load (§7.3). |
| `SIMILARITY_THRESHOLD`, `RETRIEVAL_TIMEOUT_S`, `NUM_CTX`, … | `backend/.env` | See [backend/app/config.py](backend/app/config.py). |

---

## 2. Architecture

```mermaid
flowchart LR
    UI["React UI<br/>(frontend/)"] <-- "WebSocket /ws/chat<br/>(unchanged contract)" --> API["FastAPI<br/>app/main.py"]
    API --> CM["Conversation Manager<br/>app/conversation_manager.py"]
    CM -- "1a. classify ON/OFF topic" --> LLM["Local LLM Engine<br/>Ollama qwen2.5:3b"]
    CM -- "1b. retrieve (in parallel,<br/>worker thread, 2 s timeout)" --> RET["Retrieval module<br/>rag/retriever.py<br/>LRU cache"]
    RET --> EMB["all-MiniLM-L6-v2<br/>(CPU)"]
    RET --> VDB[("Chroma<br/>rag/chroma_db")]
    CM -- "2. prompt = system + history<br/>+ SOURCES + question<br/>(token budget)" --> LLM
    LLM -- "3. token stream" --> API
    DOCS["documents/*.md<br/>(80 files)"] -- "offline: python -m rag.index<br/>chunk → embed → store" --> VDB
```

The same flow as the diagram in the assignment:
```
Web UI <--WebSocket--> FastAPI Backend <--> Conversation Manager <--> Local LLM Engine (Ollama)
                                                    |
                                                    +--> Retrieval Module (MiniLM embeddings + Chroma)
```

**One message, step by step** ([main.py](backend/app/main.py)):
1. The **off-topic classifier** (an LLM call from Assignment 1, ~350 ms) and **retrieval** (~10 ms,
   in a worker thread) run **at the same time** with `asyncio.gather`. Retrieval adds about 0 ms.
2. If the classifier says OFF_TOPIC but a document matches strongly (score ≥ 0.45), the
   documents win: the question is answered (§5.4). Otherwise an off-topic message gets the
   canned redirect, exactly as in Assignment 1.
3. The prompt is assembled within the token budget (§6), and the reply is streamed token by token.

---

## 3. Document collection

**80 Markdown documents** in [`documents/`](documents/), 250–500 words each, 36,000 words in total,
about the fictional **Zor Fitness Club** (F-7 Islamabad, G-11 Islamabad, Bahria Town Phase 7
Rawalpindi).

| Category | Docs | Examples |
|---|---|---|
| Membership and pricing | 10 | `plan_plus.md`, `pricing_prepaid_plans.md`, `instalments_and_late_fee.md` |
| Offers and joining | 9 | `offer_student.md`, `offer_ramadan_fit_pass.md`, `offer_azadi.md` |
| Branches and hours | 8 | `branch_bahria_rawalpindi.md`, `hours_ramadan.md`, `ladies_areas_overview.md` |
| Classes | 8 | `timetable_weekly_by_day.md`, `class_booking_rules.md`, `class_prenatal_yoga.md` |
| Trainers, staff and PT | 12 | `trainer_sana_iftikhar.md`, `staff_kamran_baig_nutrition.md` |
| Policies | 12 | `policy_freeze.md`, `policy_guest.md`, `policy_dress_code.md` |
| Facilities | 7 | `facility_pool.md`, `facility_kids_play_area.md` |
| FAQs (2 in Roman Urdu) | 8 | `faq_roman_urdu_fees_timings.md`, `faq_ladies.md` |
| Nutrition and wellness | 6 | `nutrition_sehri_iftar_tips.md`, `wellness_beginner_workout_guide.md` |

**How the documents were made**
1. **Research** ([`raw_sources/`](raw_sources/)): public pages of 14 Pakistani gyms and sources
   (Lahore, Islamabad, Rawalpindi, Karachi, Faisalabad), saved as short notes with their URLs. They
   covered price bands, admission fees, ladies' timings, freeze and refund rules, and guest
   policies. Failures are logged in [`_research_log.md`](raw_sources/_research_log.md).
2. **One source of truth** ([`facts_source_of_truth.md`](facts_source_of_truth.md)): the
   fictional gym's plans, PKR prices, branches, hours, 9 trainers, a 17-class timetable and all
   policies. It was built on the research *patterns* only; no real gym's facts are copied.
3. **Documents written from the facts file**, in our own words, with Pakistani context: PKR,
   separate ladies floors and hours, the Friday Jumu'ah break, Ramadan timings and the Ramadan
   Fit Pass, JazzCash and Easypaisa, and Roman Urdu FAQs. Each includes specific rules an LLM
   can't guess (e.g. "no guests at G-11 Mon–Fri 6–9pm", "PT is free if the trainer is more than
   10 minutes late").
4. **Consistency check** ([`eval/check_consistency.py`](eval/check_consistency.py)): every PKR
   amount and clock time in every document must appear in the facts file, and every document
   must be 250–500 words.

---

## 4. Indexing pipeline

[`backend/rag/index.py`](backend/rag/index.py) — run with `python -m rag.index [--samples 3]`.

### 4.1 Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- **Why:** small (~90 MB, 384-dimensional vectors), fast on a CPU (about 7 ms per query here),
  good quality for short English passages, and runs fully locally.
- **Trade-off:** it's an English model that only reads the **first 256 tokens** of a text.
  That limit decided our chunk size (§4.3).

### 4.2 Vector store: Chroma (persistent, on disk)
- **Why:** it runs locally, stores vectors **with metadata** (source file, chunk id, section,
  file hash) that we need for citations and incremental updates, persists to one folder, and
  needs no server. FAISS would need a separate metadata store and manual persistence.
- Cosine distance (`hnsw:space = cosine`), so the similarity score is `1 − distance`.
- We always pass our own vectors (`embedding_function=None`), so Chroma never downloads a model.

### 4.3 Chunking strategy and parameters
| Parameter | Value | Why |
|---|---|---|
| Split unit | Blocks at blank lines (paragraph, list or table) | Blocks are never cut mid-way, so a rule or a price row stays whole |
| Chunk size | **80–150 words** (`MIN_WORDS`, `MAX_WORDS`) | MiniLM only reads the first 256 tokens, and our Markdown averages 1.7 tokens per word. With 150–300-word chunks, **64%** of chunks were truncated when embedded; with 80–150 words + cleaning, 10% are. |
| Preferred cut | At a heading, once the chunk has ≥ 80 words | Keeps sections together |
| Overlap | The last short block (≤ 40 words) is repeated when a cut falls mid-section | Context isn't lost at the boundary |
| Prefix | Every chunk starts with `"<document title> > <nearest heading>"` | A chunk like "Late fee is PKR 1,500" still says which document and topic it belongs to |
| Tables | Each row becomes one line: `- Area: Ladies Wing; Mon–Sat: 8:00am–9:00pm; Sunday: Closed` | The 3B model misread grid tables (§12); one self-contained line per row fixed it |
| Embedding text | Markdown symbols (`**`, `\|`, `#`) removed before embedding only | Saves the 256-token budget; the LLM still sees the original text |

**Result:** 320 chunks from 80 documents, average 121 words (min 50, max 337). Most documents
give 3–5 chunks. A few very large tables stay whole on purpose and are over 150 words.

### 4.4 Re-runnable (incremental)
Each chunk stores the SHA-256 hash of its source file, plus a `CHUNKER_VERSION`. On every run:

| File state | Action |
|---|---|
| New | chunk + embed + add |
| Changed (different hash) | delete its old chunks, then chunk + embed + add |
| Deleted | delete its chunks |
| Unchanged | skip (the model isn't even loaded) |

Changing the chunking code means bumping `CHUNKER_VERSION`, which changes every hash and
re-indexes everything automatically. **Tested:** first run (80 added), a re-run with no changes
(80 unchanged, 0 embedding work), and a re-run after editing one file and deleting another
(1 updated, 1 removed, 78 untouched). See [tests/test_rag_index.py](backend/tests/test_rag_index.py).

---

## 5. Retrieval and grounding

### 5.1 Top-k and similarity threshold
- **k = 4** chunks per query (the assignment asks for at least 3).
- **Threshold = 0.35** (cosine similarity). Chunks below it are ignored. It was chosen from the
  score distribution of [`eval/test_questions.json`](eval/test_questions.json), which has 20
  answerable and 5 unanswerable questions:

| Group | Top-1 score |
|---|---|
| Answerable test questions (20) | 0.519 – 0.769 (an expected source is in the top-4 for **20/20**) |
| Off-topic (cricket, capital city, Python code) | 0.066 – 0.168 |
| Small talk ("hi", "thanks, bye") | 0.17 – 0.30 |
| Weakest answerable question seen ("Who is the head coach?") | 0.375 |
| Gym-related but **not covered** (BJJ/MMA, Lahore branch) | 0.506 – 0.520 |

0.35 sits above all off-topic and small-talk scores and below the weakest answerable one.
**Gym-related but uncovered questions can't be separated by score:** BJJ scores about the same as
real questions. So they're handled by the grounding prompt instead: *"if the sources don't
contain the answer, say our documents don't cover it."*
Reproduce the table with `backend/.venv/Scripts/python.exe eval/threshold_scores.py`.

### 5.2 Follow-up questions
"and for ladies?" means nothing on its own, since it scored only 0.31–0.36. **Rule:** a message is
embedded together with the previous user message **only if it looks like a follow-up**. That means
it's short (6 words or fewer) **and** it either starts with a connector ("and", "or", "what about",
"how about", "for", "aur"…) or refers back with a pronoun ("it", "that", "them"…). As a fallback,
a short message that finds nothing above the threshold on its own is retried once together with
the previous message (e.g. "ladies?"). Everything else, including short **complete** questions
like "What is the guest fee?", is embedded alone.

> **Bug found in live use and fixed.** The first version merged *every* message of 6 words or
> fewer with the previous one. In real mixed sessions, short complete questions got glued to
> unrelated earlier questions. "Is there a pool at F-7?" after a freeze question retrieved only
> freeze documents, so the model said "our documents don't cover that". Measured: 50% of merged
> queries failed, against 12% of the rest. See §9.4 for the full investigation and the before
> and after numbers.

### 5.3 Prompt template (the per-turn sources message)
```
[system]     persona + scope rules + conversation stages + grounding rules + short gym identity
             (the 3 branches, and the only 4 plans: Standard, Plus, Elite, Ladies Only)
[user/asst]  history (oldest trimmed first to fit the budget)
[system]     SOURCES -- excerpts from Zor Fitness Club's documents that best match the member's
             latest message, best match first. Use ONLY these for gym facts.
             [Source 1: plan_plus.md]
             Plus Membership Plan > Price
             ...chunk text...
             [Source 2: ...] ...
             Answer directly from these sources, with the specific facts. Tables: read each
             row on its own ... If a rule rules their case out, answer "No" + the reason. If
             they name something we don't have, say so and list what we do have. Say our
             documents don't cover that ONLY if the sources are about something else entirely.
             Don't mention file names -- the source line is added for you.
             (or the NO MATCH note / the RETRIEVAL UNAVAILABLE note, see §8)
[system]     scope reminder (Assignment 1 "sandwich")
[user]       latest message
```
- The Apex knowledge base from Assignment 1 was **removed** from the system prompt. Gym facts now
  come only from retrieved sources. That makes grounded answers genuinely different from
  ungrounded ones, and the system prompt shrank from about 2,300 to 1,559 tokens.
- The sources go **after** the history, so the system prompt + history stay identical from turn
  to turn and Ollama can reuse their cached computation.
- Grounding rules: every gym fact must come from SOURCES; never use facts about other gyms.
- **Referring back to the source:** every grounded answer ends with a short line such as
  `Sources: plan_plus.md, plan_comparison.md`. The **server** appends it as one final ordinary
  `token` event, because the 3B model put it at the start, the end, or nowhere when asked to
  write it itself. The line is kept out of the conversation history, so the model doesn't start
  copying it.

### 5.4 How retrieval fits with the Assignment 1 off-topic classifier
The classifier and retrieval run **in parallel**, so retrieval adds about 0 ms. The classifier
alone wrongly rejected real gym questions such as *"What are the timings at the Bahria branch?"*
(probably "Bahria" reads as a property company) and trainer names. **Override:** if the
classifier says OFF_TOPIC but the best chunk scores **≥ 0.45**, the question is answered from
the sources. Every clear off-topic message scored ≤ 0.32, so there is a 0.13 margin. The
off-topic battery improved while the off-topic catch rate stayed at 100% (§9.2). The classifier's
ON_TOPIC definition now also lists fees and payment methods (cash, card, JazzCash, Easypaisa),
after "Do you accept JazzCash?" was wrongly redirected in live testing (§9.4).

### 5.5 Visible citations in the chat UI (bonus)
When an answer was grounded, the chat shows the source documents as small chips under the
message:

![Citation chips in the chat](docs/citations_screenshot.png)

- **Wire format (backward-compatible):** one optional field on the existing `done` event, and
  nothing else changes:
  ```json
  { "type": "done", "stage": "information_gathering", "sources": ["plan_plus.md", "plan_comparison.md"] }
  ```
  The list holds the files of the chunks that were **actually in the prompt** after the token
  budget, deduplicated, best match first. When the answer was not grounded (no match, retrieval
  unavailable, off-topic redirect, or the reply itself says "our documents don't cover that"),
  the field is **omitted entirely**, so `done` is byte-for-byte Assignment 1's. An old frontend
  simply ignores the field.
- **Frontend:** `useChatSocket` attaches `sources` to the reply that just finished streaming;
  `MessageBubble` renders the chips (violet accent, fade-in) only when the list exists.
- **Tested:** `test_streaming_contract.py` checks the field's presence and values for grounded and
  override answers, its absence for no-match, retrieval failure and off-topic, deduplication, and
  the "don't cover" rule. It was also checked in a real browser with Playwright: 23 token frames
  gave 23 DOM updates (streaming unchanged), chips appeared for grounded answers and not for BJJ,
  and there were no page errors.

---

## 6. Context budget

Ollama was silently running `qwen2.5:3b` at **4,096 tokens** of context (checked with
`ollama ps`); anything longer is cut from the **front**, which means the system prompt goes
first. `num_ctx = 4096` is now set explicitly on every call. Tokens are counted with
**Qwen2.5's own tokenizer**, which matched Ollama's `prompt_eval_count` within about 1%
(3,388 vs 3,381 on the worst case).

| Part | Tokens | Rule |
|---|---|---|
| Reply space (`num_predict`) | **500** | always reserved |
| System prompt | **~1,559** | fixed, **never cut** |
| Scope reminder | **~92** | fixed |
| User message | actual, **max 1,000** | beginning kept, `…[message truncated]` marker added (matters for Urdu script) |
| Sources (chunks) | **≤ 1,200** | **lowest-ranked chunk dropped first** (4 chunks usually cost 930–1,180) |
| History | whatever is left: ~600–700 with 4 chunks, ~1,800 on no match | **oldest messages dropped first** |

A typical turn: 2,770 prompt tokens + 500 reply = 3,270 of 4,096.
The API still rejects messages over 2,000 characters, as in Assignment 1.

---

## 7. Real-time behaviour

**Test machine:** Windows 11, Intel i9-14900HX, 32 GB RAM, NVIDIA RTX 4080 Laptop (12 GB).
Ollama runs `qwen2.5:3b` (Q4_K_M) on the GPU; MiniLM and Chroma run on the CPU.

### 7.1 Retrieval latency (target < 1 s)
`cd backend && python -m rag.benchmark` (25 test questions, warm rows = 3 rounds = 75 samples):

| Retrieval only | Samples | Avg ms | Median ms | p95 ms |
|---|---|---|---|---|
| Cold start: load model + open index (once, at server startup) | 1 | 8,112 | – | – |
| Cold: first query after loading | 1 | 34.1 | – | – |
| Warm, cache miss: embed query | 75 | 7.40 | 7.59 | 8.53 |
| Warm, cache miss: vector search | 75 | 1.91 | 1.93 | 2.17 |
| **Warm, cache miss: total retrieval** | 75 | **9.38** | **9.57** | **10.44** |
| **Warm, cache hit** | 75 | **0.04** | **0.03** | **0.05** |

| End-to-end, same code path as the server (20 answerable questions) | Samples | Avg ms | Median ms | p95 ms |
|---|---|---|---|---|
| Retrieval (in parallel with the classifier) | 20 | 9.93 | 9.91 | 11.63 |
| Off-topic classifier (LLM call) | 20 | 354 | 345 | 353 |
| **Time to first token** | 20 | 932 | **807** | 838 |
| **Total reply time** | 20 | 1,304 | **1,118** | 1,515 |

- **Retrieval takes about 9–10 ms (about 100× under the 1 s target) and is 0.8% of the total reply time.**
  It overlaps the classifier call, so it adds about 0 ms before the first token.
- The average time to first token is above the p95 because of **one** request: the first one
  after loading (~3.2 s), when Ollama processes the whole system prompt for the first time. After
  that, the unchanged prefix is reused, which is why the sources go last in the prompt.
- The cold start happens once, at server startup (§1.5 cuts it with `HF_HUB_OFFLINE`).

### 7.2 Caching
Two LRU caches in [`rag/retriever.py`](backend/rag/retriever.py), both keyed on the **final text
that is embedded** (after the follow-up rule):
- `query text → embedding` (512 entries): depends only on the model, so it stays valid when
  documents change.
- `(query text, k, index version) → top-k chunks` (256 entries). `python -m rag.index` updates an
  `index_version.txt` marker whenever anything changed; the retriever reads its timestamp (one
  `stat()` call) on every request. After a re-index, old entries can never match, so **stale
  chunks are never served**, even to an already running server. Tested in
  [tests/test_rag_cache.py](backend/tests/test_rag_cache.py): a PKR 1,000 → 1,500 edit is picked up.
- A cache hit costs 0.04 ms, compared with 9.4 ms for a miss.

### 7.3 Concurrency
Retrieval runs in a worker thread (`asyncio.to_thread`), and the model loads once at startup,
so the server's event loop is never blocked. Measured with
[`eval/concurrency_test.py`](eval/concurrency_test.py) (N simultaneous WebSocket clients, each
asking a different question, timed from sending the message; a probe calls the server during
the run):

| | `OLLAMA_NUM_PARALLEL=1` (default) | `OLLAMA_NUM_PARALLEL=4` |
|---|---|---|
| Single user, time to first token (median) | 0.82 s | 0.83 s |
| 5 clients: time to first token median / max | 1.54 / 2.54 s | **0.92 / 1.31 s** |
| 10 clients: time to first token median / max | 3.17 / 5.37 s | **1.75 / 2.95 s** |
| 10 clients: all replies finished | 5.59 s | **3.64 s** |
| `POST /session/new` during the load (our server only) | ~3 ms | ~1–3 ms |
| Ollama memory | 2.2 GB | 2.7 GB |

**Honest reading:** the server stays responsive (`/session/new` in a few ms while 10 clients
wait), but **Ollama queues generation calls**. With the default `OLLAMA_NUM_PARALLEL=1`, each
extra client waits about 0.45 s longer, because every message makes 2 LLM calls (classifier +
reply). `OLLAMA_NUM_PARALLEL=4` cuts the worst wait by 45% for 0.5 GB more memory, and
single-user speed is unchanged. It's set on the test machine (§1.5).

### 7.4 Streaming is unchanged from Assignment 1
[tests/test_streaming_contract.py](backend/tests/test_streaming_contract.py) checks three paths
(grounded answer, no match, classifier override):
- the event order is `session → token × N → done`;
- every event has **exactly** Assignment 1's fields (`schemas.py` is unchanged);
- there is **one `token` event per chunk the model yields, in order**.

A real run (before the citations bonus was added):
```
0.000s <- {"type":"session","session_id":"94fb…","stage":"greeting"}
0.000s -> {"type": "message", "content": "Is there a sauna at the Bahria branch?"}
1.174s <- {"type":"token","content":"(source"}
1.184s <- {"type":"token","content":":"}
   … 25 token events, ~8 ms apart …
1.367s <- {"type":"done","stage":"information_gathering"}
```
With citations, a grounded answer ends with one extra `token` (`"\n\nSources: …"`) and `done`
carries the optional `sources` list (§5.5).

---

## 8. Failure handling

Every case is covered by [tests/test_failures.py](backend/tests/test_failures.py) and was
also checked by hand against the running server.

### 8.1 No relevant match
Retrieval works, but no chunk scores ≥ 0.35. The model gets the **NO MATCH** note: *"say our
documents don't cover that, suggest the front desk on WhatsApp, never guess a Zor fact; answer
greetings, small talk and general fitness normally."* Real reply to *"Do you have a CrossFit box
with a rig?"* (top score 0.309): **"Our documents don't cover that. You can check with the
front desk on WhatsApp (0333-5550967)."** (3/3 runs, with `OLLAMA_NUM_PARALLEL=1`; since switching
to 4 parallel slots the classifier redirects this question as off-topic instead, which is also
acceptable). No citations are sent. Counter-example: see limitation 12 (a "yes" guessed for an
equipment question).

### 8.2 Embedding or vector store failure, or timeout
Tested cases:
- the Chroma folder missing;
- the Chroma folder corrupted;
- the embedding model raising an error;
- a search stuck longer than 2 s;
- an empty index.

For each, `retrieve_context()` returns **`None` ("unavailable") within the 2 s timeout**, the
error is **logged** (`WARNING … Retrieval unavailable (RetrievalUnavailable: the index is empty
-- run python -m rag.index); replying without documents`), and the reply still streams normally.

The Apex knowledge base is gone, so in this mode the model has **no** gym facts. It gets the
**RETRIEVAL UNAVAILABLE** note: *"don't state or guess any price, time or policy; say you can't
look that up right now; point to UAN 051-111-967-348, WhatsApp 0333-5550967 or any branch
reception."*

Real reply with the index folder removed, to *"How much is the Plus membership per month?"*:
**"Sorry, I can't look that up right now. Please contact our front desk: UAN 051-111-967-348,
WhatsApp 0333-5550967, or any branch reception."** (3/3 runs). Small talk is still answered
normally. See §12 for the limitation with action requests such as freezing.

### 8.3 Context overflow
The budget in §6 guarantees the prompt always fits. The worst case was tested with the real LLM:
12 history messages (~5,300 words), the 4 largest chunks (up to 337 words) and a 3,000-word
question.
- **Prompt:** 3,388 tokens (Ollama counted 3,381) + 500 reply reserve = 3,888 ≤ 4,096. Ollama's
  log shows `truncated = 0`.
- **System prompt:** intact.
- **Question:** its beginning was kept (995 tokens) with a truncation marker.
- **Sources:** the best one was kept.
- **History:** dropped, oldest first; in this extreme case that meant all of it.

Over the WebSocket, a message over 2,000 characters gets a clear `error` event, *"That message is
too long (the limit is 2,000 characters)…"*, and the connection stays usable.

### 8.4 Other checks
- **Empty or whitespace-only messages:** a clean `bad_request` error, and the connection survives.
- **Roman Urdu and Urdu script:** both answered. "Plus plan ki fees kitni hai?" gets
  "PKR 16,000 hai" (source: `faq_roman_urdu_fees_timings.md`). Urdu script also retrieved the
  right FAQ, with a thin margin (0.416).
- **One client failing while others are connected:** one client's retrieval failure and one
  client's model crash leave the other client's stream untouched (automated test).

---

## 9. Evaluation

### 9.1 Test questions
[`eval/test_questions.json`](eval/test_questions.json) has 25 questions with their expected
source files, including 5 that the documents can't answer. Retrieval **recall@4 = 20/20**: an
expected source is in the top-4 for every answerable question.

### 9.2 Off-topic battery (Assignment 1), before and after RAG
[`evaluation/off_topic_battery.py`](evaluation/off_topic_battery.py), 30 fixed messages:

| | Assignment 1 (classifier only, KB in prompt) | Assignment 2 (KB removed, classifier + retrieval override) |
|---|---|---|
| **Clearly off-topic caught** | **10/10** | **10/10** |
| Clearly on-topic | 9/10 | 10/10 |
| Ambiguous | 5/10 | 7/10 |
| Overall | 24/30 (80%) | 27/30 (90%) |

### 9.4 Live multi-turn sessions: the refusal bug, and the before/after numbers
**Symptom:** in a live chat session, simple questions the documents answer ("How much is the Plus
plan?", "Can students get a discount?", "What is the guest fee?", "Is there a pool at F-7?") were
answered with *"Our documents don't cover that"*, one after another, with no chips. The same
questions had worked when asked one at a time.

**Investigation.** [`eval/live_session_eval.py`](eval/live_session_eval.py) replays realistic
sessions through the real WebSocket:
- the 20 answerable test questions plus 15 new realistic ones, several of them "trick" questions
  whose correct answer is a rule-based **no** (e.g. "I'm a student, can I get 25% off Elite at 8pm?");
- mixed with controls (BJJ, Lahore, off-topic, small talk);
- shuffled into sessions of 10 messages, 3 runs with different orders.

It records each reply's refusal or correctness, and joins it with the server log's embedded query,
scores and files. That showed **three separate causes**:

| # | Root cause | Evidence | Fix |
|---|---|---|---|
| 1 | **Follow-up rule merged complete short questions with the previous, unrelated message** | 32/105 queries were merged, and **50%** of them failed vs **12%** of the rest. "Do you accept JazzCash?" after a dress-code question retrieved dress-code files. "How much is the Plus plan?" after a kids'-area question gave the *family* price, PKR 13,600. | Merge only messages that look like follow-ups (§5.2) |
| 2 | **The prompt's "documents don't cover that" escape hatch** | With an **empty** history and the right source ranked first ("Is the admission fee waived on 6 months?" → `admission_fee.md`), the model still refused 3/3. Nothing told it how to answer when a rule says *no*. | Prompt: answer directly; if a rule excludes the case, say **"No" + the reason**; if they name something we don't have, say so and list what we have; "don't cover" **only** when the sources are about something else |
| 3 | **Earlier refusals in the history were copied** | With 2 refusals already in the history, "my friend did a free trial, can he come as a guest?" went from answered (2/3) to **refused 3/3** | Refused or redirected exchanges are no longer kept in the model's history (the stage badge still updates) |
| + | The classifier didn't list **payments** as on-topic | "Do you accept JazzCash?" was redirected 3/3 (retrieval 0.403, just under the 0.45 override) | Payment methods added to the classifier's ON_TOPIC definition (off-topic battery re-run: still **10/10**) |
| + | An invented "Platinum plan" price | Asked about a plan that doesn't exist, the model sometimes made up a price | The plan names are now in the 2-line gym identity: "Standard, Plus, Elite, Ladies Only, no other plans" |

**Results:** 3 runs × 35 answerable questions = 105 replies, scored by the same rules before and after:

| | Before | After |
|---|---|---|
| **Refusals on answerable questions** | **15/105 (14.3%)** | **0/105 (0%)** |
| **Correct answers** | 82/105 (78.1%) | **104/105 (99.0%)** |
| Answers with citation chips | 91/105 | 105/105 |
| BJJ / Lahore / off-topic / small-talk controls | 2/3 · 3/3 · 6/6 · 3/3 | 3/3 · 3/3 · 6/6 · 3/3 |
| Off-topic battery (classifier) | 10/10 off-topic caught | 10/10 off-topic caught |

The one remaining wrong answer is an invented Platinum price (limitation 14). The raw replies are in
`eval/live_session_before.json` and `eval/live_session_after_final.json`.

**One visible behaviour change:** questions about things we don't offer now get a grounded "No",
e.g. *"No -- We don't offer Brazilian Jiu-Jitsu or MMA classes at Zor Fitness Club"* (with the
class-list documents as chips), instead of "our documents don't cover that". Nothing is invented.

### 9.3 End-to-end examples (real replies over the WebSocket, final version)
| Question | Nova | Citation chips (`done.sources`) |
|---|---|---|
| How much is the Plus membership per month? | "The Plus membership plan costs PKR 16,000 per month at Zor Fitness Club.<br>Sources: plan_plus.md, plan_comparison.md" | plan_plus.md, plan_comparison.md |
| What are the timings at the Bahria branch? *(classifier said OFF_TOPIC; override at 0.642)* | "…6:00 AM to midnight on weekdays, and from 10:00 AM to 8:00 PM on Sundays… only the Ladies Wing is closed." | branch_bahria_rawalpindi.md, hours_all_branches.md |
| → "and for ladies?" *(follow-up)* | "…the Ladies Wing is open from 8:00 AM to 9:00 PM on weekdays, and it is closed on Sundays." | branch_bahria_rawalpindi.md, faq_ladies.md, hours_all_branches.md |
| Do you offer Brazilian jiu-jitsu or MMA classes? | "No -- We don't offer Brazilian Jiu-Jitsu or MMA classes at Zor Fitness Club." | faq_classes_and_trainers.md, timetable_weekly_by_day.md, classes_ladies.md |
| Can I bring a guest to G-11 on a weekday evening? | "No -- guests are not allowed at G-11 Monday to Friday, 6:00–9:00pm." | policy_guest.md, classes_functional_zor_circuit.md |
| Do you have a CrossFit box with a rig? | *(off-topic redirect from the classifier)* | *(none)* |

Reproduce with `backend/.venv/Scripts/python.exe eval/e2e_examples.py` while the backend is running.

---

## 10. API reference

Unchanged from Assignment 1, except for **one optional field** on `done` (citations bonus).

**REST:** `GET /health` → `{status, model, ollama_reachable, active_sessions}` ·
`POST /session/new` → `{session_id, stage}`

**WebSocket `/ws/chat`** (optionally `?session_id=<id>` to resume):
```json
// client -> server
{ "type": "message", "content": "What classes do you have on Tuesdays?" }
{ "type": "reset" }
// server -> client
{ "type": "session", "session_id": "...", "stage": "greeting" }
{ "type": "token", "content": "Hi" }
{ "type": "done", "stage": "information_gathering" }
{ "type": "done", "stage": "information_gathering", "sources": ["plan_plus.md", "plan_comparison.md"] }
{ "type": "error", "message": "...", "code": "bad_request" | "busy" | "llm_error" | "internal_error" }
```
- **`sources` (optional, new in Assignment 2):** the source documents the answer was grounded in,
  deduplicated, best match first. It is present **only** when the answer was grounded and is
  omitted otherwise (not `null`, not `[]`). Clients that don't know it can ignore it.
- A grounded answer's last `token` is a short `"\n\nSource(s): …"` line added by the server.
- A message over 2,000 characters gets `error` with code `bad_request` and the text *"That message is
  too long (the limit is 2,000 characters)…"*.

---

## 11. Testing

```bash
cd backend && python -m pytest -q        # 86 tests, about 1.5 minutes, no Ollama needed
```
| File | What it covers |
|---|---|
| `test_conversation_manager.py`, `test_llm_engine.py`, `test_websocket.py` | Assignment 1 (still passing) |
| `test_rag_index.py` | chunking rules, heading prefix, incremental add, update and delete |
| `test_rag_prompt.py` | follow-up rule (complete short questions embedded alone, real follow-ups merged, fallback), refusals kept out of history, "No + reason" prompt rule, threshold, source labels, budget |
| `test_rag_cache.py` | cache hits, re-index invalidation, cached results returned as copies |
| `test_streaming_contract.py` | WebSocket events identical to Assignment 1 in all RAG paths; the optional `sources` field only when grounded |
| `test_failures.py` | all Phase IV failure cases (§8) |

Evaluation scripts (need Ollama running; the WebSocket ones also need the backend):
`python -m rag.benchmark`, `eval/threshold_scores.py`, `eval/e2e_examples.py`, `eval/live_session_eval.py`,
`eval/concurrency_test.py`, `evaluation/off_topic_battery.py`, and `eval/check_consistency.py`
(which only checks the documents).

---

## 12. Known limitations

1. **The 3B model sometimes misreads correct sources.** Retrieval is 20/20, but the answer can
   still be wrong:
   - the Bahria hours table ("closed on Sundays" for the whole branch) was fixed by
     linearizing tables and adding one explicit sentence (3/5 → 5/5);
   - a Roman Urdu FAQ sentence mixing Standard and Plus prices was fixed by splitting it per
     plan (0/3 → 3/3);
   - under the extreme overflow test, it said "student discount on all plans" (it's Standard and
     Plus only) and missed the "only one discount at a time" rule in its own source.

   Fixes were made in the data. Similar slips can still happen elsewhere.
2. **With retrieval down, action requests aren't fully safe.** The price question gets the "can't
   look that up" reply 3/3, but "Can I freeze my 6-month plan?" got "Sure, I can help… confirm
   your membership number" in 2 of 3 runs. It invents no facts, but it pretends it can act. The
   Assignment 1 stage guide ("walk through freezing") wins over the per-turn note. A fixed reply
   whenever retrieval fails would guarantee safety but would also block small talk.
3. **Gym-related but uncovered questions pass the threshold** (BJJ 0.520 vs the weakest real
   question 0.519). The prompt now makes the model answer with a grounded "No -- we don't offer
   that" (§9.4). That depends on the model following the instruction (3/3 in testing).
4. **The classifier still misfires** on small talk and on Wi-Fi or bicycle-parking questions (score
   too low for the override). When retrieval is down, the override can't help at all.
5. **English embedding model:** Urdu script works only by a thin margin (0.416 vs 0.35). The model
   also once slipped a Cyrillic letter into an Urdu reply.
6. **Citations are per retrieved file, not per sentence.** The chips and the "Sources:" line list
   every file whose chunks were in the prompt, e.g. `classes_functional_zor_circuit.md` next to
   `policy_guest.md` for the guest question, even if the answer used only one of them. (The
   model placing "(source: …)" randomly was fixed by having the server add the line.)
7. **Truncated embeddings:** 10% of chunks (whole tables or rule lists) are longer than MiniLM's
   256 tokens, so their ends are invisible to retrieval. The LLM still sees the full chunk.
8. **Ollama concurrency:** calls are queued unless `OLLAMA_NUM_PARALLEL` > 1. Even then, each
   message costs 2 LLM calls.
9. **In the extreme overflow case, all history is dropped** (the oldest-first rule) to keep the
   question and the best source.
10. **Sessions and the cache live in memory:** a server restart forgets conversations.
11. **Fictional data:** prices and rules are realistic for Pakistan in 2026 but invented. Contact
    numbers are fictional.
12. **The no-match path can still produce a guessed "yes".** *"Is there a treadmill with an
    incline?"* scored 0.33 (below the threshold), and the model replied *"Sure, we have treadmills
    with incline settings"* despite the no-match note. That's plausible, but it's not in the
    documents. Questions about common gym equipment are most at risk.
13. **The classifier's verdicts shift slightly with `OLLAMA_NUM_PARALLEL`.** With 4 parallel slots,
    *"Do you have a CrossFit box with a rig?"* is redirected as off-topic, where it passed before.
    That's the classifier being non-deterministic under parallel batching, not a retrieval issue.
14. **Invented details for things that don't exist.** In the live evaluation, 1 of 105 answers
    gave a made-up price for a non-existent "Platinum" plan, even though the prompt lists the only
    four plans. Every other answer (104/105) was correct (§9.4).

---

## 13. Project structure

```
documents/                 80 gym documents (the corpus)
raw_sources/               research notes from public Pakistani gym pages + _research_log.md
facts_source_of_truth.md   the fictional gym's facts; every document must match it
backend/
  app/                     FastAPI app, conversation manager (RAG integration, budget), prompts, LLM engine
  rag/
    store.py               paths, embedding model, Chroma, index version marker
    index.py               offline indexing pipeline (python -m rag.index)
    retriever.py           retrieve(query) + LRU caches
    benchmark.py           latency benchmark (python -m rag.benchmark)
    chroma_db/             the vector index (git-ignored; rebuilt by rag.index)
  tests/                   86 tests
eval/                      test questions, threshold scores, e2e examples, concurrency test, consistency check
evaluation/                Assignment 1 off-topic battery (+ results.md with before/after runs)
frontend/                  React + Vite UI
docs/                      Assignment 1 README and testing notes
VIVA_NOTES.md              design decisions in plain words + the prompts used
```
