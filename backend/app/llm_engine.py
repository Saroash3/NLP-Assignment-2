"""
LLM Engine: thin async wrapper around a locally running Ollama server.

This module's ONLY job is to speak Ollama's HTTP streaming protocol and
yield tokens as they arrive, or raise a typed error the caller can turn
into a clean websocket error event instead of a crash.

It knows nothing about sessions, system prompts, or domain policy -- that
separation is what makes it independently testable (see backend/tests)
and swappable (llama.cpp or vLLM could sit behind the same interface).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from app.config import get_settings


class LLMEngineError(Exception):
    """Raised when the local model can't be reached or fails mid-generation."""


@dataclass
class GenerationStats:
    """Performance stats for one completion. Consumed by the benchmark script."""

    time_to_first_token_s: float
    total_time_s: float
    completion_tokens: int
    # Ollama's own generation-phase timer (ns -> s), when it reports one.
    # More accurate than wall-clock because it excludes prompt-eval time.
    eval_duration_s: float | None = None

    @property
    def tokens_per_second(self) -> float:
        duration = self.eval_duration_s or (self.total_time_s - self.time_to_first_token_s)
        if duration <= 0:
            return 0.0
        return self.completion_tokens / duration


class LLMEngine:
    """
    Streams chat completions from a local Ollama server via its native
    /api/chat endpoint (newline-delimited JSON streaming), using a shared
    async HTTP client so generation never blocks the event loop -- multiple
    sessions can be mid-generation at the same time without one stalling
    another (Phase IV's "asynchronous, non-blocking" requirement).
    """

    def __init__(self, client: httpx.AsyncClient | None = None):
        settings = get_settings()
        self._base_url = settings.ollama_host.rstrip("/")
        self._model = settings.model_name
        self._timeout = settings.request_timeout_s
        self._temperature = settings.temperature
        self._top_p = settings.top_p
        self._num_predict = settings.num_predict
        self._num_ctx = settings.num_ctx
        self._client = client or httpx.AsyncClient(timeout=self._timeout)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def check_health(self) -> bool:
        """Used by GET /health. True if the Ollama server responds at all."""
        try:
            resp = await self._client.get(f"{self._base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def warm_up(self) -> None:
        """Assignment 3: a 1-token request at startup so Ollama loads the model before the
        first real (possibly spoken) turn. Failures are only logged."""
        try:
            await self.generate_with_stats([{"role": "user", "content": "hi"}], num_predict=1)
        except Exception as e:
            logging.getLogger("zor_assistant").warning("LLM warm-up failed: %s", e)

    async def _stream_raw(
        self,
        messages: list[dict[str, str]],
        *,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Yield each decoded NDJSON line from Ollama's streaming response.

        `num_predict`/`temperature` override the instance's configured defaults for
        this call only -- used by the off-topic classification gate (see
        ConversationManager.classify_off_topic), which needs a tiny token budget and
        temperature 0 for a strict single-word verdict, distinct from the main
        persona chat's generation settings.
        """
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            # Assignment 3: keep the model in GPU memory for 30 min (Ollama's default is 5) --
            # reloading it costs ~6 s, which would wreck the voice latency after a pause.
            "keep_alive": "30m",
            "options": {
                "temperature": temperature if temperature is not None else self._temperature,
                "top_p": self._top_p,
                "num_predict": num_predict if num_predict is not None else self._num_predict,
                # Always sent explicitly so the context window never depends on Ollama's default.
                "num_ctx": self._num_ctx,
            },
        }
        try:
            async with self._client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise LLMEngineError(
                        f"Ollama returned HTTP {response.status_code}: {body[:300]!r}"
                    )
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # skip a stray non-JSON keep-alive line
                    if chunk.get("error"):
                        raise LLMEngineError(str(chunk["error"]))
                    yield chunk
                    if chunk.get("done"):
                        return
        except httpx.ConnectError as e:
            raise LLMEngineError(
                "Could not reach the local Ollama server. Is `ollama serve` running?"
            ) from e
        except httpx.TimeoutException as e:
            raise LLMEngineError("The local model timed out while generating a response.") from e
        except httpx.HTTPError as e:
            raise LLMEngineError(f"HTTP error talking to Ollama: {e}") from e

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream plain text chunks for a chat completion. This is what the
        websocket handler consumes to forward tokens to the browser as
        they're generated.
        """
        async for chunk in self._stream_raw(messages, num_predict=num_predict, temperature=temperature):
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content

    async def generate_with_stats(
        self,
        messages: list[dict[str, str]],
        *,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, GenerationStats]:
        """
        Consume a full completion and return (full_text, GenerationStats).
        Used by the benchmark script and by the off-topic classification gate,
        both of which need the complete response rather than a live stream to
        the client.
        """
        start = time.perf_counter()
        first_token_time: float | None = None
        chunks: list[str] = []
        final_meta: dict[str, Any] = {}

        async for chunk in self._stream_raw(messages, num_predict=num_predict, temperature=temperature):
            content = chunk.get("message", {}).get("content", "")
            if content:
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                chunks.append(content)
            if chunk.get("done"):
                final_meta = chunk

        end = time.perf_counter()
        full_text = "".join(chunks)
        ttft = (first_token_time or end) - start

        eval_count = final_meta.get("eval_count") or max(1, len(full_text.split()))
        eval_duration_ns = final_meta.get("eval_duration")
        eval_duration_s = (eval_duration_ns / 1e9) if eval_duration_ns else None

        return full_text, GenerationStats(
            time_to_first_token_s=ttft,
            total_time_s=end - start,
            completion_tokens=eval_count,
            eval_duration_s=eval_duration_s,
        )
