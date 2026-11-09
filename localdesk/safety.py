"""Action limits, screen bounds, and dangerous hotkey filters."""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass

from .config import Settings
from .errors import SafetyError
from .schema import Action, Plan

KEY_ALIASES = {"ctrl": "ctrl", "control": "ctrl", "cmd": "command", "win": "win", "meta": "command"}
VALID_KEYS = {
    "ctrl", "shift", "alt", "command", "win", "tab", "enter", "esc", "escape",
    "space", "backspace", "delete", "home", "end", "pageup", "pagedown",
    "left", "right", "up", "down", "c", "v", "x", "a", "z", "y", "s", "f",
    "w", "t", "r", "l", "d", "n", "o", "p", "plus", "minus",
} | {f"f{i}" for i in range(1, 13)}
BLOCKED_COMBOS = {
    frozenset({"ctrl", "alt", "delete"}),
    frozenset({"ctrl", "shift", "esc"}),
    frozenset({"command", "q"}),
    frozenset({"alt", "f4"}),
    frozenset({"win", "l"}),
    frozenset({"win", "r"}),
    frozenset({"ctrl", "alt", "t"}),
    frozenset({"command", "space"}),
    frozenset({"ctrl", "q"}),
}


@dataclass(frozen=True)
class ScreenBounds:
    width: int
    height: int


def validate_plan(plan: Plan, bounds: ScreenBounds, settings: Settings) -> Plan:
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (bounds.width, bounds.height)):
        raise SafetyError("Screen dimensions must be positive integers.")
    if len(plan.steps) > settings.max_steps:
        raise SafetyError(f"Plan has {len(plan.steps)} actions; the limit is {settings.max_steps}.")
    if len(plan.summary) > 500:
        raise SafetyError("Plan summary is too long.")
    estimated_seconds = 0.0
    for i, step in enumerate(plan.steps, 1):
        _validate_action(step, bounds, settings, i)
        if step.kind == "wait":
            estimated_seconds += float(step.args["seconds"])
        elif step.kind == "move":
            estimated_seconds += float(step.args.get("duration", 0.12))
        else:
            estimated_seconds += 0.08
    if estimated_seconds > settings.max_plan_seconds:
        raise SafetyError(
            f"Estimated plan duration is {estimated_seconds:.1f} seconds; "
            f"the limit is {settings.max_plan_seconds:.1f} seconds."
        )
    return plan


def _validate_action(action: Action, bounds: ScreenBounds, settings: Settings, index: int) -> None:
    a = action.args
    label = f"Step {index}"
    if action.kind in {"move", "click", "scroll"}:
        x = _integer(a.get("x"), f"{label}: x")
        y = _integer(a.get("y"), f"{label}: y")
        if not 0 <= x < bounds.width or not 0 <= y < bounds.height:
            raise SafetyError(f"{label}: coordinates are outside the screen ({x}, {y}).")
    if action.kind == "move":
        duration = _number(a.get("duration", 0.12), f"{label}: duration")
        if not 0 <= duration <= 2:
            raise SafetyError(f"{label}: move duration must be between 0 and 2 seconds.")
    elif action.kind == "click":
        if a.get("button", "left") not in {"left", "right", "middle"}:
            raise SafetyError(f"{label}: button must be left, right, or middle.")
        clicks = _integer(a.get("clicks", 1), f"{label}: clicks")
        if not 1 <= clicks <= 2:
            raise SafetyError(f"{label}: click count must be 1 or 2.")
    elif action.kind == "scroll":
        amount = _integer(a.get("amount"), f"{label}: amount")
        if not -8 <= amount <= 8:
            raise SafetyError(f"{label}: scroll amount must be between -8 and 8.")
    elif action.kind == "type":
        text = a.get("text")
        if not isinstance(text, str) or len(text) > settings.max_text_chars:
            raise SafetyError(f"{label}: text is missing or exceeds the character limit.")
        if not text:
            raise SafetyError(f"{label}: empty text is not allowed.")
        if not text.strip():
            raise SafetyError(f"{label}: whitespace-only text is not allowed.")
        if any((ord(ch) < 32 and ch not in "\t\n\r") or 0x7F <= ord(ch) <= 0x9F for ch in text):
            raise SafetyError(f"{label}: text containing control characters is not allowed.")
        if not settings.allow_shell_text and _looks_like_shell_command(text):
            raise SafetyError(f"{label}: text that looks like a shell command is blocked.")
    elif action.kind == "hotkey":
        keys = a.get("keys")
        if not isinstance(keys, list) or not 1 <= len(keys) <= 3:
            raise SafetyError(f"{label}: a hotkey must contain 1 to 3 keys.")
        normalized = [KEY_ALIASES.get(str(k).lower(), str(k).lower()) for k in keys]
        if sys.platform != "darwin":
            normalized = ["ctrl" if key == "command" else key for key in normalized]
        if any(k not in VALID_KEYS for k in normalized):
            raise SafetyError(f"{label}: the hotkey contains an unsupported key.")
        if "win" in normalized or frozenset(normalized) in BLOCKED_COMBOS:
            raise SafetyError(f"{label}: system-level hotkeys are blocked.")
        if len(set(normalized)) != len(normalized):
            raise SafetyError(f"{label}: duplicate keys are not allowed in a hotkey.")
    elif action.kind == "wait":
        seconds = _number(a.get("seconds"), f"{label}: seconds")
        if not 0 <= seconds <= 10:
            raise SafetyError(f"{label}: wait duration must be between 0 and 10 seconds.")
    else:
        raise SafetyError(f"{label}: unsupported action '{action.kind}'.")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SafetyError(f"{label} must be an integer.")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SafetyError(f"{label} must be a finite number.")
    return float(value)


def _looks_like_shell_command(text: str) -> bool:
    first = text.strip().splitlines()[0].strip().lower()
    commands = (
        r"sudo|rm\s|del\s|format\s|shutdown|reboot|powershell\b|pwsh\b|"
        r"cmd(?:\.exe)?\b|bash\b|sh\b|curl\b|wget\b|python\b|pip\b|"
        r"chmod\b|diskpart\b|reg\s+delete|osascript\b|xdg-open\b|"
        r"winget\b|apt(?:-get)?\b|brew\b"
    )
    return bool(re.match(rf"^({commands})", first))
