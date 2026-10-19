"""
Shared pieces for every tool: the Tool record (name + description + JSON schema + async
function), the per-call context, a friendly ToolError, and a tiny argument validator.

The validator is deliberately small (no jsonschema dependency): it only checks what our four
schemas use -- required keys, number/integer/string types and enums -- and drops unknown keys,
because a 3B model sometimes invents extra arguments.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


class ToolError(Exception):
    """A problem the member can fix (missing/invalid argument). The message is shown to the LLM
    so it can explain it to the member in plain words."""


@dataclass(frozen=True)
class ToolContext:
    """Facts the ORCHESTRATOR knows and the LLM must not choose, e.g. whose data to touch."""

    user_id: str


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema of the arguments object
    run: Callable[[dict, ToolContext], Awaitable[dict]]


_JSON_TYPES = {"number": (int, float), "integer": (int,), "string": (str,)}


def validate_args(schema: dict, args: Any) -> dict:
    """Return a cleaned copy of `args`, or raise ToolError explaining what is wrong."""
    if not isinstance(args, dict):
        raise ToolError("The arguments must be a JSON object.")
    properties: dict = schema.get("properties", {})
    clean: dict = {}
    for key, value in args.items():
        spec = properties.get(key)
        if spec is None or value is None or value == "":
            continue  # unknown or empty argument: ignore it
        expected = _JSON_TYPES[spec["type"]]
        # "80" for a number is common from a small model; accept numeric strings.
        if spec["type"] in ("number", "integer") and isinstance(value, str):
            try:
                value = float(value) if spec["type"] == "number" else int(float(value))
            except ValueError:
                raise ToolError(f"'{key}' must be a number.") from None
        if isinstance(value, bool) or not isinstance(value, expected):
            raise ToolError(f"'{key}' must be a {spec['type']}.")
        if "enum" in spec:
            value = str(value).lower()
            if value not in spec["enum"]:
                raise ToolError(f"'{key}' must be one of: {', '.join(spec['enum'])}.")
        clean[key] = value
    missing = [k for k in schema.get("required", []) if k not in clean]
    if missing:
        raise ToolError(f"Missing: {', '.join(missing)}.")
    return clean
