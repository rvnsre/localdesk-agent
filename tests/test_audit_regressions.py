import threading
import unittest
from unittest.mock import Mock
from PIL import Image

from localdesk.capture import CaptureSession
from localdesk.automation import Desktop
from localdesk.errors import AutomationError
from localdesk.schema import Action, Plan
from localdesk.task_benchmark import ensure_active


class AuditRegressionTests(unittest.TestCase):
    def test_each_wait_consumes_the_previous_change(self):
        image = Image.new("RGB", (20, 10))
        with CaptureSession("pyautogui") as capture:
            capture._grab = Mock(return_value=image)
            capture.capture(20, 65, (20, 10))
            image.putpixel((1, 1), (255, 0, 0))
            self.assertTrue(capture.wait_for_change(timeout=.01))
            self.assertFalse(capture.wait_for_change(timeout=.01, poll=.002))
            image.putpixel((2, 1), (255, 0, 0))
            self.assertTrue(capture.wait_for_change(timeout=.01))

    def test_bad_dimensions_are_rejected_before_capture(self):
        with CaptureSession("pyautogui") as capture:
            capture._grab = Mock()
            for width, quality, size in [(True, 65, (20, 10)), (20, True, (20, 10)), (20, 65, (20,)), (20, 65, (20, 10, 2)), (20, 65, None)]:
                with self.subTest(size=size), self.assertRaises(AutomationError):
                    capture.capture(width, quality, size)
            capture._grab.assert_not_called()

    def test_bad_wait_parameters_cannot_spin_forever(self):
        with CaptureSession("pyautogui") as capture:
            for timeout, poll in [(float("nan"), .1), (float("inf"), .1), (1, 0), (1, -1), (True, .1)]:
                with self.assertRaises(AutomationError):
                    capture.wait_for_change(timeout, poll)
            with self.assertRaisesRegex(AutomationError, "Capture a frame"):
                capture.wait_for_change(.01)

    def test_cancel_between_actions_stops_remaining_input(self):
        desktop = object.__new__(Desktop)
        desktop.pg = Mock()
        desktop.pg.FailSafeException = type("FailSafe", (Exception,), {})
        desktop.announce = Mock()
        cancelled = Mock(side_effect=[False, True])
        with self.assertRaisesRegex(AutomationError, "cancelled"):
            desktop.execute(Plan("type", (Action("type", {"text": "first"}), Action("type", {"text": "second"}))), cancelled=cancelled)
        desktop.pg.write.assert_called_once_with("first", interval=0)

    def test_closed_fixture_rejects_a_late_model_result(self):
        stopped = threading.Event()
        ensure_active(stopped)
        stopped.set()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            ensure_active(stopped)
