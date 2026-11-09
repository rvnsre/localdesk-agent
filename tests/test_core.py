from __future__ import annotations

import math
import unittest
from unittest.mock import patch

from localdesk.config import Settings
from localdesk.errors import ConfigurationError, PlanError, SafetyError
from localdesk.safety import ScreenBounds, validate_plan
from localdesk.schema import Action, Plan, parse_plan


class SettingsTests(unittest.TestCase):
    def test_default_settings_are_valid(self):
        self.assertEqual(Settings().validated(), Settings())

    def test_remote_api_requires_explicit_opt_in(self):
        with self.assertRaises(ConfigurationError):
            Settings(base_url="http://192.168.1.8:1234/v1").validated()
        self.assertEqual(
            Settings(base_url="https://ai.example/v1", allow_remote_api=True).validated().base_url,
            "https://ai.example/v1",
        )

    def test_rejects_url_credentials_controls_and_nan_timeouts(self):
        for settings in (
            Settings(base_url="http://user:pass@localhost/v1"),
            Settings(base_url="http://localhost/v1?key=secret"),
            Settings(base_url="http://localhost/v1\n"),
            Settings(base_url="http://localhost:70000/v1"),
            Settings(timeout=math.nan),
            Settings(max_plan_seconds=math.inf),
        ):
            with self.subTest(settings=settings), self.assertRaises(ConfigurationError):
                settings.validated()

    def test_from_env_reads_limits_and_rejects_bad_integer(self):
        with patch.dict("os.environ", {"LOCALDESK_MAX_STEPS": "7", "LOCALDESK_MODEL": "vision"}):
            settings = Settings.from_env()
        self.assertEqual(settings.max_steps, 7)
        self.assertEqual(settings.model, "vision")
        with patch.dict("os.environ", {"LOCALDESK_MAX_STEPS": "abc"}):
            with self.assertRaises(ConfigurationError):
                Settings.from_env()


class PlanParserTests(unittest.TestCase):
    def test_parses_supported_actions(self):
        raw = '{"summary":"Naviqasiya","steps":[{"action":"click","x":4,"y":6}]}'
        plan = parse_plan(raw)
        self.assertEqual(plan.steps, (Action("click", {"x": 4, "y": 6}),))

    def test_rejects_fences_unknown_fields_and_bad_action(self):
        cases = (
            "```json\n{\"summary\":\"x\",\"steps\":[]}\n```",
            '{"summary":"x","steps":[],"extra":true}',
            '{"summary":"x","steps":[{"action":"shell"}]}',
            '{"summary":"x\\u001b[31m","steps":[]}',
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(PlanError):
                parse_plan(raw)

    def test_rejects_non_object_steps(self):
        with self.assertRaises(PlanError):
            parse_plan('{"summary":"x","steps":[null]}')


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings().validated()
        self.bounds = ScreenBounds(100, 80)

    def test_accepts_bounded_click(self):
        plan = Plan("click", (Action("click", {"x": 99, "y": 79}),))
        self.assertIs(validate_plan(plan, self.bounds, self.settings), plan)

    def test_rejects_out_of_bounds_and_boolean_coordinates(self):
        for args in ({"x": 100, "y": 0}, {"x": True, "y": 0}):
            with self.subTest(args=args), self.assertRaises(SafetyError):
                validate_plan(Plan("x", (Action("click", args),)), self.bounds, self.settings)

    def test_rejects_shell_text_long_text_and_controls(self):
        cases = (
            {"text": "cmd /c del important.txt"},
            {"text": "x" * 2001},
            {"text": "hello\x00world"},
            {"text": "\n\t"},
        )
        for args in cases:
            with self.subTest(args=str(args)[:20]), self.assertRaises(SafetyError):
                validate_plan(Plan("x", (Action("type", args),)), self.bounds, self.settings)

    def test_rejects_system_hotkeys_and_outside_limits(self):
        for keys in (["win", "r"], ["ctrl", "alt", "delete"], ["ctrl", "q"], ["alt", "f4"]):
            with self.subTest(keys=keys), self.assertRaises(SafetyError):
                validate_plan(Plan("x", (Action("hotkey", {"keys": keys}),)), self.bounds, self.settings)
        with self.assertRaises(SafetyError):
            validate_plan(Plan("x", (Action("scroll", {"x": 1, "y": 1, "amount": 9}),)), self.bounds, self.settings)

    def test_rejects_overlong_plan(self):
        settings = Settings(max_steps=1).validated()
        plan = Plan("x", (Action("wait", {"seconds": 1}), Action("wait", {"seconds": 1})))
        with self.assertRaises(SafetyError):
            validate_plan(plan, self.bounds, settings)

    def test_rejects_unknown_direct_action_and_invalid_screen_bounds(self):
        with self.assertRaises(SafetyError):
            validate_plan(Plan("x", (Action("shell", {}),)), self.bounds, self.settings)
        with self.assertRaises(SafetyError):
            validate_plan(Plan("x", ()), ScreenBounds(0, 10), self.settings)


if __name__ == "__main__":
    unittest.main()
