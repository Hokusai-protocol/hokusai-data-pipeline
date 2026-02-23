"""Token mint hook stub for contributor reward flows."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

import httpx

from src.api.schemas.token_mint import TokenMintRequest, TokenMintResult

LOGGER = logging.getLogger(__name__)


class TokenMintHook:
    """Callable stub that logs mint attempts and optionally calls an external mint endpoint."""

    def __init__(
        self: TokenMintHook,
        mint_endpoint: str | None = None,
        dry_run: bool = True,
        timeout: float = 10.0,
        retry_attempts: int = 2,
    ) -> None:
        self.mint_endpoint = mint_endpoint
        self.dry_run = dry_run
        self.timeout = timeout
        self.retry_attempts = max(1, retry_attempts)

    @classmethod
    def from_settings(cls: type[TokenMintHook]) -> TokenMintHook:
        """Build an instance from environment-backed defaults."""
        endpoint = os.getenv("TOKEN_MINT_ENDPOINT")
        dry_run = os.getenv("TOKEN_MINT_DRY_RUN", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        timeout = float(os.getenv("TOKEN_MINT_TIMEOUT", "10.0"))
        return cls(
            mint_endpoint=endpoint,
            dry_run=dry_run,
            timeout=timeout,
        )

    def mint(
        self: TokenMintHook,
        model_id: str,
        token_id: str,
        delta_value: float,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenMintResult:
        """Validate, audit-log, and dispatch a token mint request."""
        request = TokenMintRequest(
            model_id=model_id,
            token_id=token_id,
            delta_value=delta_value,
            idempotency_key=idempotency_key,
            metadata=metadata or {},
        )
        return self.mint_request(request)

    def mint_request(self: TokenMintHook, request: TokenMintRequest) -> TokenMintResult:
        """Process a token mint request object and return a structured status payload."""
        audit_ref = str(uuid4())
        timestamp = datetime.now(timezone.utc)
        self._log_event(
            {
                "action": "token_mint_request",
                "audit_ref": audit_ref,
                "timestamp": timestamp.isoformat(),
                "status": "requested",
                "model_id": request.model_id,
                "token_id": request.token_id,
                "delta_value": request.delta_value,
                "idempotency_key": request.idempotency_key,
                "metadata_keys": sorted(request.metadata.keys()),
            }
        )

        if self.dry_run or not self.mint_endpoint:
            status: Literal["dry_run", "skipped"] = "dry_run" if self.dry_run else "skipped"
            result = TokenMintResult(status=status, audit_ref=audit_ref, timestamp=timestamp)
            self._log_outcome(
                audit_ref=audit_ref,
                request=request,
                status=result.status,
                timestamp=timestamp,
                error=None,
            )
            return result

        payload = {
            "model_id": request.model_id,
            "token_id": request.token_id,
            "delta_value": request.delta_value,
            "idempotency_key": request.idempotency_key,
            "metadata": request.metadata,
            "audit_ref": audit_ref,
            "timestamp": timestamp.isoformat(),
        }

        last_error: str | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = httpx.post(self.mint_endpoint, json=payload, timeout=self.timeout)
                if 200 <= response.status_code < 300:
                    result = TokenMintResult(
                        status="success",
                        audit_ref=audit_ref,
                        timestamp=timestamp,
                    )
                    self._log_outcome(
                        audit_ref=audit_ref,
                        request=request,
                        status=result.status,
                        timestamp=timestamp,
                        error=None,
                    )
                    return result
                body_preview = response.text[:500]
                last_error = (
                    f"Unexpected response status={response.status_code}, body={body_preview}"
                )
            except httpx.TimeoutException:
                last_error = (
                    f"Mint request timed out after {self.timeout}s "
                    f"(attempt {attempt}/{self.retry_attempts})"
                )
            except httpx.HTTPError as exc:
                last_error = (
                    f"HTTP error during mint request: {exc!s} "
                    f"(attempt {attempt}/{self.retry_attempts})"
                )
            except Exception as exc:  # noqa: BLE001
                last_error = (
                    f"Unexpected error during mint request: {exc!s} "
                    f"(attempt {attempt}/{self.retry_attempts})"
                )

            self._log_event(
                {
                    "action": "token_mint_retry",
                    "audit_ref": audit_ref,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "retrying",
                    "attempt": attempt,
                    "max_attempts": self.retry_attempts,
                    "error": last_error,
                }
            )

        result = TokenMintResult(
            status="failed",
            audit_ref=audit_ref,
            timestamp=timestamp,
            error=last_error or "Mint request failed",
        )
        self._log_outcome(
            audit_ref=audit_ref,
            request=request,
            status=result.status,
            timestamp=timestamp,
            error=result.error,
        )
        return result

    def _log_outcome(
        self: TokenMintHook,
        audit_ref: str,
        request: TokenMintRequest,
        status: str,
        timestamp: datetime,
        error: str | None,
    ) -> None:
        self._log_event(
            {
                "action": "token_mint_outcome",
                "audit_ref": audit_ref,
                "timestamp": timestamp.isoformat(),
                "status": status,
                "model_id": request.model_id,
                "token_id": request.token_id,
                "delta_value": request.delta_value,
                "idempotency_key": request.idempotency_key,
                "error": error,
            }
        )

    def _log_event(self: TokenMintHook, payload: dict[str, Any]) -> None:
        """Emit structured JSON logs for CloudWatch queryability."""
        LOGGER.info(json.dumps(payload, default=str, sort_keys=True))
