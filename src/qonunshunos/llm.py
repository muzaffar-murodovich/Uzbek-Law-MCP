"""Minimal OpenAI chat client (httpx) for offline tooling: evaluation data, rephrasing.

Keys: ``OPENAI_API_KEY_2``, ``OPENAI_API_KEY_3``, then ``OPENAI_API_KEY`` (three accounts, each
with a daily free-token allowance). When the free allowance is used up OpenAI does **not**
return an error, it starts billing. So every call is checked against a local per-key, per-day
(UTC) ledger in ``data/llm_usage.json`` and refused before the allowance would be exceeded,
unless the caller explicitly allows paid tokens (``allow_paid``).
"""

import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from qonunshunos.config import load_dotenv

log = logging.getLogger(__name__)

API_URL = "https://api.openai.com/v1/chat/completions"
KEY_VARS = ("OPENAI_API_KEY_2", "OPENAI_API_KEY_3", "OPENAI_API_KEY")
LEDGER = Path("data/llm_usage.json")

# Free daily allowance per account, with a safety margin (250k and 2.5M tokens).
BIG_MODELS = {"gpt-5.4", "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-4.1", "gpt-4o", "o1", "o3"}
SMALL_MODELS = {
    "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5-mini", "gpt-5-nano", "gpt-4.1-mini",
    "gpt-4.1-nano", "gpt-4o-mini", "o3-mini", "o4-mini",
}  # fmt: skip
DAILY_LIMIT = {"big": 240_000, "small": 2_400_000}
CALL_RESERVE = 8_000  # tokens kept free for the next call (its size is unknown upfront)


class LLMError(Exception):
    pass


class BudgetExhausted(LLMError):
    pass


def tier_of(model: str) -> str:
    if model in BIG_MODELS:
        return "big"
    if model in SMALL_MODELS:
        return "small"
    raise LLMError(f"{model} is not in the free-token list; refusing to call it")


class Ledger:
    """Tokens used today per key variable and tier (``data/llm_usage.json``)."""

    def __init__(self, path: Path = LEDGER) -> None:
        self.path = path

    def _load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    @staticmethod
    def today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def used(self, key_var: str, tier: str) -> int:
        return self._load().get(self.today(), {}).get(key_var, {}).get(tier, 0)

    def add(self, key_var: str, tier: str, tokens: int) -> None:
        data = self._load()
        day = data.setdefault(self.today(), {}).setdefault(key_var, {})
        day[tier] = day.get(tier, 0) + tokens
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")


class OpenAIChat:
    def __init__(
        self, model: str = "gpt-5.4", timeout: float = 120.0, *, allow_paid: bool = False
    ) -> None:
        load_dotenv()
        self.tier = tier_of(model)
        self.keys = [(v, os.environ[v]) for v in KEY_VARS if os.environ.get(v)]
        if not self.keys:
            raise LLMError(f"none of {', '.join(KEY_VARS)} in the environment / .env")
        self.model = model
        self.allow_paid = allow_paid  # past every free allowance, keep going on paid tokens
        self.ledger = Ledger()
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self._http = httpx.Client(timeout=timeout)

    def _pick_key(self) -> tuple[str, str]:
        limit = DAILY_LIMIT[self.tier] - CALL_RESERVE
        for var, key in self.keys:
            if self.ledger.used(var, self.tier) < limit:
                return var, key
        if self.allow_paid:
            # Spread the paid part over the accounts: the least used one today.
            return min(self.keys, key=lambda vk: self.ledger.used(vk[0], self.tier))
        raise BudgetExhausted(
            f"free {self.tier}-model tokens for today are used up on all keys "
            f"(see {self.ledger.path}); try tomorrow (UTC) or a smaller model"
        )

    def json(self, system: str, user: str, retries: int = 3) -> dict:
        """One chat completion that must return a JSON object."""
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        attempt = 0
        while True:
            var, key = self._pick_key()
            response = self._http.post(
                API_URL, headers={"Authorization": f"Bearer {key}"}, json=payload
            )
            if response.status_code == 200:
                data = response.json()
                usage = data.get("usage", {})
                for k in self.usage:
                    self.usage[k] += usage.get(k, 0)
                self.ledger.add(var, self.tier, usage.get("total_tokens", 0))
                return json.loads(data["choices"][0]["message"]["content"])
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < retries:
                attempt += 1
                time.sleep(5 * attempt)
                continue
            raise LLMError(f"HTTP {response.status_code}: {response.text[:300]}")
