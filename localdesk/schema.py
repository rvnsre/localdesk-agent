"""Constrained JSON schema and dataclasses for model responses."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

import orjson

from .errors import PlanError

ACTION_FIELDS = {
    "move": {"x", "y", "duration"},
    "click": {"x", "y", "button", "clicks"},
    "scroll": {"x", "y", "amount"},
    "type": {"text"},
    "hotkey": {"keys"},
    "wait": {"seconds"},
}

JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTION_FIELDS)},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration": {"type": "number"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                    "clicks": {"type": "integer"},
                    "amount": {"type": "integer"},
                    "text": {"type": "string"},
                    "keys": {"type": "array", "items": {"type": "string"}},
                    "seconds": {"type": "number"},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "steps"],
}


@dataclass(frozen=True)
class Action:
    kind: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Plan:
    summary: str
    steps: tuple[Action, ...]


def parse_plan(raw: str) -> Plan:
    """Parse the JSON response; Markdown fences and extra text are rejected."""
    try:
        obj = orjson.loads(raw)
    except orjson.JSONDecodeError as exc:
        raise PlanError(f"The model did not return valid JSON: {exc.msg}.") from exc
    if not isinstance(obj, dict) or set(obj) != {"summary", "steps"}:
        raise PlanError("The response must contain only 'summary' and 'steps'.")
    if not isinstance(obj["summary"], str) or not isinstance(obj["steps"], list):
        raise PlanError("summary must be a string and steps must be a list.")
    bidi_controls = {"\u061c", "\u200e", "\u200f", *map(chr, range(0x202A, 0x202F)), *map(chr, range(0x2066, 0x206A))}
    if any(unicodedata.category(ch) == "Cc" or ch in bidi_controls for ch in obj["summary"]):
        raise PlanError("summary cannot contain terminal control characters.")
    steps: list[Action] = []
    for index, item in enumerate(obj["steps"], 1):
        if not isinstance(item, dict) or not isinstance(item.get("action"), str):
            raise PlanError(f"Action is missing from step {index}.")
        kind = item["action"]
        if kind not in ACTION_FIELDS:
            raise PlanError(f"Unsupported action: {kind}.")
        unknown = set(item) - ACTION_FIELDS[kind] - {"action"}
        if unknown:
            raise PlanError(f"Step {index} contains unknown fields: {', '.join(sorted(unknown))}.")
        steps.append(Action(kind, {k: v for k, v in item.items() if k != "action"}))
    return Plan(obj["summary"].strip(), tuple(steps))
