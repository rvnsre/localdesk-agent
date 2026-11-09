"""Real desktop screenshot benchmark: MSS production path vs PyAutoGUI."""

from __future__ import annotations

import argparse
import math
import statistics
import sys
import time
from collections.abc import Callable

from .console import configure_console
from .screen import _capture_dxcam, _capture_fast, _capture_pyautogui, _encode_image


def _measure(
    capture: Callable,
    iterations: int,
    width: int,
    quality: int,
    encode: bool = True,
) -> list[float]:
    timings: list[float] = []
    for index in range(iterations + 2):
        started = time.perf_counter()
        image = capture()
        if encode:
            _encode_image(image, width, quality)
        elapsed = time.perf_counter() - started
        if index >= 2:
            timings.append(elapsed)
    return timings


def _percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description="Compare MSS, DXcam, and PyAutoGUI screenshot performance.")
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--quality", type=int, default=65)
    args = parser.parse_args()
    if not 3 <= args.iterations <= 500:
        parser.error("--iterations must be between 3 and 500")
    if not 1 <= args.width <= 4096 or not 20 <= args.quality <= 95:
        parser.error("--width or --quality is outside the allowed range")
    backends = {"MSS": _capture_fast, "PyAutoGUI": _capture_pyautogui}
    if sys.platform == "win32":
        backends["DXcam"] = _capture_dxcam
    results = {}
    for name, capture in backends.items():
        try:
            raw = _measure(capture, args.iterations, args.width, args.quality, encode=False)
            full = _measure(capture, args.iterations, args.width, args.quality, encode=True)
            results[name] = (raw, full)
        except Exception as exc:
            print(f"{name}: unavailable ({exc})")
    if "PyAutoGUI" not in results or len(results) < 2:
        print("Not enough capture backends were available for comparison.", file=sys.stderr)
        return 2
    print(f"Iteration: {args.iterations}")
    print("Capture-only median / full JPEG+base64 median (milliseconds):")
    for name, (raw, full) in results.items():
        print(f"{name:10} {statistics.median(raw) * 1000:7.1f} / {statistics.median(full) * 1000:7.1f}")
    baseline = statistics.median(results["PyAutoGUI"][1])
    for name, (_raw, full) in results.items():
        if name != "PyAutoGUI":
            median = statistics.median(full)
            print(f"{name} full-path speedup vs PyAutoGUI: {baseline / median:.2f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
