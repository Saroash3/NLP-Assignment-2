"""
Speech-to-text with faster-whisper (Whisper on CTranslate2), fully local.

Model choice: on the GPU, `large-v3-turbo` (float16) forced to English: large-v3's encoder with a
small decoder, so large-model robustness to accents at ~185 ms per question. It replaced
`small.en` after a live test where an accented "Hi Nova" became "Hain Allah" / "Hi Noah"; on
clear test voices turbo + the vocabulary prompt measured 4-8% word errors vs 12-15% for
`small.en` before. On CPU, `base.en` (int8, ~300 ms). device="auto" tries CUDA first.

VOCABULARY is passed as Whisper's initial prompt: names it could never guess (Nova, the trainers,
branches, plans). Measured: this alone roughly halved the word errors.

The model is loaded ONCE at startup and shared by every connection. transcribe() is heavy,
so it runs in a 2-thread executor: two users can be transcribed at the same time, and the
event loop (other users' text chat) is never blocked.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from app.config import get_settings

logger = logging.getLogger("zor_assistant")

_model = None
device_used = "none"
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="asr")


def _add_cuda_dlls_to_path() -> None:
    """Windows: the cuBLAS/cuDNN DLLs come from the nvidia-* pip wheels; make them findable."""
    nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for bin_dir in nvidia.glob("*/bin"):
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


def load() -> None:
    global _model, device_used
    if _model is not None:
        return
    from faster_whisper import WhisperModel

    settings = get_settings()
    attempts = [("cuda", "float16", "large-v3-turbo"), ("cpu", "int8", "base.en")]
    if settings.asr_device != "auto":
        attempts = [a for a in attempts if a[0] == settings.asr_device]
    _add_cuda_dlls_to_path()
    for device, compute_type, default_model in attempts:
        name = default_model if settings.asr_model == "auto" else settings.asr_model
        try:
            _model = WhisperModel(name, device=device, compute_type=compute_type, num_workers=2)
            # Warm-up (and the real check that the CUDA DLLs load). Noise, not silence: silence
            # skips the decoder, and the first real call then took 1.5 s instead of ~0.1 s.
            transcribe(noise())
            device_used = f"{name} on {device} ({compute_type})"
            logger.info("ASR ready: faster-whisper %s", device_used)
            return
        except Exception as e:
            _model = None
            logger.warning("ASR could not start on %s (%s); trying the next option", device, e)
    raise RuntimeError("faster-whisper could not be loaded on any device")


def is_ready() -> bool:
    return _model is not None


def noise(seconds: float = 2.0) -> np.ndarray:
    """Low-level noise for warm-ups (see load())."""
    return (np.random.default_rng(0).standard_normal(int(16000 * seconds)) * 0.1).astype(np.float32)


def warm_up() -> None:
    """Wake the GPU after a long idle: a short pass that may decode only a few tokens. (A full
    transcription of noise can hallucinate a long text; two of those at once blocked both ASR
    threads for ~5 s in a test.)"""
    segments, _ = _model.transcribe(noise(0.5), language="en", beam_size=1, max_new_tokens=4)
    list(segments)


async def warm_up_async() -> None:
    await asyncio.get_running_loop().run_in_executor(_executor, warm_up)


VOCABULARY = (
    "Hi Nova! Zor Fitness Club: F-7, G-11 and Bahria Town branches; Standard, Plus, Elite and Ladies "
    "Only plans; trainers Ali Raza, Bilal Khattak, Farah Naz, Hamza Qureshi, Hira Saleem, Mahnoor "
    "Rizvi, Sana Iftikhar, Usman Tariq, Zeeshan Haider; nutritionist Kamran Baig, physio Dr. Ayesha "
    "Malik. Admission fee, membership plans, freeze, "
    "guest pass, plans for men and women, males and females, BMI, protein, one rep max, workout "
    "schedule."  # "admission fee" was heard as "Mission P", "males" as "wheels"
)


# Words Whisper keeps choosing for this domain's names. Nobody at the gym is called Noah: an
# accented "Hi Nova" was heard as "Hi Noah" even with Nova in the vocabulary prompt.
FIXES = [
    # The assistant's own name, heard live as "Noah", "Hain Allah" and "Dova". Words that sound
    # like it never occur in a real gym question, so they are all mapped back to "Nova".
    (re.compile(r"\b(?:Noah?|Dova|Doha|Nowa|Nava|Noba|Mova|Nover|Novah)\b"), "Nova"),
    # "Standard Planes": retrieval then found nothing about plans (live test). No planes at a gym.
    (re.compile(r"\b[Pp]lanes\b"), "plans"),
    (re.compile(r"\b(\d+)[ -](?:buck|month) plane\b"), r"\1 month plan"),  # "12 buck plane" (live)
    (re.compile(r"\b[Pp]lane\b"), "plan"),
    # A clipped "ad-" turned "admission fee" into "Mission P" / "Mission fee" (live test).
    (re.compile(r"\b(?<!ad)[Mm]ission (?:fee|P)\b"), "admission fee"),
]


def normalize(audio: np.ndarray) -> np.ndarray:
    """Bring a quiet mic up to a normal level (the browser's auto-gain is off, see
    useMicrophone.ts). Measured live: peaks of 0.04-0.3 where test audio reaches ~1.0. Gain is
    capped at 20x so near-silence is not blown up into loud noise."""
    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    return audio * min(0.9 / peak, 20.0) if peak > 0.01 else audio


def transcribe(audio: np.ndarray, member_name: str | None = None) -> str:
    """16 kHz mono float32 in [-1, 1] -> English text. `member_name` (from the CRM profile) is
    added to the vocabulary, so a returning member's unusual name is spelt right."""
    # As a natural sentence: a label like "Member: Sarosh." was copied into the transcript
    # ('Member:"Okay, tell me about your plans."').
    prompt = f"Hi Nova, I'm {member_name}! {VOCABULARY.removeprefix('Hi Nova! ')}" if member_name else VOCABULARY
    segments, _ = _model.transcribe(
        normalize(audio), language="en", beam_size=1,  # greedy: beam 5 cost +60 ms, gained nothing
        condition_on_previous_text=False, initial_prompt=prompt,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    for wrong, right in FIXES:
        text = wrong.sub(right, text)
    return text


async def transcribe_async(audio: np.ndarray, member_name: str | None = None) -> str:
    return await asyncio.get_running_loop().run_in_executor(_executor, transcribe, audio, member_name)
