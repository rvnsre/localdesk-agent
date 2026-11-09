"""Session-owned capture, measured backend selection, and image fingerprints."""
from __future__ import annotations

import platform
import time
import threading
import statistics
import math
from pathlib import Path

import cv2
import numpy as np
import pybase64
import xxhash
from diskcache import Cache
from filelock import FileLock, Timeout
from platformdirs import user_cache_dir

from . import screen
from .errors import AutomationError
from .screen import ScreenFrame


def fingerprint(image):
    """Keep an in-memory full-frame digest; never persist screen content."""
    return xxhash.xxh3_128_hexdigest(np.asarray(image.convert("RGB")).tobytes())


def encode(image, width, quality):
    try:
        rgb = np.asarray(image.convert("RGB"))
        if rgb.shape[1] > width:
            rgb = cv2.resize(rgb, (width, max(1, round(rgb.shape[0] * width / rgb.shape[1]))), interpolation=cv2.INTER_AREA)
        ok, data = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise ValueError("JPEG encoder returned no data")
        return "data:image/jpeg;base64," + pybase64.b64encode(data).decode("ascii"), rgb.shape[1], rgb.shape[0]
    except (cv2.error, ValueError):
        return screen._encode_image(image, width, quality)


class CaptureSession:
    """Own native resources on a single thread; select by full capture/encode cost."""
    def __init__(self, backend="auto", cache_dir=None):
        self.requested = backend
        self.selected = None
        self.mss = None
        self.owner = threading.get_ident()
        self.last_digest = None
        self.last_timings = {}
        self.cache_dir = cache_dir or user_cache_dir("localdesk-agent")
        self.failures = {}

    def _grab(self, name):
        if threading.get_ident() != self.owner:
            raise AutomationError("Capture session cannot cross threads.")
        if name == "mss":
            if self.mss is None:
                from mss import MSS
                self.mss = MSS()
            monitor = self.mss.primary_monitor
            if monitor is None:
                raise AutomationError("No primary monitor found.")
            shot = self.mss.grab(monitor)
            from PIL import Image
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if name == "dxcam":
            if platform.system() != "Windows":
                raise AutomationError("DXcam is only supported on Windows.")
            return screen._capture_dxcam()
        if name == "pyautogui":
            return screen._capture_pyautogui()
        raise AutomationError("Unknown capture backend.")

    def calibrate(self, width, quality, input_size, use_cache=True):
        try:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
            with FileLock(str(Path(self.cache_dir) / "calibration.lock"), timeout=30):
                return self._calibrate(width, quality, input_size, use_cache)
        except Timeout as exc:
            raise AutomationError("Capture calibration is busy; retry after the other session finishes.") from exc
        except OSError:
            return self._calibrate(width, quality, input_size, use_cache=False)

    def _calibrate(self, width, quality, input_size, use_cache=True):
        candidates = ["mss", "pyautogui"]
        if platform.system() == "Windows":
            candidates.insert(0, "dxcam")
        key = f"v2:{platform.system()}:{input_size}:{width}:{quality}"
        # Only backend names and timings are stored, for at most one day.
        try:
            with Cache(self.cache_dir) as cache:
                cached = cache.get(key)
        except Exception:
            cached = None
        if use_cache and cached in candidates:
            self.selected = cached
            return
        scores = {}
        for name in candidates:
            try:
                self._grab(name)
                samples = []
                for _ in range(3):
                    start = time.perf_counter()
                    encode(self._grab(name), width, quality)
                    samples.append(time.perf_counter() - start)
                scores[name] = statistics.median(samples)
            except Exception as exc:
                self.failures[name] = type(exc).__name__
        if not scores:
            raise AutomationError("No screen capture backend is available.")
        self.selected = min(scores, key=scores.get)
        try:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
            with Cache(self.cache_dir) as cache:
                cache.set(key, self.selected, expire=86400)
        except Exception:
            pass

    def capture(self, width, quality, input_size):
        if (type(width) is not int or width < 1 or type(quality) is not int or not 20 <= quality <= 95
                or not isinstance(input_size, (tuple, list)) or len(input_size) != 2
                or any(type(v) is not int or v <= 0 for v in input_size)):
            raise AutomationError("Invalid capture dimensions or quality.")
        if self.requested != "auto":
            self.selected = self.requested
        elif self.selected is None:
            self.calibrate(width, quality, input_size)
        start = time.perf_counter()
        try:
            image = self._grab(self.selected)
        except Exception as exc:
            if self.requested != "auto":
                raise AutomationError(f"Capture backend {self.selected} is unavailable: {type(exc).__name__}") from exc
            # A cached backend can become unavailable. Recalibrate once.
            self.calibrate(width, quality, input_size, use_cache=False)
            try:
                image = self._grab(self.selected)
            except Exception as exc:
                # Ignore persisted selection for recovery.
                self.selected = "pyautogui" if self.selected != "pyautogui" else "mss"
                image = self._grab(self.selected)
        captured = time.perf_counter()
        self.last_digest = fingerprint(image)
        uri, w, h = encode(image, width, quality)
        self.last_timings = {"capture": captured - start, "encode": time.perf_counter() - captured}
        return ScreenFrame(uri, w, h, *input_size, backend=self.selected)

    def unchanged(self):
        return self.last_digest is not None and fingerprint(self._grab(self.selected)) == self.last_digest

    def wait_for_change(self, timeout=2.0, poll=.05):
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0
                or isinstance(poll, bool) or not isinstance(poll, (int, float)) or not math.isfinite(poll) or poll <= 0):
            raise AutomationError("Timeout and polling interval must be positive finite numbers.")
        if self.last_digest is None or self.selected is None:
            raise AutomationError("Capture a frame before waiting for a screen change.")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = fingerprint(self._grab(self.selected))
            if current != self.last_digest:
                self.last_digest = current
                return True
            time.sleep(min(poll, max(0, deadline - time.monotonic())))
        return False

    def close(self):
        try:
            if self.mss is not None:
                try:
                    self.mss.close()
                finally:
                    self.mss = None
        finally:
            screen._release_dxcam()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
