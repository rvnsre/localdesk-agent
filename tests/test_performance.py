import asyncio
import io
import tempfile
import unittest
from unittest.mock import Mock, patch

import pybase64
from PIL import Image

from localdesk.capture import CaptureSession, encode, fingerprint
from localdesk.performance import Timings, RuntimeOptions, summarize
from localdesk.errors import LocalDeskError, AutomationError
from localdesk.schema import Plan, Action


class CaptureTests(unittest.TestCase):
    def test_encoding_is_valid_and_preserves_aspect(self):
        uri, w, h = encode(Image.new("RGB", (200, 100), "red"), 100, 65)
        image = Image.open(io.BytesIO(pybase64.b64decode(uri.split(",")[1])))
        self.assertEqual(image.size, (100, 50))
        self.assertEqual((w, h), image.size)

    def test_calibration_excludes_unavailable_and_caches_only_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            with CaptureSession(cache_dir=directory) as session:
                session._grab = Mock(side_effect=lambda name: (_ for _ in ()).throw(RuntimeError()) if name == "dxcam" else Image.new("RGB", (20, 10)))
                session.calibrate(20, 65, (20, 10))
                self.assertIn(session.selected, {"mss", "pyautogui"})
                from diskcache import Cache
                with Cache(directory) as cache:
                    self.assertTrue(all(isinstance(cache[k], str) and cache[k] in {"mss", "pyautogui"} for k in cache))

    def test_freshness_detects_even_small_changes_and_wait_is_bounded(self):
        image = Image.new("RGB", (20, 10))
        with CaptureSession("pyautogui") as session:
            session._grab = Mock(return_value=image)
            session.capture(20, 65, (20, 10))
            self.assertTrue(session.unchanged())
            self.assertFalse(session.wait_for_change(timeout=.01, poll=.002))
            image.putpixel((1, 1), (255, 0, 0))
            self.assertFalse(session.unchanged())
            self.assertTrue(session.wait_for_change(timeout=.01))

    def test_explicit_backend_does_not_silently_fallback(self):
        with CaptureSession("mss") as session:
            session._grab = Mock(side_effect=AutomationError("blocked"))
            with self.assertRaises(AutomationError):
                session.capture(20, 65, (20, 10))

    def test_session_close_releases_mss(self):
        session = CaptureSession()
        resource = Mock()
        session.mss = resource
        session.close()
        session.close()
        resource.close.assert_called_once()

    def test_cached_backend_failure_recalibrates(self):
        with CaptureSession() as session:
            session.selected = "mss"
            def select(*_, **__):
                session.selected = "pyautogui"
            session.calibrate = Mock(side_effect=select)
            session._grab = Mock(side_effect=[RuntimeError("lost desktop"), Image.new("RGB", (20, 10))])
            frame = session.capture(20, 65, (20, 10))
            self.assertEqual(frame.backend, "pyautogui")
            self.assertFalse(session.calibrate.call_args.kwargs["use_cache"])

    def test_pillow_fallback_preserves_valid_image(self):
        import cv2
        with patch("localdesk.capture.cv2.imencode", side_effect=cv2.error("unavailable")):
            uri, w, h = encode(Image.new("RGB", (20, 10)), 10, 65)
        self.assertEqual((w, h), (10, 5))
        self.assertTrue(uri.startswith("data:image/jpeg;base64,"))


class TimingTests(unittest.TestCase):
    def test_approval_excluded_from_automatic_total(self):
        timings = Timings({"model": 1, "approval": 30, "execute": 2})
        self.assertEqual(timings.report()["automatic_total"], 3)
        self.assertEqual(summarize([.001, .002, .003])["p95_ms"], 3)

    def test_invalid_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            RuntimeOptions(profile="unknown").checked()

    def test_task_comparison_does_not_verify_missing_runs(self):
        from localdesk.task_benchmark import compare
        self.assertFalse(compare({}, {})["verified"])


class AgentFreshnessTests(unittest.TestCase):
    def test_wait_change_timeout_aborts_sequence(self):
        from localdesk.automation import Desktop
        desktop = object.__new__(Desktop)
        desktop.pg = Mock()
        desktop.pg.FailSafeException = type("FailSafeException", (Exception,), {})
        desktop.announce = Mock()
        desktop.wait_for_change = Mock(return_value=False)
        with self.assertRaisesRegex(AutomationError, "Timed out"):
            desktop.execute(Plan("wait", (Action("wait_change", {"timeout": .01}), Action("type", {"text": "x"}))))
        desktop.pg.write.assert_not_called()

    def test_fast_profile_empty_plan_retries_quality_image_once(self):
        from localdesk.agent import Agent
        from localdesk.config import Settings
        from localdesk.screen import ScreenFrame
        with patch("localdesk.agent.LocalModel") as model, patch("localdesk.agent.CaptureSession") as capture:
            capture.return_value.capture.return_value = ScreenFrame("data:", 100, 60, 1000, 600)
            capture.return_value.last_timings = {}
            model.return_value.plan.side_effect = ['{"summary":"unclear","steps":[]}', '{"summary":"click","steps":[{"action":"click","x":1,"y":1}]}']
            desktop = Mock()
            desktop.size.return_value = (1000, 600)
            agent = Agent(Settings(profile="fast"), desktop)
            self.assertEqual(len(agent.propose("click").steps), 1)
            self.assertEqual(capture.return_value.capture.call_args.args, (1920, 85, (1000, 600)))
            self.assertEqual(model.return_value.plan.call_count, 2)
            agent.close()

    def test_changed_screen_never_executes(self):
        from localdesk.agent import Agent
        from localdesk.config import Settings
        with patch("localdesk.agent.LocalModel"), patch("localdesk.agent.CaptureSession") as capture:
            desktop = Mock()
            agent = Agent(Settings(), desktop)
            agent.propose = Mock(return_value=Plan("click", (Action("click", {"x": 1, "y": 1}),)))
            agent._planned_size = desktop.size.return_value
            capture.return_value.unchanged.return_value = False
            with self.assertRaisesRegex(LocalDeskError, "screen changed"), patch("builtins.print"):
                agent.run("click", lambda: True)
            desktop.execute.assert_not_called()
            agent.close()
            agent.model.close.assert_called_once()

    def test_model_cancellation_does_not_wait_for_request_or_send_input(self):
        from localdesk.model import LocalModel
        from localdesk.config import Settings
        import threading
        entered, release = threading.Event(), threading.Event()
        model = LocalModel(Settings())
        def blocked(*_):
            entered.set()
            release.wait(3)
            return "discarded"
        model.plan = blocked
        async def exercise():
            import anyio
            with anyio.move_on_after(.1) as scope:
                await model.aplan("x", "data:", 1, 1)
            self.assertTrue(scope.cancel_called)
        try:
            asyncio.run(exercise())
            self.assertTrue(entered.is_set())
        finally:
            release.set()
            model.close()

    def test_connection_retries_never_repeat_read_timeout(self):
        import httpx
        from localdesk.model import LocalModel
        from localdesk.config import Settings
        from localdesk.errors import ModelError
        with LocalModel(Settings()) as model:
            model.session.close()
            model.session = Mock()
            model.session.post.side_effect = httpx.ReadTimeout("slow")
            with self.assertRaises(ModelError):
                model.plan("x", "data:", 1, 1)
            self.assertEqual(model.session.post.call_count, 1)
