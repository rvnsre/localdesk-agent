"""Connection to a local model using the OpenAI Chat Completions API."""

from __future__ import annotations

import orjson
import requests

from .config import Settings
from .errors import ModelError
from .prompts import SYSTEM_PROMPT, user_prompt


class LocalModel:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if settings.api_key:
            self.session.headers["Authorization"] = f"Bearer {settings.api_key}"

    def plan(self, goal: str, image_uri: str, width: int, height: int) -> str:
        """Request a JSON plan from the model."""
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "max_tokens": 900,
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
            response = self.session.post(
                url, data=orjson.dumps(payload), timeout=(5.0, self.settings.timeout),
                verify=self.settings.verify_tls,
            )
            response.raise_for_status()
            data = orjson.loads(response.content)
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty content")
            return content
        except requests.Timeout as exc:
            raise ModelError("The model API did not respond before the timeout.") from exc
        except requests.RequestException as exc:
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
