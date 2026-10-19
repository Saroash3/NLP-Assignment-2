"""
SpeechOutput: speaks one assistant reply WHILE it is still being generated.

  feed(token)  -> SentenceBuffer -> queue of sentences
  _worker()    -> takes sentences in order, synthesizes each in the TTS thread, sends an
                  `audio` event (base64 PCM, increasing seq) as soon as it is ready
  finish()     -> speaks the leftover text, waits for the queue, sends `audio_end`

Token streaming never waits for TTS: feed() only puts text on a queue, and the worker runs as
a separate task. If TTS fails, the member still gets the full text reply plus one error event,
and the turn still ends normally (no hang).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time

from app.schemas import AudioEndEvent, AudioEvent, ErrorEvent, VoiceStateEvent
from app.voice import tts
from app.voice.sentence_buffer import SentenceBuffer

logger = logging.getLogger("zor_assistant")


class SpeechOutput:
    def __init__(self, send, timings):
        self._send = send  # send_extra: audio events are Assignment 3 events
        self._timings = timings
        self._buffer = SentenceBuffer()
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._seq = 0
        self._failed = False
        self._worker_task = asyncio.create_task(self._worker())

    async def feed(self, token: str) -> None:
        for sentence in self._buffer.push(token):
            self._queue.put_nowait(sentence)

    async def finish(self) -> None:
        rest = self._buffer.flush()
        if rest:
            self._queue.put_nowait(rest)
        self._queue.put_nowait(None)  # "no more sentences"
        await self._worker_task
        await self._send(AudioEndEvent())

    async def close(self) -> None:
        """Always called (finally:). Stops the worker if the turn ended early (error/disconnect)."""
        if not self._worker_task.done():
            self._worker_task.cancel()

    async def _worker(self) -> None:
        while (sentence := await self._queue.get()) is not None:
            if self._failed:
                continue  # keep draining so finish() returns; the text reply is unaffected
            ready_at = time.perf_counter()
            try:
                pcm = await tts.synthesize_async(sentence)
            except Exception:
                logger.exception("TTS failed for %r", sentence)
                self._failed = True
                await self._send(ErrorEvent(message="Voice output failed -- the reply is shown as "
                                            "text only.", code="tts_error"))
                continue
            if self._seq == 0:
                await self._send(VoiceStateEvent(state="speaking"))
            await self._send(AudioEvent(seq=self._seq, sample_rate=tts.sample_rate(),
                                        data=base64.b64encode(pcm).decode("ascii")))
            if self._seq == 0:  # first audio of the turn: record the latencies
                now = time.perf_counter()
                self._timings.tts_first_audio_ms = (now - ready_at) * 1000
                if self._timings.end_of_speech_at is not None:
                    self._timings.total_ms = (now - self._timings.end_of_speech_at) * 1000
            self._seq += 1
