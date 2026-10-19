"""
Voice activity detection with Silero VAD (ONNX, CPU), used in STREAMING mode.

The model file ships inside the faster-whisper package (assets/silero_vad_v6.onnx), so there is
nothing extra to download. It scores 512-sample windows (32 ms at 16 kHz) with the speech
probability 0..1. To work on a live stream, each connection keeps its own LSTM state (h, c) and
the last 64 samples ("context") between calls -- that is what StreamingVAD holds. The ONNX
session itself is loaded once and shared (onnxruntime sessions are thread-safe).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

WINDOW = 512  # samples per VAD window at 16 kHz = 32 ms
CONTEXT = 64  # samples of the previous window the model expects in front of each window

_session = None


def load() -> None:
    global _session
    if _session is None:
        import faster_whisper
        import onnxruntime as ort

        path = Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"
        options = ort.SessionOptions()
        options.inter_op_num_threads = options.intra_op_num_threads = 1  # tiny model: 1 thread is fastest
        _session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])


def is_ready() -> bool:
    return _session is not None


class StreamingVAD:
    """Per-connection VAD state."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)

    def probabilities(self, windows: np.ndarray) -> np.ndarray:
        """windows: [n, 512] float32 consecutive audio -> [n] speech probabilities."""
        previous = np.concatenate([self._context[None, :], windows[:-1, -CONTEXT:]])
        batch = np.concatenate([previous, windows], axis=1)  # [n, 576]
        probs, self._h, self._c = _session.run(None, {"input": batch, "h": self._h, "c": self._c})
        self._context = windows[-1, -CONTEXT:].copy()
        return np.asarray(probs).reshape(-1)
