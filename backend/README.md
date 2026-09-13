# Backend — Apex Fitness Assistant API

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
| `app/conversation_manager.py` | Session state, sliding-window history, stage tracking, and the off-topic classification gate (`classify_off_topic` — see root README §3) |
| `app/llm_engine.py` | Async streaming client for Ollama's `/api/chat` |
| `app/prompts.py` | System prompt assembly (persona, scope rules, stage guide) + the separate classifier prompt/canned redirects |
| `app/knowledge_base.py` | Gym domain data (plans, trainers, schedule, facilities, policies) |
| `app/schemas.py` | Pydantic models for the REST/WebSocket JSON contracts |
| `app/config.py` | Settings (model name, Ollama host, history window size, ...) |
| `tests/` | Unit + integration tests (see `../docs/TESTING.md`) |
