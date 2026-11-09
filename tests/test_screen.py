from __future__ import annotations

import base64
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from localdesk.errors import AutomationError, SafetyError
from localdesk.schema import Action, Plan
from localdesk.screen import ScreenFrame, _capture_best, _release_dxcam, capture_screen, map_plan_to_input


class ScreenTests(unittest.TestCase):
    def test_capture_rejects_bad_input_size_before_touching_desktop(self):
        with self.assertRaises(AutomationError):
            capture_screen(1280, 65, (0, 600))
        with self.assertRaises(AutomationError):
            capture_screen(1280, 65, (True, 600))

    def test_scaled_coordinates_map_to_input_dimensions(self):
        frame = ScreenFrame("data:", 640, 360, 1920, 1080)
        plan = Plan("x", (Action("click", {"x": 320, "y": 180}),))
        mapped = map_plan_to_input(plan, frame)
        self.assertEqual(mapped.steps[0].args, {"x": 960, "y": 540})

    def test_maps_last_pixel_and_rejects_outside_or_bad_aspect(self):
        frame = ScreenFrame("data:", 640, 360, 1920, 1080)
        edge = Plan("x", (Action("move", {"x": 639, "y": 359}),))
        self.assertEqual(map_plan_to_input(edge, frame).steps[0].args, {"x": 1917, "y": 1077})
        with self.assertRaises(SafetyError):
            map_plan_to_input(Plan("x", (Action("click", {"x": 640, "y": 0}),)), frame)
        with self.assertRaises(SafetyError):
            map_plan_to_input(Plan("x", ()), ScreenFrame("data:", 640, 360, 1000, 1000))

    def test_capture_uses_mss_and_encodes_resized_jpeg(self):
        pixels = bytes([0, 0, 255, 255] * 32)
        shot = SimpleNamespace(size=(8, 4), bgra=pixels)

        class FakeMSS:
            monitors = [{}, {"left": 0, "top": 0, "width": 8, "height": 4}]
            primary_monitor = monitors[1]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def grab(self, _monitor):
                if _monitor is not self.primary_monitor:
                    raise AssertionError("primary_monitor must be selected")
                return shot

        with patch("localdesk.screen.sys.platform", "linux"), patch("mss.MSS", return_value=FakeMSS()):
            frame = capture_screen(4, 60, (8, 4))
        data = base64.b64decode(frame.image_uri.split(",", 1)[1])
        decoded = Image.open(io.BytesIO(data))
        self.assertEqual((frame.image_width, frame.image_height), (4, 2))
        self.assertEqual(decoded.size, (4, 2))
        self.assertEqual((frame.input_width, frame.input_height), (8, 4))
        self.assertEqual(frame.backend, "mss")

    def test_windows_dxcam_access_failure_disables_backend_and_falls_back(self):
        image = Image.new("RGB", (8, 4))
        with (
            patch("localdesk.screen.sys.platform", "win32"),
            patch("localdesk.screen._DXCAM_UNAVAILABLE", False),
            patch("localdesk.screen._capture_dxcam", side_effect=RuntimeError("Access denied")) as dxcam,
            patch("localdesk.screen._release_dxcam"),
            patch("localdesk.screen._capture_pyautogui", return_value=image) as legacy,
            patch("localdesk.screen._capture_fast", return_value=image) as mss,
        ):
            result = _capture_best()
            second_result = _capture_best()
        self.assertEqual(result, (image, "pyautogui"))
        self.assertEqual(second_result, (image, "pyautogui"))
        dxcam.assert_called_once()
        self.assertEqual(legacy.call_count, 2)
        mss.assert_not_called()

    def test_windows_falls_back_to_mss_when_dxcam_and_imagegrab_fail(self):
        image = Image.new("RGB", (8, 4))
        with (
            patch("localdesk.screen.sys.platform", "win32"),
            patch("localdesk.screen._DXCAM_UNAVAILABLE", True),
            patch("localdesk.screen._capture_pyautogui", side_effect=RuntimeError("ImageGrab blocked")),
            patch("localdesk.screen._capture_fast", return_value=image) as mss,
        ):
            result = _capture_best()
        self.assertEqual(result, (image, "mss"))
        mss.assert_called_once()

    def test_pyautogui_is_last_resort_if_mss_is_restricted(self):
        image = Image.new("RGB", (8, 4))
        with (
            patch("localdesk.screen.sys.platform", "linux"),
            patch("localdesk.screen._capture_fast", side_effect=RuntimeError("MSS blocked")),
            patch("localdesk.screen._capture_pyautogui", return_value=image) as legacy,
        ):
            result = _capture_best()
        self.assertEqual(result, (image, "pyautogui"))
        legacy.assert_called_once()

    def test_dxcam_release_errors_do_not_break_fallback_cleanup(self):
        camera = SimpleNamespace(release=Mock(side_effect=RuntimeError("COM release failed")))
        with patch("localdesk.screen._DXCAM_CAMERA", camera):
            _release_dxcam()
        camera.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
