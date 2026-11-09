"""Capture screens and map image coordinates to desktop input coordinates."""

from __future__ import annotations

import base64
import atexit
import io
import sys
import threading
from dataclasses import dataclass

from PIL import Image

from .errors import AutomationError, SafetyError
from .schema import Action, Plan


@dataclass(frozen=True)
class ScreenFrame:
    """The resized image sent to the model and the PyAutoGUI input dimensions."""

    image_uri: str
    image_width: int
    image_height: int
    input_width: int
    input_height: int
    backend: str = "mss"


_DXCAM_LOCK = threading.Lock()
_DXCAM_CAMERA = None
_DXCAM_UNAVAILABLE = False


def capture_screen(max_width: int, quality: int, input_size: tuple[int, int]) -> ScreenFrame:
    """Convert a screen capture to a JPEG data URI and retain image/input dimensions."""
    if max_width < 1 or not 20 <= quality <= 95:
        raise AutomationError("Screenshot width or quality is outside the allowed range.")
    if len(input_size) != 2 or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in input_size):
        raise AutomationError("Desktop input dimensions must be positive integers.")
    try:
        image, backend = _capture_best()
        if image.width <= 0 or image.height <= 0:
            raise AutomationError("Screenshot has empty dimensions.")
        image_uri, image_width, image_height = _encode_image(image, max_width, quality)
        return ScreenFrame(
            image_uri=image_uri,
            image_width=image_width,
            image_height=image_height,
            input_width=input_size[0],
            input_height=input_size[1],
            backend=backend,
        )
    except AutomationError:
        raise
    except Exception as exc:
        raise AutomationError(f"Could not capture the screen: {exc}") from exc


def _encode_image(image: Image.Image, max_width: int, quality: int) -> tuple[str, int, int]:
    if image.width > max_width:
        scale = max_width / image.width
        image = image.resize(
            (max_width, max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
    if image.mode != "RGB":
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality, optimize=False)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}", image.width, image.height


def _capture_pyautogui() -> Image.Image:
    """Legacy screenshot path, exposed for benchmarking and troubleshooting."""
    import pyautogui

    return pyautogui.screenshot()


def _capture_fast() -> Image.Image:
    """Pass the MSS primary monitor's BGRA buffer directly to Pillow."""
    from mss import MSS

    with MSS() as capture:
        if len(capture.monitors) < 2:
            raise AutomationError("MSS did not find an active display.")
        monitor = capture.primary_monitor
        if monitor is None:
            raise AutomationError("MSS could not identify the primary display.")
        shot = capture.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _capture_dxcam() -> Image.Image:
    """Windows Desktop Duplication backend, reused between captures."""
    global _DXCAM_CAMERA
    with _DXCAM_LOCK:
        if _DXCAM_CAMERA is None:
            import dxcam

            _DXCAM_CAMERA = dxcam.create(output_color="RGB", processor_backend="numpy")
        frame = _DXCAM_CAMERA.grab(new_frame_only=False)
        if frame is None:
            raise AutomationError("DXcam could not capture a frame from the active display.")
        return Image.fromarray(frame)


def _release_dxcam() -> None:
    global _DXCAM_CAMERA
    with _DXCAM_LOCK:
        if _DXCAM_CAMERA is not None:
            try:
                _DXCAM_CAMERA.release()
            except Exception:
                pass
            finally:
                _DXCAM_CAMERA = None


def _capture_best() -> tuple[Image.Image, str]:
    """Use DXcam on Windows and MSS elsewhere; degrade cleanly if DXGI fails."""
    global _DXCAM_UNAVAILABLE
    if sys.platform == "win32" and not _DXCAM_UNAVAILABLE:
        try:
            return _capture_dxcam(), "dxcam"
        except Exception:
            # DXGI access-denied is usually a persistent session/display restriction.
            # Avoid paying for the same failed initialization on every user request.
            _DXCAM_UNAVAILABLE = True
            _release_dxcam()
    if sys.platform == "win32":
        # The local benchmark showed Pillow/ImageGrab slightly faster than MSS here.
        try:
            return _capture_pyautogui(), "pyautogui"
        except Exception:
            return _capture_fast(), "mss"
    try:
        return _capture_fast(), "mss"
    except Exception:
        # Keep GUI support available where MSS's native screen API is restricted.
        return _capture_pyautogui(), "pyautogui"


atexit.register(_release_dxcam)


def map_plan_to_input(plan: Plan, frame: ScreenFrame) -> Plan:
    """Convert vision-image coordinates to desktop input pixels."""
    if frame.image_width <= 0 or frame.image_height <= 0:
        raise SafetyError("Screenshot dimensions are invalid.")
    if frame.input_width <= 0 or frame.input_height <= 0:
        raise SafetyError("Desktop input dimensions are invalid.")
    image_ratio = frame.image_width / frame.image_height
    input_ratio = frame.input_width / frame.input_height
    if abs(image_ratio / input_ratio - 1.0) > 0.03:
        raise SafetyError(
            "Screenshot and mouse coordinate aspect ratios do not match. "
            "Check the primary display; a multi-monitor or Retina setup may be involved."
        )
    mapped: list[Action] = []
    for index, action in enumerate(plan.steps, 1):
        args = dict(action.args)
        if action.kind in {"move", "click", "scroll"}:
            x, y = args.get("x"), args.get("y")
            if (isinstance(x, bool) or not isinstance(x, int) or
                    isinstance(y, bool) or not isinstance(y, int)):
                raise SafetyError(f"Step {index}: x and y must be integers.")
            if not 0 <= x < frame.image_width or not 0 <= y < frame.image_height:
                raise SafetyError(f"Step {index}: coordinates are outside the model image.")
            args["x"] = min(frame.input_width - 1, round(x * frame.input_width / frame.image_width))
            args["y"] = min(frame.input_height - 1, round(y * frame.input_height / frame.image_height))
        mapped.append(Action(action.kind, args))
    return Plan(plan.summary, tuple(mapped))
