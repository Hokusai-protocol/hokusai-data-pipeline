# ruff: noqa: ANN101 - self needs no annotation
"""A minimal client for TypeSafe's System One endpoint (HOK-3026).

One request sends one state and the whole question set; Jev answers the
questions in parallel. The key comes from ``TYPESAFE_API_KEY``. Request bodies
hold raw PR text, so nothing here logs or stores them.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from typing import Any

import requests

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
KEY_VARIABLE = "TYPESAFE_API_KEY"
# Input tokens only; output tokens are free (docs.typesafe.ai/models, read 2026-11-14).
USD_PER_MILLION_INPUT_TOKENS = 0.042
RETRYABLE = (429, 500, 502, 503, 504, 529)


class JevError(Exception):
    """The request failed. ``status`` is the HTTP status, or None for a transport failure."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def transient(self) -> bool:
        """True when the same request may succeed later: transport failures and overload."""
        return self.status is None or self.status in RETRYABLE


class ContextExceededError(JevError):
    """The state and questions do not fit the model's context: rebuild with a smaller state."""


class JevClient:
    """Posts System One requests, backing off on rate limits and overload."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        session: requests.Session | None = None,
        max_retries: int = 6,
        timeout: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        key = api_key or os.environ.get(KEY_VARIABLE)
        if not key:
            raise JevError(f"Set {KEY_VARIABLE} (keys: console.typesafe.ai/keys)", 401)
        self._headers = {"Authorization": f"Bearer {key}"}
        self._session = session or requests.Session()
        self._max_retries = max_retries
        self._timeout = timeout
        self._sleep = sleep

    def ask(
        self, *, model: str, state: Any, questions: Mapping[str, Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Return the response body: ``model``, ``answers`` and ``usage``."""
        body = {"model": model, "state": state, "questions": dict(questions)}
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.post(
                    ENDPOINT, json=body, headers=self._headers, timeout=self._timeout
                )
            except requests.RequestException as error:
                if attempt < self._max_retries:
                    self._sleep(min(2.0**attempt, 60.0))
                    continue
                raise JevError(f"Transport failure: {type(error).__name__}") from error
            if response.status_code == 200:
                data = response.json()
                missing = set(questions) - set(data.get("answers", {}))
                if missing:
                    raise JevError(f"Response lacks answers for {sorted(missing)}", 200)
                return data
            if response.status_code in RETRYABLE and attempt < self._max_retries:
                wait = response.headers.get("retry-after", "")
                seconds = float(wait) if wait.replace(".", "", 1).isdigit() else 2.0**attempt
                self._sleep(min(seconds, 60.0))
                continue
            detail = response.text[:300]
            if response.status_code == 400 and "max_tokens_exceeded" in detail:
                raise ContextExceededError(detail, 400)
            raise JevError(f"HTTP {response.status_code}: {detail}", response.status_code)
        raise JevError("unreachable")


def cost_usd(input_tokens: int) -> float:
    """Return the price of ``input_tokens`` at the listed rate."""
    return input_tokens * USD_PER_MILLION_INPUT_TOKENS / 1_000_000
