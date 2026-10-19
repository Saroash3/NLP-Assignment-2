"""
Turns a stream of LLM tokens into speakable sentences, as early as possible.

push(token) returns every sentence completed by that token; flush() returns what is left at
the end. A sentence ends at . ! ? or a newline followed by a space/newline. The FIRST chunk of a
reply may also end at a comma once it is long enough: it lets the first audio start sooner,
which is the latency that matters most.
"""
from __future__ import annotations

import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
CLAUSE_END = re.compile(r"(?<=[,;:])\s+")
FIRST_CHUNK_MIN_CHARS = 40  # only break the first chunk at a comma after this many characters
MARKDOWN = re.compile(r"[*_#`>|]+")


def clean_for_speech(text: str) -> str:
    """Strip markdown symbols and odd spacing that would be read out or confuse the TTS."""
    text = MARKDOWN.sub("", text).replace(" -- ", ", ").replace("--", ", ")
    return re.sub(r"\s+", " ", text).strip()


class SentenceBuffer:
    def __init__(self) -> None:
        self._text = ""
        self._first = True

    def _cut(self, pattern: re.Pattern) -> list[str]:
        parts = pattern.split(self._text)
        self._text = parts.pop()  # the last part has no ending yet: keep buffering it
        return parts

    def push(self, token: str) -> list[str]:
        self._text += token
        done = self._cut(SENTENCE_END)
        if self._first and not done and len(self._text) >= FIRST_CHUNK_MIN_CHARS:
            done = self._cut(CLAUSE_END)
        sentences = [s for s in (clean_for_speech(p) for p in done) if s]
        if sentences:
            self._first = False
        return sentences

    def flush(self) -> str | None:
        rest, self._text = clean_for_speech(self._text), ""
        return rest or None
