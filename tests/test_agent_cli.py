from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from localdesk.agent import Agent
from localdesk.cli import build_parser
from localdesk.config import Settings
from localdesk.errors import LocalDeskError
from localdesk.schema import Plan
from localdesk.screen import ScreenFrame


class FakeDesktop:
    def __init__(self):
        self.dimensions = (1000, 600)
        self.executed = []

    def size(self):
        return self.dimensions

    def execute(self, plan, max_seconds=120):
        self.executed.append((plan, max_seconds))


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings().validated()
        self.desktop = FakeDesktop()
        self.agent_patcher = patch("localdesk.agent.LocalModel")
        self.model_cls = self.agent_patcher.start()
        self.addCleanup(self.agent_patcher.stop)
        self.model = self.model_cls.return_value
        self.model.plan.return_value = '{"summary":"ok","steps":[{"action":"click","x":50,"y":30}]}'
        self.capture_patcher = patch("localdesk.agent.CaptureSession")
        self.capture_cls = self.capture_patcher.start()
        self.addCleanup(self.capture_patcher.stop)
        self.capture_cls.return_value.unchanged.return_value = True
        self.frame_patcher = patch.object(self.capture_cls.return_value, "capture", return_value=ScreenFrame("data:", 100, 60, 1000, 600))
        self.frame_patcher.start()
        self.addCleanup(self.frame_patcher.stop)
        self.agent = Agent(self.settings, self.desktop)

    def test_propose_scales_and_validates_model_coordinates(self):
        plan = self.agent.propose("click button")
        self.assertEqual(plan.steps[0].args, {"x": 500, "y": 300})
        self.model.plan.assert_called_once_with("click button", "data:", 100, 60)

    def test_run_requires_approval_and_rechecks_display_size(self):
        with patch("builtins.print"):
            self.assertFalse(self.agent.run("x", lambda: False))
        self.assertEqual(self.desktop.executed, [])
        with patch("builtins.print"):
            self.assertTrue(self.agent.run("x", lambda: True))
        self.assertEqual(self.desktop.executed[0][1], self.settings.max_plan_seconds)
        def resize_during_confirmation():
            self.desktop.dimensions = (1200, 700)
            return True

        with patch("builtins.print"), self.assertRaises(LocalDeskError):
            self.agent.run("x", resize_during_confirmation)

    def test_rejects_empty_or_oversized_goal_before_api_call(self):
        with self.assertRaises(LocalDeskError):
            self.agent.propose("   ")
        small = Agent(Settings(max_goal_chars=2).validated(), self.desktop)
        with self.assertRaises(LocalDeskError):
            small.propose("long")


class CliTests(unittest.TestCase):
    def test_cli_options(self):
        args = build_parser().parse_args(["--dry-run", "Find the button"])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.goal, "Find the button")


if __name__ == "__main__":
    unittest.main()
