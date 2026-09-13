"""
Centralized configuration, loaded from environment variables (with sane
defaults) via pydantic-settings. Keeping this in one place means the model
name, Ollama host, and tuning knobs are never hardcoded deeper in the app.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolved relative to this file (backend/app/config.py -> backend/.env), NOT the process's
# current working directory. A relative "./.env" would silently fall back to the class
# defaults below whenever something is run from outside backend/ (e.g. the benchmark script,
# which the README itself tells you to run from the repo root) -- it was caught exactly that
# way during testing, so it's pinned to an absolute path to make that failure impossible.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # --- LLM / Ollama ---
    ollama_host: str = "http://localhost:11434"
    model_name: str = "qwen2.5:3b"
    request_timeout_s: float = 60.0

    # --- Conversation memory ---
    # Number of user+assistant EXCHANGES (turn pairs) kept in the prompt.
    # See conversation_manager.py for the sliding-window implementation and
    # the README's "Context Memory Management" section for the rationale.
    max_history_turns: int = 6

    # --- Generation params ---
    # Kept low (rather than a more "natural" ~0.7-0.8) because reliability of the scope/
    # persona rules matters more here than conversational flair for a small local model -- see
    # the README's Known Limitations for what this trades off.
    temperature: float = 0.15
    top_p: float = 0.9
    # Hard cap on generated tokens per reply. 350 was too tight -- it truncated legitimate
    # full-week class-schedule listings mid-sentence during manual testing; 500 comfortably
    # covers a full 7-class listing while still bounding worst-case latency.
    num_predict: int = 500

    # --- Server ---
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
