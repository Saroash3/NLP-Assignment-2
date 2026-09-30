# Viva Notes: Assignment 2 (RAG)

Plain-language explanations of every design decision, the exact prompts the model receives,
the prompts used with the AI coding assistant, and likely viva questions with short answers.
Numbers come from the README (measured on the test machine).

---

## 1. The whole system in one paragraph

A member types a question in the React chat. It goes over the **same WebSocket as Assignment 1**
to FastAPI. Two things then happen **at the same time**: a small LLM call decides whether the
message is gym-related (Assignment 1's classifier), and the **retriever** turns the question into
a vector with MiniLM and finds the 4 most similar chunks of our 80 gym documents in Chroma
(~10 ms). Chunks scoring below 0.35 are thrown away. The conversation manager builds a prompt
(system prompt + recent history + the chunks with their file names + the question) that is
guaranteed to fit in 4,096 tokens, and the reply streams back token by token, exactly as before.

---

## 2. Design decisions, in plain words

### Data
| Decision | Why (simple words) |
|---|---|
| A **fictional** gym (Zor Fitness Club) built from research on real Pakistani gyms | Realistic prices and rules without copying any real gym's facts (honor policy). The research is in `raw_sources/`. |
| One **facts file** (`facts_source_of_truth.md`) that every document follows | 80 documents written by hand drift apart. One source of truth + `eval/check_consistency.py` (every price and time must appear in the facts file) keeps them consistent. |
| Documents full of **unusual, specific rules** | If the documents only said generic things, the model would answer the same with or without RAG. Rules like "no guests at G-11 on weekdays 6–9pm" prove the answer came from the documents. |
| **Removed the Apex knowledge base** from the system prompt | Otherwise the model would already "know" everything and RAG would add nothing. Now facts come only from retrieval. |

### Indexing
| Decision | Why |
|---|---|
| **all-MiniLM-L6-v2** embeddings | Small (90 MB), fast on a CPU (~7 ms per query), good for short English text, fully local. |
| **Chroma** vector store | Local, saves to one folder, and stores **metadata** (file name, hash) next to each vector, which we need for citations and incremental updates. FAISS stores only vectors. |
| Chunks of **80–150 words** (not 200–300) | MiniLM only reads the first **256 tokens**. Our Markdown is ~1.7 tokens per word, so 300-word chunks lost their ending: 64% were truncated. Measured, then chosen. |
| Cut at **headings / blank lines**, never mid-paragraph | A rule or a price row stays in one piece. |
| **Title > heading prefix** on every chunk | A chunk that says only "Late fee is PKR 1,500" would lose its topic. The prefix keeps it. |
| **Small overlap** (last short paragraph repeated) | If a cut falls in the middle of a section, the next chunk still has the context. |
| **Tables turned into one line per row** | The 3B model misread grid tables (it applied the Ladies Wing's "Closed" to the whole branch). "Area: Ladies Wing; Sunday: Closed" can't be misread. |
| **File hashes** for incremental re-indexing | Only new or changed files are embedded again; deleted files are removed. A re-run with no changes does no embedding at all. |

### Retrieval
| Decision | Why |
|---|---|
| **top-k = 4** | The assignment says at least 3. 4 chunks is about 1,000 tokens, which fits the budget. |
| **Threshold 0.35** | From real scores: off-topic ≤ 0.17, small talk ≤ 0.30, weakest real question 0.375. 0.35 separates them. |
| Gym-related but uncovered questions (BJJ) are **handled by the prompt, not the threshold** | BJJ scored 0.520, the same as real questions, so no threshold can separate them. The prompt says "if the sources don't answer it, say so." |
| **Follow-up rule:** if the message has ≤ 6 words, add the previous user message | "and for ladies?" alone means nothing (score ~0.36). Longer messages are left alone so a topic switch isn't dragged back. Tested: 6/6. |
| Retrieval **in parallel** with the classifier | The classifier takes ~350 ms anyway; retrieval (10 ms) finishes inside that time, so it adds 0 ms. |
| **Override:** a strong document match (≥ 0.45) beats an OFF_TOPIC verdict | The classifier rejected "timings at the Bahria branch?". Off-topic messages never scored above 0.32, so 0.45 is safe. The off-topic catch rate stayed 10/10. |

### Prompt and budget
| Decision | Why |
|---|---|
| Set **num_ctx = 4096 explicitly** | Ollama was silently using 4096 and cuts overflow from the front, meaning the system prompt would go first. |
| Count tokens with **Qwen's own tokenizer** | Character estimates were wrong by up to 30% (prose vs tables). The real tokenizer matched Ollama within 1%. |
| Budget: reply 500, system ~1,559, reminder ~92, user ≤ 1,000, sources ≤ 1,200, history = the rest | Everything is guaranteed to fit. |
| **Drop the lowest-ranked chunk first, then the oldest history** | The best evidence and the newest context matter most. |
| **User message cap 1,000 tokens** (keep the beginning + a marker) | Urdu script uses many more tokens per character; the question is usually at the start. |
| Sources placed **after** the history | The system prompt + history stay identical between turns, so Ollama reuses its cache. |
| Source labels `[Source 1: plan_plus.md]` | The model knows which text came from which file. |
| **Server adds the "Source:" line** at the end (one final token) instead of the model | When the 3B model wrote it, it came at the start, the end, or not at all. Server-side, it is always at the end and always matches the chips. |
| The source line is **not stored in history** | Otherwise the model copies "Sources: …" into its next answer and the line appears twice (seen in testing). |
| Citations = optional `sources` field on `done` | Backward-compatible: old clients ignore it, and the field is absent (not null) when not grounded, so `done` is exactly Assignment 1's. Chips appear when the answer finishes. |
| No chips if the reply says "our documents don't cover that" | For BJJ, the chunks were related but didn't answer; chips would falsely claim grounding. |

### Real-time
| Decision | Why |
|---|---|
| Load the model and index **once at startup** | Loading takes seconds; per request it would be far too slow. |
| **asyncio.to_thread** for embedding + search | They are CPU work; in a thread, the async server keeps serving other users. |
| **2 s timeout** | A stuck search must never hang the chat. |
| **Two LRU caches** (embeddings, results) | A repeated question costs 0.04 ms instead of 9.4 ms. |
| **Index version in the cache key** | After `python -m rag.index`, old cache entries can never match, so no stale answers. Embeddings stay cached because they don't depend on the documents. |
| `OLLAMA_NUM_PARALLEL=4` | Ollama answered one request at a time; with 4 slots, the worst wait for 10 users went from 5.4 s to 3.0 s. |

### Failures
| Case | What happens |
|---|---|
| No relevant match | `[]` → NO MATCH note → "our documents don't cover that" + WhatsApp. |
| Index missing, corrupted or empty, embedding error, timeout | `None` → logged → RETRIEVAL UNAVAILABLE note → "I can't look that up right now" + UAN/WhatsApp. The chat keeps working. |
| Context overflow | The budget always fits; the system prompt is never cut; the user message is truncated with a marker. |

---

## 3. The prompts the model receives (exact text, from `backend/app/prompts.py`)

**Gym identity** (the only gym facts left in the system prompt):
> ABOUT ZOR FITNESS CLUB: a gym in Pakistan with three branches -- F-7 Islamabad, G-11 Islamabad
> and Bahria Town Phase 7 Rawalpindi. Front desk WhatsApp: 0333-5550967.

**Grounding rules** (part of the system prompt, `_BEHAVIOR_RULES`):
> - GROUNDING: every gym fact you state (prices, fees, hours, class times, trainer names,
>   policies, rules) must come from the SOURCES message you receive before the member's latest
>   message. Never invent or guess a Zor fact, and never use facts about other gyms.
> - If the sources don't contain the answer, say plainly that our documents don't cover that
>   and suggest the front desk on WhatsApp -- don't fill the gap with a guess.
> - Do NOT write file names or "Source:" lines yourself -- the system adds the source line
>   after your answer automatically.

**Sources message** (per turn):
> SOURCES -- excerpts from Zor Fitness Club's documents that best match the member's latest
> message, best match first. Use ONLY these for gym facts.
>
> [Source 1: plan_plus.md]
> *chunk text…*
>
> Answer the member's latest message from these sources. Tables: read each row on its own -- a
> value in one row (e.g. 'Closed') applies ONLY to that row's area or plan. If the sources don't
> contain the answer, say our documents don't cover that and suggest the front desk on WhatsApp
> (0333-5550967). Don't mention file names -- the source line is added for you.

**No match note:**
> SOURCES: none -- no Zor Fitness Club document matched the member's latest message. This message
> is gym-related (it already passed the topic check), so do NOT refuse it as off-topic. If it asks
> for a Zor Fitness Club fact (a service, facility, price, time, rule or name), reply: our
> documents don't cover that, and suggest the front desk on WhatsApp (0333-5550967) -- never guess
> or invent a Zor Fitness Club fact. Then continue the conversation normally … If it is a
> greeting, small talk or a general fitness question, just answer it normally.

**Retrieval unavailable note:**
> SOURCES: unavailable -- the Zor Fitness Club document search is not working right now, so you
> have NO gym facts this turn and you CANNOT look anything up. Do NOT state or guess any … price,
> fee, time, schedule, trainer or policy, do not offer to look it up, and do not start, confirm
> or walk through any booking, freeze, refund, transfer or payment. If the member asks about any
> of these …, reply with: "Sorry, I can't look that up right now. Please contact our front desk:
> UAN 051-111-967-348, WhatsApp 0333-5550967, or any branch reception." Greetings, small talk and
> general fitness questions can be answered normally.

The **persona, scope rules, stage guide, scope reminder and the classifier prompt** are unchanged
from Assignment 1, except that the gym name is now Zor (see `prompts.py`, `CLASSIFIER_SYSTEM_PROMPT`).

**Why the wording looks like this (lessons from testing):**
- Giving the model the **exact sentence** to say worked much better than describing the
  behaviour. The no-match reply went from an off-topic refusal to the right answer 3/3, and the
  unavailable reply from "I can look that up for you" to the right answer 3/3.
- "This message already passed the topic check, do NOT refuse it" was needed because the scope
  reminder pushed the model into refusal mode.

---

## 4. Prompts used with the AI coding assistant (to reproduce the work)

The work was done phase by phase with an AI coding assistant (Claude Code). At each phase it
stopped and showed its test results before the next one started. Condensed prompts:

1. **Setup:** "Read Assignment_2.pdf and follow it exactly. Explore the existing Assignment 1
   codebase and summarise the architecture before changing anything. Hard constraints: WebSocket
   contract unchanged, RAG only, fully local, minimal readable code, a new `rag/` module, test
   each phase separately."
2. **Phase 0, documents:** "Research real Pakistani gyms (public pages only, save notes with URLs
   in raw_sources/), build ONE fictional gym in facts_source_of_truth.md, then write 60–80
   documents of 250–500 words each in batches of 10, with PKR prices, ladies timings, Friday
   prayer and Ramadan rules, Roman Urdu FAQs and unusual rules. Check consistency after each batch.
   Create 20–25 test questions including out-of-corpus ones."
3. **Phase I, indexing:** "Heading-aware chunking with overlap, all-MiniLM-L6-v2, persistent
   Chroma with source metadata, incremental re-indexing by file hash. Prefix each chunk with its
   title and heading. Print chunk statistics. Test: first run, a re-run with no changes, a re-run
   after one edit and one delete."
4. **Phase II, retrieval:** "retrieve(query) with top-k 4. Show me the top-1 score for every test
   question before choosing a threshold. Handle short follow-up questions. Check num_ctx and
   write down a token budget (drop the lowest chunks first, then the oldest history). No-match
   behaviour. Remove the Apex KB but keep the classifier, and show the off-topic catch rate
   didn't drop. Run retrieval in parallel with the classifier in a thread pool. 5 end-to-end
   examples."
5. **Phase III, real-time:** "Benchmark retrieval alone (cold, warm, cache hit) and end-to-end
   first-token time; an LRU cache invalidated by re-indexing; a concurrency test with 5 and 10
   WebSocket clients (be honest if Ollama queues); an automated test that streaming is identical
   to Assignment 1."
6. **Phase IV, failures:** "One test per case: no match; Chroma folder missing or corrupted,
   embedding error, timeout, empty index (add a 'retrieval unavailable' note so the model invents
   nothing); context overflow with a huge history, a 3,000-word message and the largest chunks;
   empty messages, Roman Urdu and Urdu, and one client failing while others are connected."
7. **Docs, bonus, landing page:** "README with every PDF deliverable and real numbers, these viva
   notes, visible citations (backward-compatible field), and a landing page redesign on a separate
   branch."

Every decision marked "user OK'd" in the history (threshold 0.35, chunk size 80–150, classifier
override 0.45) was shown with measurements first and approved before it was implemented.

---

## 5. Likely viva questions, with short answers

**What is RAG, in one sentence?** Before answering, look up the relevant parts of our own
documents and put them in the prompt, so the model answers from them instead of from memory.

**Why not put all 80 documents in the prompt?** 36,000 words × ~1.7 tokens per word ≈ 60,000
tokens, about 15× our 4,096-token context, and slow. Retrieval picks the ~1,000 tokens that matter.

**How is similarity computed?** Both the question and the chunks become 384-number vectors. The
score is the cosine similarity (1.0 = same direction). Chroma stores cosine *distance*, so
score = 1 − distance.

**Why 0.35?** Show the score table (README §5.1): it sits between the highest small-talk score (0.30)
and the lowest real question (0.375).

**What if a question is gym-related but not in the documents?** It passes the threshold, and the
grounding rule makes the model say "our documents don't cover that". Real example: BJJ/MMA.

**How do you stop the prompt from overflowing?** A token budget counted with Qwen's tokenizer:
the system prompt is always kept, the lowest-ranked chunks are dropped, then the oldest history,
and the user message is capped at 1,000 tokens.

**Does retrieval make the chat slower?** No. 9–10 ms, in parallel with the 350 ms classifier call.
Retrieval is 0.8% of the total reply time.

**What happens if Chroma breaks?** Retrieval returns "unavailable" within 2 s, it is logged, and
the model is told it has no facts and must point to the UAN, WhatsApp or the branch desk. Tested
with a missing folder, a corrupted folder, an embedding error, a timeout and an empty index.

**How do you know the cache never gives stale answers?** The index version (the marker file's
timestamp) is part of the cache key; the test changes a price, re-indexes, and gets the new price.

**How do you know streaming didn't change?** An automated test compares every event's fields
with Assignment 1's schemas (the only allowed addition is the optional `sources` on `done`) and
checks one token event per model chunk, for the grounded, no-match, override, failure and
off-topic paths. In a real browser, 23 token frames gave 23 updates of the answer text.

**How do the citations work?** The server knows which chunks it put in the prompt. After the
reply streams, it sends one final token "Sources: a.md, b.md" and adds `"sources": [...]` to
`done`; the React hook attaches that list to the message, and `MessageBubble` draws the chips.
There are no chips for no-match, failure, off-topic, or "documents don't cover that".

**Why is the Chroma folder not in git?** It's generated and machine-specific. `python -m rag.index`
rebuilds it from `documents/` in about 25 seconds.

**Biggest weakness?** The 3B model sometimes misreads correct sources (e.g. table rows). We fixed
the cases we found through the data (linearized tables, clearer sentences), and the rest are
listed honestly in the README's Known Limitations.

---

## 6. Demo commands

```bash
cd backend
python -m rag.index --samples 3                          # build the index + show stats and 3 chunks
python -m pytest -q                                      # 71 tests
python -m rag.benchmark                                  # latency tables
uvicorn app.main:app --port 8000                         # run the backend
../backend/.venv/Scripts/python.exe ../eval/e2e_examples.py      # 5 real conversations (backend running)
../backend/.venv/Scripts/python.exe ../eval/concurrency_test.py  # 1, 5 and 10 clients
```
