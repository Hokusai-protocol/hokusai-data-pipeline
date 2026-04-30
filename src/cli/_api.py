"""Shared HTTP helper for Hokusai CLI commands."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request


class BenchmarkSpecLookupError(Exception):
    """Raised when a benchmark spec cannot be fetched or validated."""


def fetch_benchmark_spec(
    spec_id: str,
    *,
    api_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Fetch a BenchmarkSpec from the Hokusai API.

    Raises BenchmarkSpecLookupError for all failure modes so callers get a
    single, user-friendly exception type.
    """
    resolved_url = (api_url or os.getenv("HOKUSAI_API_URL", "http://localhost:8001")).rstrip("/")
    resolved_key = api_key or os.getenv("HOKUSAI_API_KEY")

    if not resolved_key:
        raise BenchmarkSpecLookupError(
            "HOKUSAI_API_KEY is not set. "
            "Export it before using --benchmark-spec-id: export HOKUSAI_API_KEY=<key>"
        )

    url = f"{resolved_url}/api/v1/benchmarks/{spec_id}"
    req = request.Request(  # noqa: S310
        url=url,
        headers={
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            content = resp.read().decode("utf-8")
            return json.loads(content)
    except error.HTTPError as exc:
        if exc.code == 404:
            raise BenchmarkSpecLookupError(f"Benchmark spec '{spec_id}' not found") from exc
        if exc.code in (401, 403):
            raise BenchmarkSpecLookupError(
                "Authentication failed when fetching benchmark spec. "
                "Check that HOKUSAI_API_KEY is valid."
            ) from exc
        detail = ""
        if exc.fp:
            raw = exc.read()
            if raw:
                detail = raw.decode("utf-8", errors="replace")
        raise BenchmarkSpecLookupError(
            f"Failed to fetch benchmark spec: {exc.code} {detail}"
        ) from exc
    except error.URLError as exc:
        raise BenchmarkSpecLookupError(
            f"Could not reach Hokusai API at {resolved_url}: {exc.reason}"
        ) from exc
