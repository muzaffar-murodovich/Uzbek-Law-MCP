"""Polite HTTP client for lex.uz.

One request at a time, at least ``min_interval`` seconds between requests, a plain User-Agent
without personal data, and a few retries on server errors and timeouts.
"""

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://lex.uz"
USER_AGENT = "QonunshunosBot/0.1"
NOT_FOUND_PATH = "/Pages/404.aspx"


class NotFound(Exception):
    pass


class FetchError(Exception):
    pass


@dataclass
class Page:
    url: str  # final URL after redirects
    status: int
    text: str


class LexClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        min_interval: float = 2.0,
        timeout: float = 60.0,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self.retries = retries
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None
        self._http = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LexClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _throttle(self) -> None:
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)

    def request(self, method: str, path: str, data: Mapping[str, str] | None = None) -> Page:
        attempt = 0
        while True:
            self._throttle()
            try:
                response = self._http.request(method, path, data=data)
                error = f"HTTP {response.status_code}" if response.status_code >= 500 else None
            except httpx.TransportError as exc:  # timeouts, connection errors
                response, error = None, f"{type(exc).__name__}: {exc}"
            finally:
                self._last = self._clock()

            if error is None and response is not None:
                if (
                    response.url.path.lower() == NOT_FOUND_PATH.lower()
                    or response.status_code == 404
                ):
                    raise NotFound(path)
                if response.status_code >= 400:
                    raise FetchError(f"{method} {path}: HTTP {response.status_code}")
                return Page(url=str(response.url), status=response.status_code, text=response.text)

            if attempt >= self.retries:
                raise FetchError(f"{method} {path}: {error} after {attempt + 1} attempts")
            backoff = 2.0 * 2**attempt
            log.warning("%s %s failed (%s), retrying in %.0f s", method, path, error, backoff)
            self._sleep(backoff)
            attempt += 1

    def get(self, path: str) -> Page:
        return self.request("GET", path)

    def post(self, path: str, data: Mapping[str, str]) -> Page:
        return self.request("POST", path, data=data)


def document_path(lex_id: int) -> str:
    return f"/docs/{lex_id}"


def card_path(lex_id: int) -> str:
    return f"/actinfo/card1/{lex_id}"
