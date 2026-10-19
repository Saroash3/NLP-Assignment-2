"""
VoiceSession: the microphone side of ONE WebSocket connection.

The browser streams 16 kHz mono 16-bit PCM as binary frames. feed() cuts them into 32 ms
windows, scores each with the streaming VAD, and runs this small state machine:

  waiting --(window with speech prob >= 0.5)--> in speech
     ^  (pre-roll: the last ~0.5 s before speech is kept, so the first syllable isn't cut)
     |
  in speech: every ~0.7 s, a PARTIAL transcript runs in the background (live captions)
  in speech --(0.6 s of windows below 0.35, or 15 s total)--> END OF SPEECH:
     final transcript (faster-whisper) -> returned to main.py, which runs the normal turn

Blips shorter than 0.25 s of speech are ignored (a cough, a click). All model calls run in
worker threads, so other users are never blocked.
"""
from __future__ import annotations

import asyncio
import logging
import time
import wave
from collections import deque
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.schemas import ErrorEvent, TranscriptEvent, VoiceStateEvent
from app.turn import TurnTimings
from app.voice import asr, tts, vad

logger = logging.getLogger("zor_assistant")

SPEECH_PROB = 0.5  # a window above this starts speech
SILENCE_PROB = 0.35  # below this counts as silence (hysteresis: no flicker between the two)
END_SILENCE_WINDOWS = 19  # 19 x 32 ms ~ 0.6 s of silence = end of speech (0.5 s cut off short pauses)
MIN_SPEECH_WINDOWS = 8  # < ~0.25 s of real speech = noise, ignored
PRE_ROLL_WINDOWS = 16  # ~0.5 s kept from before the speech started (0.3 s cut a soft "ad-")
PARTIAL_EVERY_WINDOWS = 22  # a live partial transcript every ~0.7 s
MAX_SPEECH_WINDOWS = 470  # ~15 s: force the end of a very long utterance


UTTERANCE_DIR = Path(__file__).resolve().parents[2] / "logs" / "utterances"


class VoiceUnavailable(Exception):
    pass


def _save_wav(audio: np.ndarray) -> None:
    """Debug only (Settings.voice_debug_save): keep the exact audio Whisper got, to tune ASR on
    real voices instead of synthetic ones."""
    UTTERANCE_DIR.mkdir(parents=True, exist_ok=True)
    path = UTTERANCE_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


class VoiceSession:
    def __init__(self, send_extra):
        self._send = send_extra
        self.active = False
        self._vad = vad.StreamingVAD()
        self._utterance_id = 0
        self.member_name: str | None = None  # from the CRM profile; helps Whisper spell it (main.py)
        self._new_utterance()

    def _new_utterance(self) -> None:
        self._utterance_id += 1  # partial transcripts of an older utterance are then ignored
        self._leftover = np.empty(0, dtype=np.float32)
        self._pre_roll: deque[np.ndarray] = deque(maxlen=PRE_ROLL_WINDOWS)
        self._speech: list[np.ndarray] = []
        self._in_speech = False
        self._voiced = self._silence = self._since_partial = 0
        self._partial_task: asyncio.Task | None = None

    # --- control messages ---

    async def start(self) -> None:
        if not (asr.is_ready() and tts.is_ready() and vad.is_ready()):
            raise VoiceUnavailable("Voice mode isn't available: the speech models are not loaded "
                                   "on the server. Text chat still works.")
        self.active = True
        await self.listen_again()

    async def stop(self) -> None:
        self.active = False
        self._new_utterance()
        await self._send(VoiceStateEvent(state="idle"))

    async def listen_again(self) -> None:
        """Fresh state, then 'listening' (called at start and after every spoken turn)."""
        self._vad.reset()
        self._new_utterance()
        if self.active:
            await self._send(VoiceStateEvent(state="listening"))

    # --- audio ---

    async def feed(self, data: bytes) -> tuple[str, TurnTimings] | None:
        """Process one audio frame. Returns (final transcript, timings) at the end of an
        utterance, else None."""
        if not self.active or len(data) % 2:
            return None
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        audio = np.concatenate([self._leftover, samples])
        n = len(audio) // vad.WINDOW
        self._leftover = audio[n * vad.WINDOW:]
        if n == 0:
            return None
        windows = audio[: n * vad.WINDOW].reshape(n, vad.WINDOW)
        probs = await asyncio.to_thread(self._vad.probabilities, windows)
        self._log_level(windows, probs)

        for window, prob in zip(windows, probs):
            if not self._in_speech:
                self._pre_roll.append(window)
                if prob >= SPEECH_PROB:
                    self._in_speech, self._speech, self._voiced = True, list(self._pre_roll), 1
                continue
            self._speech.append(window)
            self._since_partial += 1
            if prob < SILENCE_PROB:
                self._silence += 1
            else:
                self._silence = 0
                self._voiced += 1
            if self._silence >= END_SILENCE_WINDOWS or len(self._speech) >= MAX_SPEECH_WINDOWS:
                return await self._end_of_utterance()

        if self._in_speech and self._since_partial >= PARTIAL_EVERY_WINDOWS and (
            self._partial_task is None or self._partial_task.done()
        ):
            self._since_partial = 0
            self._partial_task = asyncio.create_task(
                self._partial(np.concatenate(self._speech), self._utterance_id))
        return None

    def _log_level(self, windows: np.ndarray, probs: np.ndarray) -> None:
        """Diagnostics: every ~3 s of received audio, log the mic level and best VAD score, so
        "it isn't hearing me" can be told apart from "no audio arrives" in the server log."""
        if not getattr(self, "_stats_windows", 0):
            self._stats_since = time.perf_counter()
        self._stats_windows = getattr(self, "_stats_windows", 0) + len(windows)
        self._stats_peak = max(getattr(self, "_stats_peak", 0.0), float(np.abs(windows).max()))
        self._stats_prob = max(getattr(self, "_stats_prob", 0.0), float(probs.max()))
        if self._stats_windows >= 94:  # 94 x 32 ms ~ 3 s
            # "received in" > ~3.1 s = audio arrives slower than real time (browser throttling,
            # e.g. a hidden tab) -- one of the causes of "it stopped hearing me".
            logger.info("Mic audio: %.1f s received in %.1f s, peak level %.3f, best speech prob %.2f",
                        self._stats_windows * vad.WINDOW / 16000, time.perf_counter() - self._stats_since,
                        self._stats_peak, self._stats_prob)
            if self._stats_peak == 0.0 and not getattr(self, "_warned_silent", False):
                # Exactly zero = a muted or wrong input device (real silence is never all zeros).
                self._warned_silent = True
                asyncio.get_running_loop().create_task(self._send(ErrorEvent(
                    message="Your microphone is sending silence. Check the mic-mute key and the "
                    "microphone chosen in the browser's site settings.", code="mic_silent")))
            self._stats_windows, self._stats_peak, self._stats_prob = 0, 0.0, 0.0

    async def _partial(self, audio: np.ndarray, utterance_id: int) -> None:
        try:
            text = await asr.transcribe_async(audio, self.member_name)
        except Exception:
            logger.exception("Partial transcription failed")
            return
        if utterance_id != self._utterance_id:
            return  # the utterance already ended; this partial is stale
        if text:
            await self._send(TranscriptEvent(text=text, final=False))

    async def _end_of_utterance(self) -> tuple[str, TurnTimings] | None:
        timings = TurnTimings(end_of_speech_at=time.perf_counter())
        audio, voiced = np.concatenate(self._speech), self._voiced
        self._new_utterance()
        if voiced < MIN_SPEECH_WINDOWS:
            return None  # just a noise blip
        await self._send(VoiceStateEvent(state="transcribing"))
        if get_settings().voice_debug_save:
            asyncio.create_task(asyncio.to_thread(_save_wav, audio))
        try:
            text = await asr.transcribe_async(audio, self.member_name)
        except Exception:
            logger.exception("Final transcription failed")
            await self._send(ErrorEvent(message="Sorry, I couldn't transcribe that -- please try "
                                        "again.", code="asr_error"))
            text = ""
        timings.asr_ms = (time.perf_counter() - timings.end_of_speech_at) * 1000
        if not text:
            await self._send(VoiceStateEvent(state="listening"))
            return None
        await self._send(TranscriptEvent(text=text, final=True))
        logger.info("Heard: %s", text)
        return text, timings
