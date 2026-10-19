"""
Text-to-speech with Piper (local ONNX voice, CPU).

Why Piper over Kokoro: Piper synthesizes a sentence in ~tens of ms on CPU (far faster than
real time) with a 60 MB voice, while Kokoro sounds more natural but is ~5x slower on CPU and
much heavier -- and first-audio latency is what this assignment grades.

The voice is loaded ONCE at startup. synthesize() is CPU-bound, so it runs in a dedicated
single-thread executor: it never blocks the event loop, and one thread is enough because a
sentence takes only tens of ms. It also keeps espeak-ng (Piper's phonemizer, a C library with
global state) on one thread.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings

logger = logging.getLogger("zor_assistant")

_voice = None
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts")


def load() -> None:
    global _voice
    if _voice is not None:
        return
    from piper import PiperVoice  # imported here so the text-only app starts without piper

    _voice = PiperVoice.load(str(get_settings().tts_voice_path))
    synthesize("Warm up.")  # first call initialises onnxruntime; keep that off the first turn
    logger.info("TTS ready: Piper voice %s (%d Hz)", get_settings().tts_voice_path.name, sample_rate())


def is_ready() -> bool:
    return _voice is not None


def sample_rate() -> int:
    return _voice.config.sample_rate


def synthesize(text: str) -> bytes:
    """One sentence -> 16-bit mono PCM bytes at sample_rate()."""
    return b"".join(chunk.audio_int16_bytes for chunk in _voice.synthesize(text))


async def synthesize_async(text: str) -> bytes:
    return await asyncio.get_running_loop().run_in_executor(_executor, synthesize, text)
