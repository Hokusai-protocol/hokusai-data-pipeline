"""Service layer for Hokusai contribution ingestion."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol

import boto3
from botocore.exceptions import ClientError

from src.api.endpoints.model_registry_entries import MODEL_CONFIGS
from src.api.schemas.contribution import ContributionAcceptedResponse, ContributionRequest

if TYPE_CHECKING:
    from src.api.services.auth_service_notifier import AuthServiceNotifier

logger = logging.getLogger(__name__)


class ContributionError(Exception):
    """Base contribution ingestion error."""


class ContributionModelNotFoundError(ContributionError):
    """Raised when the requested model is not registered."""

    def __init__(self: ContributionModelNotFoundError, model_id: str) -> None:
        super().__init__(f"Model {model_id} not found")
        self.model_id = model_id


class ContributionConflictError(ContributionError):
    """Raised when an idempotency key is reused with a different payload."""

    def __init__(self: ContributionConflictError, submission_id: str) -> None:
        super().__init__("Idempotency key already used with different payload")
        self.submission_id = submission_id


class ContributionPersistenceUnavailableError(ContributionError):
    """Raised when the persistence backend is unavailable or misconfigured."""


class ContributionValidationError(ContributionError):
    """Raised when the request is semantically invalid."""

    def __init__(self: ContributionValidationError, detail: dict[str, Any]) -> None:
        super().__init__(detail.get("message", "Contribution validation failed"))
        self.detail = detail


@dataclass(frozen=True)
class StoredContributionRecord:
    """Persisted contribution batch."""

    submission_id: str
    model_id: str
    idempotency_key: str
    body_hash: str
    rows: list[dict[str, Any]]
    metadata: dict[str, Any]
    response_payload: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class ContributionAcceptance:
    """Acceptance result returned to the router."""

    response: ContributionAcceptedResponse
    status_code: int


class ContributionStore(Protocol):
    """Persistence contract for contribution batches."""

    def get(
        self: ContributionStore, *, model_id: str, submission_id: str
    ) -> StoredContributionRecord | None:
        """Return an existing submission if present."""

    def create(
        self: ContributionStore, *, record: StoredContributionRecord
    ) -> StoredContributionRecord:
        """Persist a new submission record."""


class S3ContributionStore:
    """S3-backed contribution persistence."""

    def __init__(self: S3ContributionStore, *, bucket: str, prefix: str) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = boto3.client("s3")

    def _key_for(self: S3ContributionStore, model_id: str, submission_id: str) -> str:
        base = f"contributions/model_id={model_id}/{submission_id}.json"
        if self.prefix:
            return f"{self.prefix}/{base}"
        return base

    def get(
        self: S3ContributionStore, *, model_id: str, submission_id: str
    ) -> StoredContributionRecord | None:
        key = self._key_for(model_id, submission_id)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404"}:
                return None
            raise ContributionPersistenceUnavailableError(
                f"Failed to read contribution record {submission_id}"
            ) from exc

        try:
            payload = json.loads(response["Body"].read().decode("utf-8"))
        except Exception as exc:
            raise ContributionPersistenceUnavailableError(
                f"Stored contribution record {submission_id} is unreadable"
            ) from exc

        return StoredContributionRecord(
            submission_id=payload["submission_id"],
            model_id=payload["model_id"],
            idempotency_key=payload["idempotency_key"],
            body_hash=payload["body_hash"],
            rows=payload["rows"],
            metadata=payload["metadata"],
            response_payload=payload["response_payload"],
            created_at=payload["created_at"],
        )

    def create(
        self: S3ContributionStore, *, record: StoredContributionRecord
    ) -> StoredContributionRecord:
        key = self._key_for(record.model_id, record.submission_id)
        payload = {
            "submission_id": record.submission_id,
            "model_id": record.model_id,
            "idempotency_key": record.idempotency_key,
            "body_hash": record.body_hash,
            "rows": record.rows,
            "metadata": record.metadata,
            "response_payload": record.response_payload,
            "created_at": record.created_at,
        }
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"),
                ContentType="application/json",
                ServerSideEncryption="aws:kms",
                Metadata={
                    "model_id": record.model_id,
                    "submission_id": record.submission_id,
                    "idempotency_key": record.idempotency_key,
                    "body_hash": record.body_hash,
                },
            )
        except Exception as exc:
            raise ContributionPersistenceUnavailableError(
                f"Failed to persist contribution record {record.submission_id}"
            ) from exc
        return record


class ContributionService:
    """Validate, normalize, deduplicate, and persist contribution submissions."""

    def __init__(
        self: ContributionService,
        store: ContributionStore | None = None,
        notifier: AuthServiceNotifier | None = None,
    ) -> None:
        self.max_body_bytes = int(os.getenv("CONTRIBUTIONS_MAX_BODY_BYTES", str(1024 * 1024)))
        self._store: ContributionStore | None = store
        self._notifier = notifier

    @property
    def store(self: ContributionService) -> ContributionStore:
        """Return the configured store, building the default lazily on first use."""
        if self._store is None:
            self._store = self._build_default_store()
        return self._store

    @store.setter
    def store(self: ContributionService, value: ContributionStore) -> None:
        self._store = value

    @staticmethod
    def canonicalize_body(request: ContributionRequest, path_model_id: str) -> dict[str, Any]:
        """Return the internal canonical request payload used for hashing/persistence."""
        return {
            "model_id": path_model_id,
            "benchmark_spec_id": request.benchmark_spec_id,
            "rows": request.rows,
            "metadata": request.metadata.model_dump(exclude_none=True),
            "schema_version": request.schema_version,
            "template_id": request.template_id,
        }

    def accept_contribution(
        self: ContributionService,
        *,
        model_id: str,
        request: ContributionRequest,
        idempotency_key: str | None,
        auth: dict[str, Any],
    ) -> ContributionAcceptance:
        """Accept and persist a contribution batch."""
        self._validate_model_id(model_id)
        self._validate_site_model_id(model_id, request.model_id)

        canonical_body = self.canonicalize_body(request, model_id)
        body_hash = self._compute_body_hash(canonical_body)
        resolved_idempotency_key = self._resolve_idempotency_key(
            supplied_key=idempotency_key,
            request=request,
            body_hash=body_hash,
        )
        submission_id = resolved_idempotency_key
        existing = self.store.get(model_id=model_id, submission_id=submission_id)
        if existing is not None:
            if existing.body_hash != body_hash:
                raise ContributionConflictError(submission_id=submission_id)
            response = ContributionAcceptedResponse.model_validate(existing.response_payload)
            response = response.model_copy(update={"idempotent_replay": True})
            return ContributionAcceptance(response=response, status_code=200)

        response = ContributionAcceptedResponse(
            accepted=True,
            modelId=model_id,
            submissionId=submission_id,
            jobId=submission_id,
            jobIds=[submission_id],
            rowsAccepted=len(request.rows),
            submittedRows=len(request.rows),
            tokenReward=0,
            idempotentReplay=False,
        )
        metadata = {
            **request.metadata.model_dump(exclude_none=True),
            "auth_context": {
                "user_id": auth.get("user_id"),
                "api_key_id": auth.get("api_key_id"),
                "service_id": auth.get("service_id"),
            },
        }
        record = StoredContributionRecord(
            submission_id=submission_id,
            model_id=model_id,
            idempotency_key=resolved_idempotency_key,
            body_hash=body_hash,
            rows=request.rows,
            metadata=metadata,
            response_payload=response.model_dump(by_alias=True),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.create(record=record)
        if self._notifier is not None:
            try:
                self._notifier.notify_accepted(
                    record=record,
                    auth=auth,
                    storage_ref=self._storage_ref_for_record(record),
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to notify auth service for accepted contribution",
                    extra={"submission_id": submission_id, "model_id": model_id},
                )
        return ContributionAcceptance(response=response, status_code=201)

    def _build_default_store(self: ContributionService) -> ContributionStore:
        bucket = os.getenv("HOKUSAI_CONTRIBUTIONS_BUCKET")
        if not bucket:
            raise ContributionPersistenceUnavailableError(
                "HOKUSAI_CONTRIBUTIONS_BUCKET environment variable is not set"
            )
        prefix = os.getenv("HOKUSAI_CONTRIBUTIONS_PREFIX", "").strip("/")
        return S3ContributionStore(bucket=bucket, prefix=prefix)

    @staticmethod
    def _validate_model_id(model_id: str) -> None:
        if model_id not in MODEL_CONFIGS:
            raise ContributionModelNotFoundError(model_id=model_id)

    @staticmethod
    def _validate_site_model_id(path_model_id: str, body_model_id: str | None) -> None:
        if body_model_id is not None and body_model_id != path_model_id:
            raise ContributionValidationError(
                {
                    "error": "model_id_mismatch",
                    "message": "Body modelId must match the path model id",
                    "pathModelId": path_model_id,
                    "bodyModelId": body_model_id,
                }
            )

    @staticmethod
    def _compute_body_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _resolve_idempotency_key(
        *,
        supplied_key: str | None,
        request: ContributionRequest,
        body_hash: str,
    ) -> str:
        if supplied_key:
            return supplied_key.strip()
        metadata_key = request.metadata.idempotency_key
        if metadata_key:
            return metadata_key.strip()
        return f"bodyhash-{body_hash[:32]}"

    def _storage_ref_for_record(
        self: ContributionService, record: StoredContributionRecord
    ) -> str | None:
        if isinstance(self.store, S3ContributionStore):
            key = self.store._key_for(record.model_id, record.submission_id)
            return f"s3://{self.store.bucket}/{key}"
        return None
