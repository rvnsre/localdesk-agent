"""PyAutoGUI execution layer with cross-platform key normalization."""

from __future__ import annotations

import math
import time
import sys
from typing import Callable

from .errors import AutomationError
from .console import configure_console
from .schema import Action, Plan


class Desktop:
    def __init__(self, announce: Callable[[str], None] = print) -> None:
        configure_console()
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            # No implicit per-action sleep; explicit move/wait timings remain validated.
            pyautogui.PAUSE = 0.0
            self.pg = pyautogui
        except Exception as exc:
            raise AutomationError(f"Could not initialize PyAutoGUI: {exc}") from exc
        self.announce = announce

    def size(self) -> tuple[int, int]:
        size = self.pg.size()
        return int(size.width), int(size.height)

    def execute(self, plan: Plan, max_seconds: float = 120.0) -> None:
        if not isinstance(max_seconds, (int, float)) or isinstance(max_seconds, bool) or not math.isfinite(max_seconds) or max_seconds <= 0:
            raise AutomationError("Execution time limit must be a positive finite number.")
        deadline = time.monotonic() + max_seconds
        for index, action in enumerate(plan.steps, 1):
            if time.monotonic() >= deadline:
                raise AutomationError(
                    f"Execution reached the {max_seconds:.0f}-second limit; remaining actions were stopped."
                )
            self.announce(f"[{index}/{len(plan.steps)}] {describe_action(action)}")
            self._execute_one(action)

    def _execute_one(self, action: Action) -> None:
        a = action.args
        try:
            if action.kind == "move":
                self.pg.moveTo(a["x"], a["y"], duration=a.get("duration", 0.12))
            elif action.kind == "click":
                self.pg.click(a["x"], a["y"], clicks=a.get("clicks", 1), button=a.get("button", "left"))
            elif action.kind == "scroll":
                self.pg.moveTo(a["x"], a["y"], duration=0)
                self.pg.scroll(a["amount"])
            elif action.kind == "type":
                self._type_text(a["text"])
            elif action.kind == "hotkey":
                self.pg.hotkey(*[_pyautogui_key(k) for k in a["keys"]])
            elif action.kind == "wait":
                time.sleep(a["seconds"])
            else:
                raise AutomationError(f"Unsupported action: {action.kind}.")
        except self.pg.FailSafeException:
            raise AutomationError("Fail-safe stop: the pointer reached the upper-left corner of the screen.")
        except Exception as exc:
            raise AutomationError(f"{action.kind} action failed: {exc}") from exc

    def _type_text(self, text: str) -> None:
        """Use PyAutoGUI for plain ASCII; restore the clipboard after Unicode or multiline paste."""
        if text.isascii() and not any(ch in text for ch in "\r\n\t"):
            self.pg.write(text, interval=0)
            return
        try:
            import pyperclip
            previous = pyperclip.paste()
        except Exception as exc:
            raise AutomationError(
                "Clipboard access is required to type Unicode or multiline text. "
                "Install a clipboard utility or use plain ASCII text."
            ) from exc
        paste_key = "command" if sys.platform == "darwin" else "ctrl"
        try:
            pyperclip.copy(text)
            self.pg.hotkey(paste_key, "v")
            time.sleep(0.15)
        finally:
            try:
                pyperclip.copy(previous)
            except Exception as exc:
                self.announce(f"Warning: the previous clipboard text could not be restored: {exc}")


def _pyautogui_key(key: str) -> str:
    aliases = {"control": "ctrl", "cmd": "command", "meta": "command", "escape": "esc"}
    normalized = aliases.get(key.lower(), key.lower())
    if normalized == "command" and sys.platform != "darwin":
        return "ctrl"
    return normalized


def describe_action(action: Action) -> str:
    a = action.args
    if action.kind == "move":
        return f"move ({a.get('x')}, {a.get('y')}) in {a.get('duration', 0.12)} s"
    if action.kind == "click":
        count = a.get("clicks", 1)
        button = a.get("button", "left")
        return f"click {button} ({a.get('x')}, {a.get('y')})" + (f" x{count}" if count > 1 else "")
    if action.kind == "scroll":
        return f"scroll {a.get('amount')} at ({a.get('x')}, {a.get('y')})"
    if action.kind == "type":
        return f"type: {a['text']!r}"
    if action.kind == "hotkey":
        return "hotkey: " + "+".join(a["keys"])
    return f"wait {a.get('seconds')} s"
