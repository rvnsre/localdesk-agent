import unittest
from unittest.mock import patch

from localdesk.config import Settings
from localdesk.errors import SafetyError
from localdesk.safety import ScreenBounds, validate_plan
from localdesk.schema import Action, Plan


class SafetyRegressionTests(unittest.TestCase):
    def validate(self, action, settings=None):
        plan = Plan("Regression", (action,))
        return validate_plan(plan, ScreenBounds(100, 100), settings or Settings())

    def test_shell_commands_on_later_lines_are_blocked(self):
        for text in ("hello\npowershell -Command example", "hello\r\n  bash script.sh", "hello\n\n\tsudo example"):
            with self.subTest(text=text), self.assertRaises(SafetyError):
                self.validate(Action("type", {"text": text}))

    def test_shell_text_opt_in_and_normal_multiline_text_remain_supported(self):
        self.validate(Action("type", {"text": "Hello\nWorld"}))
        self.validate(Action("type", {"text": "hello\nbash script.sh"}), Settings(allow_shell_text=True))

    def test_extra_modifier_cannot_bypass_blocked_hotkey(self):
        with patch("localdesk.safety.sys.platform", "win32"):
            for keys in (["ctrl", "alt", "f4"], ["alt", "shift", "f4"]):
                with self.subTest(keys=keys), self.assertRaises(SafetyError):
                    self.validate(Action("hotkey", {"keys": keys}))
            self.validate(Action("hotkey", {"keys": ["ctrl", "shift", "t"]}))
