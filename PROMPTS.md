# PROMPTS.md — Assignment 3 build log

One entry per stage: what it was for, the key design decisions, and what was measured.
Hardware used for every number below: Intel i9-14900HX (24 cores), RTX 4080 Laptop GPU (12 GB),
32 GB RAM, Windows 11, Python 3.14, Ollama with `qwen2.5:3b` (`OLLAMA_NUM_PARALLEL=4`).

---

## Stage A — Tools + orchestrator (text chat)

**Purpose.** Three fitness tools that the LLM can call through prompt-based function calling,
used by the same pipeline as normal chat.

**Decisions**
- **Tools** (`backend/app/tools/`): `calculate_fitness_metrics` (BMI, Mifflin-St Jeor calories,
  Epley 1RM), `lookup_nutrition` (42 foods in `backend/data/foods.json`, alias + fuzzy match),
  `workout_schedule` (add / list / delete in `backend/data/workouts.json`). Each tool is a
  `Tool(name, description, parameters=JSON schema, run=async fn)`.
- **First attempt — tools listed in the main system prompt, model replies with JSON: failed.**
  Measured on qwen2.5:3b: 0 of 7 tool requests produced a tool call. The tool list was buried in
  the ~1,600-token persona prompt plus retrieved sources. The model asked for numbers it had
  already been given, or refused BMI as "math", because the A2 scope rules say "refuse any
  calculation". It also pushed the system prompt to 2,296 tokens, which squeezed out the history
  at `num_ctx=4096`.
- **Final design — a separate tool-router call** (`orchestrator.route`). A short prompt whose
  only job is to reply `NONE` or one JSON object `{"tool": ..., "arguments": {...}}`, with 12
  few-shot examples, temperature 0. It is still prompt-based function calling, just in a prompt
  small enough for a 3B model. Result: **7/7 tool requests routed correctly, 0 false positives**
  on plan/price/off-topic questions.
- **No added latency for the decision:** the router runs in `asyncio.gather` **in parallel**
  with the A2 off-topic classifier and retrieval (Ollama serves the parallel requests), and the
  answer is still ONE streamed generation, so the text token contract is unchanged.
- **The tool result is a system message** placed after the scope reminder, so the "refuse math"
  reminder can't override it. Its wording says the numbers are FINAL. Before that change the
  model "recalculated" a 1RM (96 kg → said 128 kg); after it, 6/6 were correct.
- **A tool call overrides an OFF_TOPIC verdict** (the classifier doesn't know "my BMI" is the
  member's own fitness), the same idea as the A2 retrieval override.
- **Safety:** `validate_args` checks types, enums and required keys and drops invented keys;
  `run_tool` uses `asyncio.wait_for(timeout=5 s)`, and a timeout, error or crash becomes a
  friendly message that the model words for the member. `user_id` comes from the server
  (`ToolContext`), never from the LLM, so a member can't touch another member's schedule.
  JSON files are written atomically under a lock, in a worker thread.
- **Contract:** new event types (`tool_call`, `tool_result`, `latency`) are only sent to clients
  that connect with `?extended=1`. The A2 contract tests still pass unchanged, and a new test
  checks that an old client sees only `token`/`done`.
- **Small fixes:** the classifier gained tool examples and an explicit rule that greetings and
  small talk are ON_TOPIC. Greetings ("Hello") were redirected as off-topic by the **A2 prompt
  too** (checked), and few-shot examples alone only fixed the exact example phrasings. A2
  off-topic battery: 27/30 before → **28/30** after ("How's your day going?" now passes), and
  every clearly off-topic case is still refused.

**Tests:** `backend/tests/test_tools.py` covers each tool, the validator, the parser, timeout,
crash, router failure, a full tool turn over the WebSocket, and the old-client contract.

---

## Stage B — Text-to-speech (Piper)

**Purpose.** Speak each sentence of the reply as soon as it is complete, while the text keeps
streaming.

**Decisions**
- **Piper (`en_US-lessac-medium`, ONNX, CPU) over Kokoro.** Piper synthesizes a sentence in
  ~50–100 ms on CPU (~40× real time) with a 60 MB voice. Kokoro sounds more natural but is
  several times slower on CPU, and the first-audio latency is what's graded.
- `voice/sentence_buffer.py`: a sentence ends at `. ! ?` + space or a newline, so `24.7` doesn't
  split. **The first chunk may end at a comma once it has 40+ characters**, which starts the
  first audio sooner. Markdown symbols are stripped before speaking.
- `voice/speech_output.py`: tokens go onto a queue; a worker task synthesizes sentences **in
  order** in a single-thread executor and sends `audio` events (`seq`, `sample_rate`, base64
  PCM). Token streaming never waits for TTS. A TTS failure sends one `tts_error`, and the text
  reply and the turn still finish normally (tested).
- The `Source: …` line is sent to the chat only; it is never spoken.
- One TTS thread: a sentence takes tens of ms, and it keeps espeak-ng (Piper's phonemizer, a C
  library with global state) on a single thread.

## Stage C — Speech-to-text + VAD

**Purpose.** Stream the mic over the same WebSocket, show live captions, detect the end of
speech, and turn the final transcript into a normal turn.

**Decisions**
- **Transport:** binary WebSocket frames of 16 kHz mono int16 PCM, 1024 samples (64 ms) each,
  on the **same** `/ws/chat` socket. JSON control messages `voice_start` / `voice_stop`. The
  receive loop uses `websocket.receive()` and dispatches on text vs. bytes; text handling is
  unchanged.
- **VAD: Silero v6 (ONNX)**, the copy that ships inside faster-whisper (nothing extra to
  download), run in **streaming** mode. Each connection keeps its own LSTM state and 64-sample
  context. Hysteresis: speech starts at p ≥ 0.5 and counts as silence below 0.35. End of speech
  = 0.5 s of silence; blips under 0.25 s are ignored; 0.3 s of pre-roll keeps the first
  syllable.
- **ASR: faster-whisper.** Measured on a 4.8 s question: CPU int8 tiny.en 146 ms, base.en
  299 ms, small.en 831 ms; **GPU float16 small.en ≈ 70–110 ms** with a perfect transcript.
  `device="auto"` tries CUDA (`small.en`) and falls back to CPU (`base.en`). The CUDA DLLs come
  from the `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` wheels. A domain `initial_prompt`
  ("BMI, protein, one rep max…") biases spelling.
- **Warm-up with noise, not silence:** a silent warm-up skips the decoder, and the first real
  call then took 1.5 s. With a noise warm-up it takes ~70 ms.
- **Partial transcripts** run every ~0.7 s as a background task (skipped if one is still
  running); a stale partial is dropped via an utterance id. The ASR executor has 2 threads, so
  a partial never delays the final transcript and two users can be transcribed at once.

## Stage D — Full voice loop

**Purpose.** Spoken turns go through the same LLM streaming, history, RAG and tools as typed
turns.

**Decisions**
- The final transcript calls the **same `run_turn()`** as typed text; the only extra argument
  is `speech=SpeechOutput(...)`.
- **Half-duplex:** the browser only sends mic audio while the server says `listening` and
  nothing is playing. This prevents the assistant from transcribing its own voice from the
  speakers. Trade-off: no barge-in.
- Server states: `listening → transcribing → thinking → speaking → listening`. The browser
  shows `speaking` while its audio queue plays.
- Verified in a real Chromium with a fake-microphone WAV: AudioWorklet → partials → final →
  `lookup_nutrition` card → spoken answer, 682 ms to first audio.

## Stage E — Latency + concurrency

**Purpose.** Measure every voice turn, hit the ~1 s target, and make sure no user blocks
another.

**Decisions / findings**
- Per-turn `TurnTimings` → a `latency` event plus a log line: ASR, retrieval + routing, tool,
  LLM first token, TTS first audio, end of speech → first audio.
- **Biggest win: `localhost` → `127.0.0.1` for Ollama.** On Windows, `localhost` tries IPv6
  first and Ollama listens on IPv4, so **every** LLM request lost ~270 ms. Classifier
  310 → 41 ms, main first token 330 → 42 ms; the voice median went from 1,318 to 737 ms. (This
  also speeds up A1/A2 text chat.)
- `keep_alive: 30m` plus a warm-up request at startup, so a reload of the model (~6 s) never
  lands on a member's first turn.
- `benchmarks/voice_benchmark.py` streams Piper-spoken questions in **real time**: one voice
  user, voice + text together, and two voice users together. Results are in
  `benchmarks/voice_results.md`.
- All heavy work runs off the event loop: ASR (2 threads), TTS (1 thread), VAD and JSON
  stores (`to_thread`), and LLM calls through async httpx. The A2 concurrency test (10 text
  clients) still passes, and `/session/new` answers in ~2 ms under load.

## Stage F — CRM bonus (`user_profile`)

**Purpose.** Remember the member across visits and greet a returning member.

**Decisions**
- A stable **`user_id` per browser** (localStorage) is sent as `?user_id=`. `profiles.json`
  stores name, goal, injuries, preferences, last workout, and the last 5 interactions.
- **LLM-callable tool** `user_profile` (`get` / `update`) is routed like the others ("My name is
  Sara and I want to build muscle" → update).
- **Server-side, without the LLM:** the profile is added to every prompt as a system message
  (loaded inside the same `gather`, so it costs no latency), each on-topic request is logged,
  and a **new session of a known user starts with "Welcome back, Sara! Last time you asked:
  …"**. The greeting is a template, so it's instant and can't hallucinate. It is kept in the
  history and **spoken once when voice mode starts**.
- Off-topic requests are not logged, so the greeting never recalls "who won the World Cup".
- Prompt fixes after a live run: after a tool call the model invented class times, so the
  tool-result message now forbids gym facts that aren't in the sources. It ignored a saved
  knee injury, so the profile note now says advice must avoid stressing a listed injury.

---

## Stage H — Fixes from the first live demo

**Purpose.** Problems found when the app was used with a real microphone and browser.

- **"Listening…" but nothing heard:** the mic AudioContext is created after the permission
  prompt, outside the click, so Chrome started it *suspended* and no audio was sent. Fix:
  `context.resume()`, plus a muted (gain 0) path to the speakers so the worklet is always pulled.
- **A muted/wrong mic sent pure zeros** (server log: peak level 0.000), and the UI just sat on
  "Listening…". The server now logs the mic level every ~3 s and sends a `mic_silent` toast ("check
  the mic-mute key and the browser's microphone setting").
- **The first turn after a long idle took 9.2 s** (Ollama unloads the model after 30 min; the GPU
  was in a low-power state). Turning voice mode on now warms the LLM, Whisper and Piper in the
  background.
- **Router false positive:** "What classes do you have on Tuesdays?" was sent to
  `workout_schedule` → a `NONE` example was added.
- **Nutrition doubling:** the model turned "2 x 1 egg, protein 13 g" into 26 g → the result key
  `portion` was renamed `totals_for`.
- **Mishearing an accented speaker** ("Hi Nova" → "Hain Allah" / "Hi Noah"): ASR switched from
  `small.en` to `large-v3-turbo` (forced English) plus a vocabulary prompt (Nova, trainers,
  branches, plans). Word errors on 40 test sentences: 12–15% → 4–8%, for ~+60 ms. Measured: beam
  search 5 added 60 ms and gained nothing on turbo, so decoding stays greedy. Honest limit: the only
  "accented" test voices available offline (Hindi Piper voices reading English) are too robotic to
  measure accent robustness; large Whisper models are known to be far more robust than small ones.
- End of speech 0.5 → 0.6 s (short pauses were cutting people off).
- **"It stopped hearing me" after a few turns:** the log showed sound arriving but no speech
  detected, at ~65% of real-time speed. Possible causes: two mic pipelines after toggling, or a
  throttled/hidden tab. Fixes: the mic hook now always stops the old pipeline first and discards a
  start that was cancelled mid-way (tested in Chromium with 4 rapid toggles: "Hi Nova, how much
  protein is in two eggs?" heard exactly), and the server logs "X s received in Y s" so a slow
  stream is visible.
- Tool answers said "13 g **each**" and "The tool result shows…": the result is labelled "in
  total", and the instruction now gives an example answer and forbids "the tool / the result".
- **Real-voice fixes (from saved clips of the live tester):** Chrome now resamples the mic to
  16 kHz itself (my linear-interpolation resampler had no low-pass filter and distorted real mics);
  browser noise suppression and auto-gain off; server-side volume normalisation (a real clip
  peaked at 0.04); "Noah" → "Nova"; the member's saved name is added to Whisper's vocabulary as a
  sentence ("Hi Nova, I'm Sarosh!") -- a "Member: X" label leaked into a transcript. After these,
  12 of 13 live sentences were transcribed correctly ("males" was once heard as "wheels").
- **"My name is treated as off-topic":** the off-topic gate classifies each message ALONE, so "Tell
  me my name" and "what is my name?" looked like trivia, and follow-ups like "Okay, so what is that
  specific times?" meant nothing without the previous turn. Fixes: classifier + router examples for
  questions about the member (now answered from the CRM profile: "Your name is Sarosh", 4/4), and a
  rule that a short, vague follow-up (≤ 8 words, connector or pronoun, fillers like "okay," skipped)
  right after an on-topic turn is not redirected. Clear off-topic questions ("Who won the cricket
  World Cup?") are not vague, so they are still refused (tested).
- **Men's timings were answered wrongly** (Ramadan hours, or an invented 10am–10pm): no chunk was
  about men's hours, and "Main floor" in the hours table never says "men". Added `hours_for_men.md`
  (title on every chunk = strong retrieval signal; all times from the facts file) and an explicit
  sentence under the G-11 timetable (the 3B model read the 4:30pm ladies/cleaning row as the men's
  start). Men's-hours questions now retrieve the new document first (0.49–0.65), A2 recall@4 is
  still 20/20, and the G-11 blocks (6–10am, 5–11pm) appear in 6/6 answers.
- **"My name is Sarosh, it's taking Saros" -- a feedback loop I had built:** the saved name was
  fed to Whisper as a spelling hint, so once "Saros" was misheard and saved, every spoken correction
  was heard as "Saros" again. Re-transcribing the tester's 12 name clips: hint "Saros" -> "Saros"
  every time; hint "Sarosh" -> "Sarosh" in 11/12, no other sentence changed. Fix: only a TYPED name
  becomes a hint (the profile records name_source), and a spoken near-miss of a typed name keeps
  the typed spelling (a genuinely new name still replaces it). Also "Doha" -> "Nova", "plane" -> "plan".
- **Tap-to-talk (requested for accuracy), now the default:** tap the mic to start recording, tap
  again to send. Everything in between is ONE utterance (`record_start` / `record_stop`), so the
  VAD can never cut the member off at a pause and background noise can never start a turn; the
  VAD only checks that the recording contains speech (silence is not sent -- Whisper invents text
  for it) and live captions start only once speech is heard. Capped at 60 s. Hands-free (VAD
  end-of-speech, the original requirement) stays available via a small mode switch next to the mic.
- **Nutrition tool, "pick any food":** the live log showed (a) no tool call for many food questions,
  (b) only 42 foods (no pizza, cake...), (c) "6 foot" sent as height_cm=720 -> BMI 2.1. Fixes:
  13,224 foods from USDA FoodData Central (public domain, built once by `data/build_food_db.py`)
  behind the 59 curated entries (Pakistani dishes added as typical home-recipe averages); word
  matching with plural folding, synonyms (donut -> doughnut), "slice" = "piece", generic "NFS"
  entries and non-diet versions preferred, realistic default portions; answers give calories,
  protein, carbs and fat. Feet/inches/pounds are now parsed from the member's words by code and
  impossible heights rejected (and a failed tool may not be answered with an invented number).
  **The router now sees only the latest message:** with the previous exchange in its context the
  3B model wrote answers itself (0/9 tool calls), and with the previous question it re-used that
  question's food ("carbs in rice" -> egg); latest-only measured 7/8, plus a retry with the
  previous message for vague follow-ups. Tool turns use a neutral sources note (the "no matching
  documents" note made the model say "our documents don't cover that" over a correct tool result).
  Replay of the tester's session: 11/12 correct before the last router examples, then "what about
  chicken?" fixed too.
- **"Use a bigger model" -- measured on the tester's REAL voice (21 saved clips, references written
  from what they said):** turbo greedy 97.5% word accuracy / 18 of 21 sentences exact / ~165 ms;
  full `large-v3` 96.3% / 15 of 21 / ~290 ms; large-v3 beam 5 95.1%; hotwords and beam search did
  not help either model. The bigger model was *worse* on this voice and slower, so turbo stayed.
  The two real misses ("Hi **Dova**", "plans regarding **wheels**") were fixed with sound-alike
  name corrections (Dova/Noah/Nowa… → Nova) and "males, females, men, women" in the vocabulary:
  **98.8% word accuracy, 20 of 21 exact** (the last one is "I am" vs "I'm"). Caveat: tuned on the
  same clips, so expect a little lower on new speech.
- **Document gap: "plans regarding males?"** got only Ladies-Only documents, so Nova implied the gym
  was women-only. No document said men can join. Added `who_can_join_men_and_women.md` (from the
  facts file; men: Standard/Plus/Elite, women: all four, explicit "men cannot join Ladies Only")
  and classifier examples ("Is this gym only for ladies?" was redirected as off-topic). 9/9 re-runs
  correct. Note: a running server keeps serving cached search results after a re-index; restart it.
- **Tried and removed:** Urdu speech, Urdu replies (via NLLB translation) and a Pakistani-accent
  voice were prototyped. They worked, but the extra models and the accent quality were judged
  too much for this assignment, so the app is back to English-only with the American Piper voice.
