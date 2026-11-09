from __future__ import annotations

import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

import orjson
import requests

from localdesk.automation import Desktop
from localdesk.config import Settings
from localdesk.errors import AutomationError, LocalDeskError, ModelError
from localdesk.model import LocalModel
from localdesk.schema import Action, Plan


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.model = LocalModel(Settings().validated())
        self.model.session = Mock()

    def test_sends_optimized_payload_and_reads_plan(self):
        raw = '{"summary":"x","steps":[]}'
        response = Mock()
        response.content = orjson.dumps({"choices": [{"message": {"content": raw}}]})
        response.raise_for_status.return_value = None
        self.model.session.post.return_value = response
        self.assertEqual(self.model.plan("goal", "data:image/jpeg;base64,AA==", 10, 10), raw)
        kwargs = self.model.session.post.call_args.kwargs
        self.assertIsInstance(kwargs["data"], bytes)
        self.assertEqual(orjson.loads(kwargs["data"])["model"], "local-model")
        self.assertEqual(kwargs["timeout"], (5.0, 90.0))

    def test_maps_timeout_http_and_malformed_response_errors(self):
        self.model.session.post.side_effect = requests.Timeout()
        with self.assertRaisesRegex(ModelError, "timeout"):
            self.model.plan("x", "data:", 1, 1)
        self.model.session.post.side_effect = requests.ConnectionError()
        with self.assertRaisesRegex(ModelError, "server is running"):
            self.model.plan("x", "data:", 1, 1)
        response = Mock(status_code=400)
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        self.model.session.post.side_effect = None
        self.model.session.post.return_value = response
        with self.assertRaisesRegex(ModelError, "HTTP 400"):
            self.model.plan("x", "data:", 1, 1)
        response.raise_for_status.side_effect = None
        response.content = b"not json"
        with self.assertRaises(ModelError):
            self.model.plan("x", "data:", 1, 1)

    def test_real_local_http_round_trip(self):
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received["path"] = self.path
                received["payload"] = orjson.loads(self.rfile.read(int(self.headers["Content-Length"])))
                body = orjson.dumps({"choices": [{"message": {"content": '{"summary":"ok","steps":[]}'}}]})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/v1"
            model = LocalModel(Settings(base_url=url).validated())
            answer = model.plan("tap", "data:image/jpeg;base64,AA==", 320, 200)
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        self.assertEqual(answer, '{"summary":"ok","steps":[]}')
        self.assertEqual(received["path"], "/v1/chat/completions")
        self.assertEqual(received["payload"]["model"], "local-model")
        self.assertEqual(received["payload"]["messages"][1]["content"][1]["image_url"]["url"], "data:image/jpeg;base64,AA==")


class AutomationTests(unittest.TestCase):
    def make_desktop(self):
        class FailSafeException(Exception):
            pass

        pg = Mock()
        pg.FailSafeException = FailSafeException
        desktop = object.__new__(Desktop)
        desktop.pg = pg
        desktop.announce = Mock()
        return desktop, pg, FailSafeException

    def test_executes_actions_in_order_and_uses_platform_command_alias(self):
        desktop, pg, _ = self.make_desktop()
        plan = Plan("ok", (
            Action("move", {"x": 1, "y": 2}),
            Action("click", {"x": 1, "y": 2}),
            Action("scroll", {"x": 1, "y": 2, "amount": 1}),
            Action("type", {"text": "hello"}),
            Action("hotkey", {"keys": ["command", "a"]}),
            Action("wait", {"seconds": 0}),
        ))
        with patch("localdesk.automation.time.sleep"):
            desktop.execute(plan)
        self.assertEqual(pg.moveTo.call_count, 2)
        self.assertEqual(pg.click.call_count, 1)
        self.assertEqual(pg.write.call_args.args, ("hello",))
        expected = "command" if sys.platform == "darwin" else "ctrl"
        self.assertEqual(pg.hotkey.call_args.args, (expected, "a"))

    def test_failsafe_aborts_and_unicode_clipboard_is_restored(self):
        desktop, pg, fail_safe = self.make_desktop()
        pg.moveTo.side_effect = fail_safe()
        with self.assertRaisesRegex(AutomationError, "Fail-safe stop"):
            desktop.execute(Plan("x", (Action("move", {"x": 1, "y": 1}),)))

        desktop, pg, _ = self.make_desktop()
        with patch("pyperclip.paste", return_value="old"), patch("pyperclip.copy") as copy, patch("localdesk.automation.time.sleep"):
            desktop._type_text("café")
        self.assertEqual(copy.call_args_list[0].args, ("café",))
        self.assertEqual(copy.call_args_list[-1].args, ("old",))
        expected = "command" if sys.platform == "darwin" else "ctrl"
        self.assertEqual(pg.hotkey.call_args.args, (expected, "v"))

    def test_pause_is_disabled_and_deadline_stops_remaining_steps(self):
        pg = Mock()
        with patch.dict(sys.modules, {"pyautogui": pg}):
            desktop = Desktop()
        self.assertTrue(pg.FAILSAFE)
        self.assertEqual(pg.PAUSE, 0.0)
        desktop = object.__new__(Desktop)
        desktop.pg = pg
        desktop.announce = Mock()
        plan = Plan("x", (Action("wait", {"seconds": 0}), Action("wait", {"seconds": 0})))
        with patch("localdesk.automation.time.monotonic", side_effect=[0.0, 0.0, 2.0]), patch("localdesk.automation.time.sleep") as sleep:
            with self.assertRaisesRegex(AutomationError, "limit"):
                desktop.execute(plan, max_seconds=1)
        self.assertEqual(sleep.call_count, 1)


if __name__ == "__main__":
    unittest.main()
