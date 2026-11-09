from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from localdesk.console import configure_console


class ConsoleTests(unittest.TestCase):
    def test_windows_console_switches_to_utf8(self):
        out, err = Mock(), Mock()
        with patch("localdesk.console.sys.platform", "win32"):
            configure_console(out, err)
        out.reconfigure.assert_called_once_with(encoding="utf-8", errors="backslashreplace")
        err.reconfigure.assert_called_once_with(encoding="utf-8", errors="backslashreplace")

    def test_non_windows_streams_are_untouched(self):
        out = Mock()
        with patch("localdesk.console.sys.platform", "linux"):
            configure_console(out, out)
        out.reconfigure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
