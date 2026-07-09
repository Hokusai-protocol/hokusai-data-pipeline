"""Service layer for Hokusai contribution ingestion."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Callable, Protocol

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.api.endpoints.model_registry_entries import MODEL_CONFIGS
from src.api.models.contribution_lifecycle import (
    LIFECYCLE_STATE_VALUES,
    ContributionLifecycle,
    ContributionLifecycleState,
)
from src.api.schemas.contribution import (
    ContributionAcceptedResponse,
    ContributionRequest,
    FidelitySummary,
    LifecycleReasonCode,
    LifecycleUpdatePayload,
    RejectedRow,
    RowCounts,
)
from src.api.services.contribution_fidelity import BatchClassification, classify_batch
from src.api.utils.config import get_settings

if TYPE_CHECKING:
    from src.api.services.auth_service_notifier import AuthServiceNotifier

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]


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


class ContributionLifecycleUnavailableError(ContributionError):
    """Raised when lifecycle persistence cannot be reached for a required operation."""


class ContributionLifecycleNotFoundError(ContributionError):
    """Raised when a lifecycle record does not exist."""

    def __init__(self: ContributionLifecycleNotFoundError, submission_id: str) -> None:
        super().__init__(f"Lifecycle record not found for {submission_id}")
        self.submission_id = submission_id


class ContributionLifecycleStateError(ContributionError):
    """Raised when a lifecycle state transition request is invalid."""

    def __init__(self: ContributionLifecycleStateError, state: str) -> None:
        valid_states = ", ".join(LIFECYCLE_STATE_VALUES)
        super().__init__(f"Invalid lifecycle state {state!r}. Expected one of: {valid_states}")
        self.state = state


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


@dataclass(frozen=True)
class ContributionLifecycleRecord:
    """Serialized lifecycle state returned by service methods."""

    submission_id: str
    state: str
    accepted_row_count: int
    rejected_row_count: int
    reason: str | None
    processing_metadata: dict[str, Any] | None
    training_run_id: str | None
    evaluation_run_id: str | None
    created_at: datetime
    updated_at: datetime


_LIFECYCLE_METADATA_DATASET_VERSION_KEY = "dataset_version"
_LIFECYCLE_METADATA_ESTIMATED_REWARD_AT_KEY = "estimated_reward_at"
_NOTIFIABLE_LIFECYCLE_STATES = {
    ContributionLifecycleState.PROCESSED.value,
    ContributionLifecycleState.INCLUDED_IN_TRAINING.value,
    ContributionLifecycleState.REJECTED.value,
    ContributionLifecycleState.EXCLUDED.value,
}

# Reserved contribution-metadata keys carrying the authoritative, per-row
# fidelity classification computed at intake. The training assembler honors
# ``_METADATA_ROW_FIDELITY_TIERS_KEY`` to exclude ``partial`` rows.
_METADATA_ROW_FIDELITY_TIERS_KEY = "row_fidelity_tiers"
_METADATA_FIDELITY_SUMMARY_KEY = "fidelity_summary"
# Lowercase cause understood by ``AuthServiceNotifier._map_reason_code`` and
# mapped to ``LifecycleReasonCode.EXCLUDED_FROM_TRAINING``.
_EXCLUDED_FROM_TRAINING_REASON = LifecycleReasonCode.EXCLUDED_FROM_TRAINING.value.lower()


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

    def list_keys(self: S3ContributionStore, *, model_id: str) -> list[str]:
        """Return stored contribution object keys for a model in stable order."""
        prefix = self._key_for(model_id, "").rsplit("/", 1)[0] + "/"
        paginator = self._client.get_paginator("list_objects_v2")
        keys: list[str] = []
        try:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    key = item.get("Key")
                    if isinstance(key, str):
                        keys.append(key)
        except ClientError as exc:
            raise ContributionPersistenceUnavailableError(
                f"Failed to list contribution records for model {model_id}"
            ) from exc
        return sorted(keys)

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


@lru_cache(maxsize=4)
def _lifecycle_session_factory_from_url(database_url: str) -> sessionmaker:
    engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


class ContributionService:
    """Validate, normalize, deduplicate, and persist contribution submissions."""

    def __init__(
        self: ContributionService,
        store: ContributionStore | None = None,
        notifier: AuthServiceNotifier | None = None,
        lifecycle_session_factory: SessionFactory | None = None,
        database_url: str | None = None,
    ) -> None:
        self.max_body_bytes = int(os.getenv("CONTRIBUTIONS_MAX_BODY_BYTES", str(1024 * 1024)))
        self._store: ContributionStore | None = store
        self._notifier = notifier
        self._lifecycle_session_factory = lifecycle_session_factory
        self._database_url = database_url

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
            self._notify_auth_accepted(
                record=existing,
                auth=self._auth_context_for_notification(record=existing, fallback_auth=auth),
            )
            return ContributionAcceptance(response=response, status_code=200)

        classification = classify_batch(
            request.rows,
            benchmark_spec_id=request.benchmark_spec_id,
            model_id=model_id,
        )
        if classification.accepted_count == 0:
            raise ContributionValidationError(
                {
                    "error": "no_acceptable_rows",
                    "message": (
                        "All submitted rows were classified invalid "
                        "(missing route identity or model selection)"
                    ),
                    "submittedRows": len(request.rows),
                    "rejectedRows": classification.rejected,
                }
            )

        response = ContributionAcceptedResponse(
            accepted=True,
            modelId=model_id,
            submissionId=submission_id,
            jobId=submission_id,
            jobIds=[submission_id],
            rowsAccepted=classification.accepted_count,
            submittedRows=len(request.rows),
            tokenReward=0,
            idempotentReplay=False,
            rowFidelityTiers=list(classification.accepted_tiers),
            fidelitySummary=FidelitySummary(
                training_eligible=classification.training_eligible_count,
                partial=classification.partial_count,
                passthrough=classification.passthrough_count,
                invalid=classification.rejected_count,
            ),
            rejectedRows=[
                RejectedRow(index=entry["index"], reason=entry["reason"])
                for entry in classification.rejected
            ],
        )
        metadata = {
            **request.metadata.model_dump(exclude_none=True),
            "auth_context": {
                "user_id": auth.get("user_id"),
                "api_key_id": auth.get("api_key_id"),
                "service_id": auth.get("service_id"),
            },
            _METADATA_ROW_FIDELITY_TIERS_KEY: classification.accepted_tiers,
            _METADATA_FIDELITY_SUMMARY_KEY: {
                "training_eligible": classification.training_eligible_count,
                "partial": classification.partial_count,
                "passthrough": classification.passthrough_count,
                "invalid": classification.rejected_count,
                "rejected": classification.rejected,
            },
        }
        record = StoredContributionRecord(
            submission_id=submission_id,
            model_id=model_id,
            idempotency_key=resolved_idempotency_key,
            body_hash=body_hash,
            rows=classification.accepted_rows,
            metadata=metadata,
            response_payload=response.model_dump(by_alias=True),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.create(record=record)
        try:
            self.create_lifecycle_record(
                submission_id=submission_id,
                accepted_row_count=classification.accepted_count,
                rejected_row_count=classification.rejected_count,
                reason=self._lifecycle_reason_for(classification),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to persist contribution lifecycle state during acceptance",
                extra={"submission_id": submission_id, "model_id": model_id},
            )
        self._notify_auth_accepted(record=record, auth=auth)
        return ContributionAcceptance(response=response, status_code=201)

    def create_lifecycle_record(
        self: ContributionService,
        *,
        submission_id: str,
        accepted_row_count: int,
        rejected_row_count: int = 0,
        reason: str | None = None,
        processing_metadata: dict[str, Any] | None = None,
        training_run_id: str | None = None,
        evaluation_run_id: str | None = None,
    ) -> ContributionLifecycleRecord | None:
        """Create the initial lifecycle row if DB persistence is available."""
        session_factory = self._get_lifecycle_session_factory()
        if session_factory is None:
            logger.info(
                "Lifecycle persistence unavailable during acceptance; skipping record creation",
                extra={"submission_id": submission_id},
            )
            return None

        session = session_factory()
        try:
            existing = (
                session.query(ContributionLifecycle)
                .filter(ContributionLifecycle.submission_id == submission_id)
                .first()
            )
            if existing is not None:
                return self._encode_lifecycle_row(existing)

            row = ContributionLifecycle(
                submission_id=submission_id,
                state=ContributionLifecycleState.RECEIVED.value,
                accepted_row_count=accepted_row_count,
                rejected_row_count=rejected_row_count,
                reason=reason,
                processing_metadata=processing_metadata,
                training_run_id=training_run_id,
                evaluation_run_id=evaluation_run_id,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = (
                    session.query(ContributionLifecycle)
                    .filter(ContributionLifecycle.submission_id == submission_id)
                    .first()
                )
                if existing is not None:
                    return self._encode_lifecycle_row(existing)
                raise
            session.refresh(row)
            return self._encode_lifecycle_row(row)
        finally:
            session.close()

    def advance_lifecycle_state(
        self: ContributionService,
        *,
        submission_id: str,
        state: str,
        accepted_row_count: int | None = None,
        rejected_row_count: int | None = None,
        reason: str | None = None,
        processing_metadata: dict[str, Any] | None = None,
        dataset_version: str | None = None,
        training_run_id: str | None = None,
        evaluation_run_id: str | None = None,
        estimated_reward_at: datetime | None = None,
    ) -> ContributionLifecycleRecord:
        """Upsert and update lifecycle state with absolute counts and optional run refs."""
        normalized_state = self._normalize_lifecycle_state(state)
        session_factory = self._get_lifecycle_session_factory()
        if session_factory is None:
            raise ContributionLifecycleUnavailableError(
                "Lifecycle persistence is unavailable because no database is configured"
            )

        session = session_factory()
        try:
            row = (
                session.query(ContributionLifecycle)
                .filter(ContributionLifecycle.submission_id == submission_id)
                .with_for_update()
                .first()
            )
            row = self._upsert_lifecycle_row(
                session=session,
                existing_row=row,
                submission_id=submission_id,
                state=normalized_state,
                accepted_row_count=accepted_row_count,
                rejected_row_count=rejected_row_count,
                reason=reason,
                processing_metadata=processing_metadata,
                dataset_version=dataset_version,
                training_run_id=training_run_id,
                evaluation_run_id=evaluation_run_id,
                estimated_reward_at=estimated_reward_at,
            )

            session.commit()
            session.refresh(row)
            record = self._encode_lifecycle_row(row)
            try:
                self._notify_lifecycle_update(session=session, row=row)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to persist lifecycle callback tracking",
                    extra={"submission_id": submission_id, "state": normalized_state},
                    exc_info=True,
                )
            return record
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def retry_failed_callbacks(self: ContributionService, *, limit: int = 50) -> int:
        """Retry failed lifecycle callbacks up to the configured max-attempt threshold."""
        session_factory = self._get_lifecycle_session_factory()
        if session_factory is None:
            raise ContributionLifecycleUnavailableError(
                "Lifecycle persistence is unavailable because no database is configured"
            )

        max_attempts = max(1, int(os.getenv("LIFECYCLE_CALLBACK_MAX_ATTEMPTS", "5")))
        session = session_factory()
        delivered = 0
        try:
            rows = (
                session.query(ContributionLifecycle)
                .filter(ContributionLifecycle.callback_status == "failed")
                .filter(ContributionLifecycle.callback_attempts < max_attempts)
                .order_by(ContributionLifecycle.updated_at.asc())
                .limit(limit)
                .all()
            )
            for row in rows:
                try:
                    delivered += int(self._notify_lifecycle_update(session=session, row=row))
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Failed to persist lifecycle callback retry state",
                        extra={"submission_id": row.submission_id, "state": row.state},
                        exc_info=True,
                    )
            return delivered
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_lifecycle_state(
        self: ContributionService, submission_id: str
    ) -> ContributionLifecycleRecord | None:
        """Fetch lifecycle state for a submission id."""
        session_factory = self._get_lifecycle_session_factory()
        if session_factory is None:
            raise ContributionLifecycleUnavailableError(
                "Lifecycle persistence is unavailable because no database is configured"
            )

        session = session_factory()
        try:
            row = (
                session.query(ContributionLifecycle)
                .filter(ContributionLifecycle.submission_id == submission_id)
                .first()
            )
            if row is None:
                return None
            return self._encode_lifecycle_row(row)
        finally:
            session.close()

    def _build_default_store(self: ContributionService) -> ContributionStore:
        bucket = os.getenv("HOKUSAI_CONTRIBUTIONS_BUCKET")
        if not bucket:
            raise ContributionPersistenceUnavailableError(
                "HOKUSAI_CONTRIBUTIONS_BUCKET environment variable is not set"
            )
        prefix = os.getenv("HOKUSAI_CONTRIBUTIONS_PREFIX", "").strip("/")
        return S3ContributionStore(bucket=bucket, prefix=prefix)

    def _resolve_database_url(self: ContributionService) -> str | None:
        if self._database_url:
            return self._database_url

        env_url = os.getenv("POSTGRES_URI") or os.getenv("DATABASE_URL")
        if env_url:
            return env_url

        try:
            settings = get_settings()
            return settings.postgres_uri
        except Exception as exc:
            logger.info("Contribution lifecycle could not resolve database URL: %s", exc)
            return None

    def _get_lifecycle_session_factory(self: ContributionService) -> SessionFactory | None:
        if self._lifecycle_session_factory:
            return self._lifecycle_session_factory

        database_url = self._resolve_database_url()
        if not database_url:
            return None
        return _lifecycle_session_factory_from_url(database_url)

    @staticmethod
    def _lifecycle_reason_for(classification: BatchClassification) -> str | None:
        """Return the excluded-from-training reason when no row can train.

        A submission whose only accepted rows are ``partial`` (telemetry only)
        carries the ``EXCLUDED_FROM_TRAINING`` reason so the dashboard reflects
        that nothing from it enters the success-under-budget training set.
        """
        if classification.has_only_partial:
            return _EXCLUDED_FROM_TRAINING_REASON
        return None

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

    @staticmethod
    def _normalize_lifecycle_state(state: str) -> str:
        normalized = state.strip()
        if normalized not in LIFECYCLE_STATE_VALUES:
            raise ContributionLifecycleStateError(normalized)
        return normalized

    @staticmethod
    def _encode_lifecycle_row(row: ContributionLifecycle) -> ContributionLifecycleRecord:
        return ContributionLifecycleRecord(
            submission_id=row.submission_id,
            state=row.state,
            accepted_row_count=row.accepted_row_count,
            rejected_row_count=row.rejected_row_count,
            reason=row.reason,
            processing_metadata=row.processing_metadata,
            training_run_id=row.training_run_id,
            evaluation_run_id=row.evaluation_run_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _notify_lifecycle_update(
        self: ContributionService,
        *,
        session: Session,
        row: ContributionLifecycle,
    ) -> bool:
        if self._notifier is None or row.state not in _NOTIFIABLE_LIFECYCLE_STATES:
            return False

        delivered = False
        error_message = None
        try:
            payload = self._build_lifecycle_update_payload(row)
            delivered, error_message = self._notifier.notify_lifecycle_update(payload)
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            logger.warning(
                "Lifecycle callback raised unexpectedly",
                extra={
                    "submission_id": row.submission_id,
                    "state": row.state,
                    "error": error_message,
                },
            )

        row.callback_status = "delivered" if delivered else "failed"
        row.callback_attempts = (row.callback_attempts or 0) + 1
        row.callback_last_error = None if delivered else error_message
        row.callback_last_attempt_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        return delivered

    def _build_lifecycle_update_payload(
        self: ContributionService,
        row: ContributionLifecycle,
    ) -> LifecycleUpdatePayload:
        processing_metadata = row.processing_metadata or {}
        estimated_reward_at = self._parse_estimated_reward_at(
            processing_metadata.get(_LIFECYCLE_METADATA_ESTIMATED_REWARD_AT_KEY)
        )
        return LifecycleUpdatePayload(
            submission_id=row.submission_id,
            status=row.state,
            row_counts=RowCounts(
                accepted=row.accepted_row_count,
                rejected=row.rejected_row_count,
                total=row.accepted_row_count + row.rejected_row_count,
            ),
            dataset_version=processing_metadata.get(_LIFECYCLE_METADATA_DATASET_VERSION_KEY),
            training_run_id=row.training_run_id,
            evaluation_run_id=row.evaluation_run_id,
            estimated_reward_at=estimated_reward_at,
            reason_code=self._notifier._map_reason_code(row.reason),
        )

    def _upsert_lifecycle_row(
        self: ContributionService,
        *,
        session: Session,
        existing_row: ContributionLifecycle | None,
        submission_id: str,
        state: str,
        accepted_row_count: int | None,
        rejected_row_count: int | None,
        reason: str | None,
        processing_metadata: dict[str, Any] | None,
        dataset_version: str | None,
        training_run_id: str | None,
        evaluation_run_id: str | None,
        estimated_reward_at: datetime | None,
    ) -> ContributionLifecycle:
        merged_processing_metadata = self._merge_processing_metadata(
            current=existing_row.processing_metadata if existing_row is not None else None,
            updates=processing_metadata,
            dataset_version=dataset_version,
            estimated_reward_at=estimated_reward_at,
        )
        if existing_row is None:
            row = ContributionLifecycle(
                submission_id=submission_id,
                state=state,
                accepted_row_count=accepted_row_count or 0,
                rejected_row_count=rejected_row_count or 0,
                reason=reason,
                processing_metadata=merged_processing_metadata,
                training_run_id=training_run_id,
                evaluation_run_id=evaluation_run_id,
            )
            session.add(row)
            return row

        existing_row.state = state
        if accepted_row_count is not None:
            existing_row.accepted_row_count = accepted_row_count
        if rejected_row_count is not None:
            existing_row.rejected_row_count = rejected_row_count
        if reason is not None:
            existing_row.reason = reason
        if (
            processing_metadata is not None
            or dataset_version is not None
            or estimated_reward_at is not None
        ):
            existing_row.processing_metadata = merged_processing_metadata
        if training_run_id is not None:
            existing_row.training_run_id = training_run_id
        if evaluation_run_id is not None:
            existing_row.evaluation_run_id = evaluation_run_id
        return existing_row

    @staticmethod
    def _merge_processing_metadata(
        *,
        current: dict[str, Any] | None,
        updates: dict[str, Any] | None,
        dataset_version: str | None,
        estimated_reward_at: datetime | None,
    ) -> dict[str, Any] | None:
        merged: dict[str, Any] = dict(current or {})
        if updates is not None:
            merged.update(updates)
        if dataset_version is not None:
            merged[_LIFECYCLE_METADATA_DATASET_VERSION_KEY] = dataset_version
        if estimated_reward_at is not None:
            merged[_LIFECYCLE_METADATA_ESTIMATED_REWARD_AT_KEY] = estimated_reward_at.isoformat()
        return merged or None

    @staticmethod
    def _parse_estimated_reward_at(value: Any) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _storage_ref_for_record(
        self: ContributionService, record: StoredContributionRecord
    ) -> str | None:
        if isinstance(self.store, S3ContributionStore):
            key = self.store._key_for(record.model_id, record.submission_id)
            return f"s3://{self.store.bucket}/{key}"
        return None

    def _notify_auth_accepted(
        self: ContributionService,
        *,
        record: StoredContributionRecord,
        auth: dict[str, Any],
    ) -> None:
        if self._notifier is None:
            return
        try:
            self._notifier.notify_accepted(
                record=record,
                auth=auth,
                storage_ref=self._storage_ref_for_record(record),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to notify auth service for accepted contribution",
                extra={"submission_id": record.submission_id, "model_id": record.model_id},
            )

    @staticmethod
    def _auth_context_for_notification(
        *,
        record: StoredContributionRecord,
        fallback_auth: dict[str, Any],
    ) -> dict[str, Any]:
        auth_context = record.metadata.get("auth_context")
        if isinstance(auth_context, dict) and auth_context:
            return auth_context
        return fallback_auth
