"""Capture a screen, prepare a plan, request approval, and execute it."""

from __future__ import annotations

from collections.abc import Callable

from .automation import Desktop
from .config import Settings
from .errors import LocalDeskError
from .model import LocalModel
from .safety import ScreenBounds, validate_plan
from .schema import parse_plan
from .screen import capture_screen, map_plan_to_input


class Agent:
    def __init__(self, settings: Settings, desktop: Desktop | None = None) -> None:
        self.settings = settings
        self.desktop = desktop or Desktop()
        self.model = LocalModel(settings)
        self._planned_size: tuple[int, int] | None = None

    def propose(self, goal: str):
        if not goal.strip():
            raise LocalDeskError("Task cannot be empty.")
        if len(goal) > self.settings.max_goal_chars:
            raise LocalDeskError(
                f"Task has {len(goal)} characters; the limit is {self.settings.max_goal_chars}."
            )
        input_size = self.desktop.size()
        frame = capture_screen(
            self.settings.screenshot_width,
            self.settings.screenshot_jpeg_quality,
            input_size,
        )
        raw = self.model.plan(goal, frame.image_uri, frame.image_width, frame.image_height)
        plan = parse_plan(raw)
        plan = map_plan_to_input(plan, frame)
        self._planned_size = input_size
        return validate_plan(
            plan,
            ScreenBounds(frame.input_width, frame.input_height),
            self.settings,
        )

    def run(self, goal: str, approve: Callable[[], bool]) -> bool:
        plan = self.propose(goal)
        print(f"\nPlan: {plan.summary}")
        if not plan.steps:
            print("The model did not find a clear, safe action; nothing was done.")
            return False
        from .automation import describe_action
        for index, action in enumerate(plan.steps, 1):
            print(f"  {index}. {describe_action(action)}")
        if not approve():
            print("The user rejected the plan.")
            return False
        if self.desktop.size() != self._planned_size:
            raise LocalDeskError("The screen size changed while approval was pending; generate a new plan.")
        self.desktop.execute(plan, max_seconds=self.settings.max_plan_seconds)
        return True
