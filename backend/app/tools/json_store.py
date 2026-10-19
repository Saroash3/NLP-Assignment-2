"""
A tiny JSON-file store used by workout_schedule and user_profile.

Every read-modify-write runs in a worker thread (asyncio.to_thread), so file I/O never blocks
the event loop, and holds a threading.Lock, so two users saving at the same moment cannot
overwrite each other's change. Writes go to a temp file first and are then renamed over the
real file (os.replace is atomic), so a crash mid-write never leaves a half-written file.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            # A corrupted file must not take the tool down forever: start fresh, keep a backup.
            self.path.replace(self.path.with_suffix(".corrupt.json"))
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def _update_sync(self, change: Callable[[dict], Any]) -> Any:
        with self._lock:
            data = self._read()
            result = change(data)  # `change` edits `data` in place and returns what the caller wants
            self._write(data)
            return result

    def _get_sync(self, key: str) -> Any:
        with self._lock:
            return self._read().get(key)

    async def update(self, change: Callable[[dict], Any]) -> Any:
        return await asyncio.to_thread(self._update_sync, change)

    async def get(self, key: str) -> Any:
        return await asyncio.to_thread(self._get_sync, key)
