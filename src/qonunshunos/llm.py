"""Minimal OpenAI chat client (httpx) for offline tooling: evaluation data, rephrasing.

Keys come from ``OPENAI_API_KEY`` and ``OPENAI_API_KEY_2`` (two accounts with separate daily
free-token quotas); on a rate-limit or quota error the next key is tried.
"""

import json
import logging
import os
import time

import httpx

from qonunshunos.config import load_dotenv

log = logging.getLogger(__name__)

API_URL = "https://api.openai.com/v1/chat/completions"
KEY_VARS = ("OPENAI_API_KEY", "OPENAI_API_KEY_2")


class LLMError(Exception):
    pass


class OpenAIChat:
    def __init__(self, model: str = "gpt-5.4", timeout: float = 120.0) -> None:
        load_dotenv()
        self.keys = [os.environ[v] for v in KEY_VARS if os.environ.get(v)]
        if not self.keys:
            raise LLMError("no OPENAI_API_KEY in the environment / .env")
        self.model = model
        self.key_index = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self._http = httpx.Client(timeout=timeout)

    def json(self, system: str, user: str, retries: int = 3) -> dict:
        """One chat completion that must return a JSON object."""
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        attempt = 0
        while True:
            key = self.keys[self.key_index]
            response = self._http.post(
                API_URL, headers={"Authorization": f"Bearer {key}"}, json=payload
            )
            if response.status_code == 200:
                data = response.json()
                for k in self.usage:
                    self.usage[k] += data.get("usage", {}).get(k, 0)
                return json.loads(data["choices"][0]["message"]["content"])
            if response.status_code == 429 and self.key_index + 1 < len(self.keys):
                log.warning("key %d limited, switching", self.key_index + 1)
                self.key_index += 1
                continue
            if response.status_code >= 500 and attempt < retries:
                attempt += 1
                time.sleep(2 * attempt)
                continue
            raise LLMError(f"HTTP {response.status_code}: {response.text[:300]}")
