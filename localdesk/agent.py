"""Capture a screen, prepare a plan, request approval, and execute it."""

from __future__ import annotations

from collections.abc import Callable

from .automation import Desktop
from .config import Settings
from .errors import LocalDeskError
from .model import LocalModel
from .safety import ScreenBounds, validate_plan
from .schema import parse_plan
from .screen import map_plan_to_input
from .capture import CaptureSession
from .performance import Timings


class Agent:
    def __init__(self, settings: Settings, desktop: Desktop | None = None) -> None:
        self.settings = settings
        self.desktop = desktop or Desktop()
        self.model = LocalModel(settings)
        self.capture = CaptureSession(settings.capture_backend)
        self.desktop.wait_for_change = self.capture.wait_for_change
        self.timings = Timings()
        self._planned_size: tuple[int, int] | None = None

    def propose(self, goal: str):
        if not goal.strip():
            raise LocalDeskError("Task cannot be empty.")
        if len(goal) > self.settings.max_goal_chars:
            raise LocalDeskError(
                f"Task has {len(goal)} characters; the limit is {self.settings.max_goal_chars}."
            )
        self.timings = Timings()
        input_size = self.desktop.size()
        frame = self._capture_frame(self.settings.screenshot_width, self.settings.screenshot_jpeg_quality, input_size)
        with self.timings.measure("model"):
            raw = self.model.plan(goal, frame.image_uri, frame.image_width, frame.image_height)
        with self.timings.measure("validation"):
            plan = parse_plan(raw)
        if not plan.steps and self.settings.profile == "fast":
            frame = self._capture_frame(1920, 85, input_size)
            with self.timings.measure("model"):
                raw = self.model.plan(goal, frame.image_uri, frame.image_width, frame.image_height)
            with self.timings.measure("validation"):
                plan = parse_plan(raw)
        with self.timings.measure("validation"):
            plan = map_plan_to_input(plan, frame)
            self._planned_size = input_size
            return validate_plan(plan, ScreenBounds(frame.input_width, frame.input_height), self.settings)

    def _capture_frame(self, width, quality, size):
        import time
        start = time.perf_counter()
        frame = self.capture.capture(width, quality, size)
        total = time.perf_counter() - start
        details = self.capture.last_timings
        details = details if isinstance(details, dict) else {}
        for name in ("capture", "encode"):
            self.timings.stages[name] = self.timings.stages.get(name, 0) + details.get(name, 0)
        self.timings.stages["prepare_other"] = self.timings.stages.get("prepare_other", 0) + max(0, total - sum(details.values()))
        return frame

    def run(self, goal: str, approve: Callable[[], bool]) -> bool:
        plan = self.propose(goal)
        print(f"\nPlan: {plan.summary}")
        if not plan.steps:
            print("The model did not find a clear, safe action; nothing was done.")
            return False
        from .automation import describe_action
        for index, action in enumerate(plan.steps, 1):
            print(f"  {index}. {describe_action(action)}")
        with self.timings.measure("approval"):
            approved = approve()
        if not approved:
            print("The user rejected the plan.")
            return False
        if self.desktop.size() != self._planned_size:
            raise LocalDeskError("The screen size changed while approval was pending; generate a new plan.")
        with self.timings.measure("freshness"):
            if not self.capture.unchanged():
                raise LocalDeskError("The screen changed after planning; generate and approve a new plan.")
        with self.timings.measure("execute"):
            self.desktop.execute(plan, max_seconds=self.settings.max_plan_seconds)
        return True

    def close(self):
        try:
            self.model.close()
        finally:
            self.capture.close()
