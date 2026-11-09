"""Configuration loaded from environment variables and CLI options."""

from __future__ import annotations

import os
import math
from dataclasses import dataclass
from urllib.parse import urlparse

from .errors import ConfigurationError


@dataclass(frozen=True)
class Settings:
    """OpenAI-compatible local API settings and safety limits."""

    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = "local-model"
    api_key: str = "local"
    timeout: float = 90.0
    max_steps: int = 12
    max_text_chars: int = 2000
    max_goal_chars: int = 4000
    max_plan_seconds: float = 120.0
    screenshot_width: int = 1280
    screenshot_jpeg_quality: int = 65
    temperature: float = 0.1
    verify_tls: bool = True
    allow_remote_api: bool = False
    allow_shell_text: bool = False
    profile: str = "balanced"
    capture_backend: str = "auto"
    max_tokens: int = 900

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from LOCALDESK_* environment variables."""
        from .performance import RuntimeOptions, PROFILES
        from pydantic import ValidationError
        try:
            runtime = RuntimeOptions().checked()
        except (ValueError, ValidationError) as exc:
            raise ConfigurationError(str(exc)) from exc
        width, quality, tokens = PROFILES[runtime.profile]
        return cls(
            profile=runtime.profile, capture_backend=runtime.capture_backend,
            max_tokens=_int_env("LOCALDESK_MAX_TOKENS", tokens),
            base_url=os.getenv("LOCALDESK_BASE_URL", cls.base_url),
            model=os.getenv("LOCALDESK_MODEL", cls.model),
            api_key=os.getenv("LOCALDESK_API_KEY", cls.api_key),
            timeout=_float_env("LOCALDESK_TIMEOUT", cls.timeout),
            max_steps=_int_env("LOCALDESK_MAX_STEPS", cls.max_steps),
            max_text_chars=_int_env("LOCALDESK_MAX_TEXT_CHARS", cls.max_text_chars),
            max_goal_chars=_int_env("LOCALDESK_MAX_GOAL_CHARS", cls.max_goal_chars),
            max_plan_seconds=_float_env("LOCALDESK_MAX_SECONDS", cls.max_plan_seconds),
            screenshot_width=_int_env("LOCALDESK_SCREENSHOT_WIDTH", width),
            screenshot_jpeg_quality=_int_env("LOCALDESK_JPEG_QUALITY", quality),
            temperature=_float_env("LOCALDESK_TEMPERATURE", cls.temperature),
            verify_tls=os.getenv("LOCALDESK_VERIFY_TLS", "true").lower() not in {"0", "false", "no"},
            allow_remote_api=os.getenv("LOCALDESK_ALLOW_REMOTE_API", "false").lower() in {"1", "true", "yes"},
            allow_shell_text=os.getenv("LOCALDESK_ALLOW_SHELL_TEXT", "false").lower() in {"1", "true", "yes"},
        ).validated()

    def validated(self) -> "Settings":
        if self.profile not in {"balanced", "fast", "quality"} or self.capture_backend not in {"auto", "mss", "dxcam", "pyautogui"}:
            raise ConfigurationError("Unknown profile or capture backend.")
        if not 128 <= self.max_tokens <= 4096:
            raise ConfigurationError("max_tokens must be between 128 and 4096.")
        if not self.base_url.strip() or any(ord(ch) < 33 or ord(ch) == 127 for ch in self.base_url):
            raise ConfigurationError("LOCALDESK_BASE_URL cannot be empty.")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError("API URL must use the http(s)://host/v1 format.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConfigurationError("API URL cannot contain credentials, a query, or a fragment.")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ConfigurationError("API URL port must be between 1 and 65535.") from exc
        if port == 0:
            raise ConfigurationError("API URL port must be between 1 and 65535.")
        host = (parsed.hostname or "").lower()
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if host not in local_hosts and not self.allow_remote_api:
            raise ConfigurationError(
                "The API host is not loopback. Set LOCALDESK_ALLOW_REMOTE_API=true to allow a remote server."
            )
        if not math.isfinite(self.timeout) or self.timeout <= 0 or self.timeout > 600:
            raise ConfigurationError("timeout must be between 0 and 600 seconds.")
        if not 1 <= self.max_steps <= 40:
            raise ConfigurationError("max_steps must be between 1 and 40.")
        if not 1 <= self.max_text_chars <= 10000:
            raise ConfigurationError("max_text_chars must be between 1 and 10000.")
        if not 1 <= self.max_goal_chars <= 20000:
            raise ConfigurationError("max_goal_chars must be between 1 and 20000.")
        if not 1 <= self.screenshot_width <= 4096:
            raise ConfigurationError("screenshot_width must be between 1 and 4096.")
        if not 20 <= self.screenshot_jpeg_quality <= 95:
            raise ConfigurationError("JPEG quality must be between 20 and 95.")
        if not math.isfinite(self.max_plan_seconds) or self.max_plan_seconds <= 0 or self.max_plan_seconds > 900:
            raise ConfigurationError("max_plan_seconds must be between 0 and 900 seconds.")
        if not self.model.strip() or any(ch in self.model for ch in "\r\n"):
            raise ConfigurationError("LOCALDESK_MODEL cannot be empty or contain a newline.")
        if any(ch in self.api_key for ch in "\r\n"):
            raise ConfigurationError("LOCALDESK_API_KEY cannot contain a newline.")
        if not 0 <= self.temperature <= 2:
            raise ConfigurationError("temperature must be between 0 and 2.")
        return self


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
