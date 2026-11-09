"""Connection to a local model using the OpenAI Chat Completions API."""

from __future__ import annotations

import orjson
import httpx
import anyio
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from .config import Settings
from .errors import ModelError
from .prompts import SYSTEM_PROMPT, user_prompt


class LocalModel:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = httpx.Client(verify=settings.verify_tls, trust_env=False, timeout=httpx.Timeout(settings.timeout, connect=5.0))
        self.session.headers.update({"Content-Type": "application/json"})
        if settings.api_key:
            self.session.headers["Authorization"] = f"Bearer {settings.api_key}"

    def plan(self, goal: str, image_uri: str, width: int, height: int) -> str:
        """Request a JSON plan from the model."""
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": user_prompt(goal, width, height)},
                    {"type": "image_url", "image_url": {"url": image_uri}},
                ]},
            ],
        }
        try:
            response = self._post(url, orjson.dumps(payload))
            response.raise_for_status()
            data = orjson.loads(response.content)
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ModelError("The model API returned empty content.")
            return content
        except httpx.TimeoutException as exc:
            raise ModelError("The model API did not respond before the timeout.") from exc
        except httpx.HTTPError as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                status = response.status_code
                hint = " Check JSON mode and vision/image_url support." if status in {400, 404, 415, 422} else ""
                raise ModelError(f"The model API returned HTTP {status}.{hint}") from exc
            raise ModelError(
                "Could not connect to the model API. Check that the server is running and verify the URL and port."
            ) from exc
        except (orjson.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ModelError(f"The API response does not match the expected format: {exc}") from exc

    def _post(self, url, payload):
        # Retry only connection establishment failures, never read timeouts or actions.
        for attempt in Retrying(stop=stop_after_attempt(2), wait=wait_fixed(.1),
                                retry=retry_if_exception_type(httpx.ConnectError), reraise=True):
            with attempt:
                return self.session.post(url, content=payload)

    async def aplan(self, goal, image_uri, width, height):
        # Cancellation abandons the waiting coroutine. HTTP timeout still bounds the worker;
        # it never performs desktop input and its result is discarded on cancellation.
        return await anyio.to_thread.run_sync(self.plan, goal, image_uri, width, height, abandon_on_cancel=True)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
