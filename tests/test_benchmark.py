from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PIL import Image

from localdesk.benchmark import _measure, _percentile95


class BenchmarkTests(unittest.TestCase):
    def test_measure_excludes_two_warmups_and_returns_each_sample(self):
        capture = Mock(return_value=Image.new("RGB", (8, 4)))
        with patch("localdesk.benchmark._encode_image", return_value=("data:", 8, 4)):
            values = _measure(capture, 3, 1280, 65)
        self.assertEqual(len(values), 3)
        self.assertEqual(capture.call_count, 5)

    def test_p95_selects_upper_tail_sample(self):
        self.assertEqual(_percentile95([0.1, 0.2, 0.3, 0.4]), 0.4)


if __name__ == "__main__":
    unittest.main()
