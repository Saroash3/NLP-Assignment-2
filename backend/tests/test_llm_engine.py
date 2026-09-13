"""
Unit tests for the Ollama streaming client, using httpx.MockTransport to
fake an Ollama server's NDJSON response. These tests verify our parsing
and error-handling logic in isolation -- they never touch a real model,
so they run the same on any machine (and in CI) regardless of whether
Ollama is installed.
"""
import json

import httpx
import pytest

from app.llm_engine import LLMEngine, LLMEngineError


def _ndjson_response(lines: list[dict]) -> httpx.Response:
    body = "\n".join(json.dumps(line) for line in lines).encode()
    return httpx.Response(200, content=body)


@pytest.mark.asyncio
async def test_stream_chat_yields_text_chunks_in_order():
    lines = [
        {"message": {"content": "Hello"}, "done": False},
        {"message": {"content": " there"}, "done": False},
        {"message": {"content": "!"}, "done": True, "eval_count": 3, "eval_duration": 300_000_000},
    ]
    transport = httpx.MockTransport(lambda request: _ndjson_response(lines))
    client = httpx.AsyncClient(transport=transport)
    engine = LLMEngine(client=client)

    chunks = [chunk async for chunk in engine.stream_chat([{"role": "user", "content": "hi"}])]

    assert "".join(chunks) == "Hello there!"
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_with_stats_uses_ollama_reported_eval_counts():
    lines = [
        {"message": {"content": "Hi"}, "done": False},
        {"message": {"content": " Nova"}, "done": False},
        {
            "message": {"content": ""},
            "done": True,
            "eval_count": 10,
            "eval_duration": 1_000_000_000,  # 1 second, in nanoseconds
        },
    ]
    transport = httpx.MockTransport(lambda request: _ndjson_response(lines))
    client = httpx.AsyncClient(transport=transport)
    engine = LLMEngine(client=client)

    text, stats = await engine.generate_with_stats([{"role": "user", "content": "hi"}])

    assert text == "Hi Nova"
    assert stats.completion_tokens == 10
    assert stats.eval_duration_s == pytest.approx(1.0)
    assert stats.tokens_per_second == pytest.approx(10.0)
    await client.aclose()


@pytest.mark.asyncio
async def test_stream_chat_raises_llm_engine_error_on_http_failure():
    transport = httpx.MockTransport(lambda request: httpx.Response(500, content=b"boom"))
    client = httpx.AsyncClient(transport=transport)
    engine = LLMEngine(client=client)

    with pytest.raises(LLMEngineError):
        async for _ in engine.stream_chat([{"role": "user", "content": "hi"}]):
            pass
    await client.aclose()


@pytest.mark.asyncio
async def test_stream_chat_raises_llm_engine_error_on_connect_failure():
    def raise_connect_error(request):
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(raise_connect_error)
    client = httpx.AsyncClient(transport=transport)
    engine = LLMEngine(client=client)

    with pytest.raises(LLMEngineError, match="ollama serve"):
        async for _ in engine.stream_chat([{"role": "user", "content": "hi"}]):
            pass
    await client.aclose()


@pytest.mark.asyncio
async def test_check_health_false_when_unreachable():
    def raise_connect_error(request):
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(raise_connect_error)
    client = httpx.AsyncClient(transport=transport)
    engine = LLMEngine(client=client)

    assert await engine.check_health() is False
    await client.aclose()
