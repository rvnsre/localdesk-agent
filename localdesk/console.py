"""Reliable UTF-8 output on Windows terminals."""

from __future__ import annotations

import sys
from typing import TextIO


def configure_console(stdout: TextIO | None = None, stderr: TextIO | None = None) -> None:
    """Switch Windows console streams to UTF-8 while preserving redirected streams."""
    if sys.platform != "win32":
        return
    for stream in (
        stdout if stdout is not None else sys.stdout,
        stderr if stderr is not None else sys.stderr,
    ):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # An IDE or redirected stream may not allow reconfiguration.
            continue
