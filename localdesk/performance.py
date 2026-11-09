"""Profiles, privacy-preserving measurements, and runtime diagnostics."""
from __future__ import annotations

import importlib.metadata
import platform
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from packaging.requirements import Requirement
from packaging.version import Version
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import psutil


class RuntimeOptions(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOCALDESK_", extra="ignore")
    profile: str = "balanced"
    capture_backend: str = "auto"
    max_tokens: int = Field(default=900, ge=128, le=4096)

    def checked(self):
        if self.profile not in PROFILES:
            raise ValueError("Profile must be balanced, fast, or quality.")
        if self.capture_backend not in {"auto", "mss", "dxcam", "pyautogui"}:
            raise ValueError("Unknown capture backend.")
        return self


PROFILES = {"balanced": (1280, 65, 900), "fast": (960, 60, 600), "quality": (1920, 85, 1200)}


@dataclass
class Timings:
    stages: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def measure(self, name):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = self.stages.get(name, 0.0) + time.perf_counter() - start

    def report(self):
        return {**self.stages, "automatic_total": sum(v for k, v in self.stages.items() if k != "approval")}


def summarize(values):
    if not values:
        return {"median_ms": None, "p95_ms": None}
    ordered = sorted(values)
    import math
    return {"median_ms": statistics.median(values) * 1000,
            "p95_ms": ordered[max(0, math.ceil(len(values) * .95) - 1)] * 1000}


def doctor():
    """Read package compatibility and resources without touching the desktop."""
    from . import __version__
    # Installed metadata is preferred; source checkouts use the same explicit requirements.
    try:
        requirements = importlib.metadata.requires("localdesk-agent") or []
    except importlib.metadata.PackageNotFoundError:
        requirements = []
    packages = []
    for raw in requirements:
        req = Requirement(raw)
        if req.marker and not req.marker.evaluate():
            continue
        try:
            version = importlib.metadata.version(req.name)
            packages.append({"name": req.name, "version": version, "compatible": Version(version) in req.specifier})
        except importlib.metadata.PackageNotFoundError:
            packages.append({"name": req.name, "version": None, "compatible": False})
    return {"version": __version__, "platform": platform.system(), "python": platform.python_version(),
            "cpu_count": psutil.cpu_count(), "available_memory_bytes": psutil.virtual_memory().available,
            "packages": packages, "desktop_tested": False}
