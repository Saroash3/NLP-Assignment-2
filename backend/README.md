# Backend — Zor Fitness Assistant API (with RAG)

FastAPI service: WebSocket streaming chat (`/ws/chat`) + REST health/session endpoints, backed
by a locally running Ollama model. Full project docs (architecture, model choice, benchmarks,
example dialogues) are in the [root README](../README.md) — this file is just quick-start
commands for this directory.

## Run it

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash); .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
python -m rag.index                # build the vector index from ../documents
uvicorn app.main:app --reload --port 8000
```

Requires Ollama running locally with the model pulled: `ollama pull qwen2.5:3b`.

## Test it

```bash
pytest -v
```

## Layout

| File | Responsibility |
|---|---|
| `app/main.py` | FastAPI app, REST routes, the `/ws/chat` websocket handler |
| `app/conversation_manager.py` | Session state, history, stage tracking, the off-topic gate, and RAG integration: retrieval with timeout, follow-up rule, classifier override, token budget |
| `app/llm_engine.py` | Async streaming client for Ollama's `/api/chat` |
| `app/prompts.py` | System prompt (persona, scope, stages, grounding rules), the per-turn SOURCES / no-match / unavailable messages, and the classifier prompt |
| `rag/store.py` | Paths, embedding model loader, Chroma collection, index version marker |
| `rag/index.py` | Offline indexing pipeline: chunk → embed → store, incremental by file hash (`python -m rag.index`) |
| `rag/retriever.py` | `retrieve(query)` top-k search + LRU caches |
| `rag/benchmark.py` | Latency benchmark (`python -m rag.benchmark`) |
| `app/schemas.py` | Pydantic models for the REST/WebSocket JSON contracts |
| `app/config.py` | Settings (model name, Ollama host, history window size, ...) |
| `tests/` | Unit + integration tests (see `../docs/TESTING.md`) |
