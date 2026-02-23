"""Service for inference usage and deferred outcome logging."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Callable
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.api.models import InferenceLog
from src.api.schemas.inference_log import InferenceLogCreate
from src.api.utils.config import get_settings

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class InferenceLogNotFoundError(Exception):
    """Raised when an inference log id cannot be found."""


class InferenceLogOwnershipError(Exception):
    """Raised when token ownership checks fail for an inference log."""


@lru_cache(maxsize=4)
def _session_factory_from_url(database_url: str) -> sessionmaker:
    engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


class ContributorLogger:
    """Persistence service for model usage logs and deferred outcomes."""

    def __init__(
        self,
        session_factory: SessionFactory | None = None,
        database_url: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._database_url = database_url

    def _resolve_database_url(self) -> str | None:
        if self._database_url:
            return self._database_url

        env_url = os.getenv("POSTGRES_URI")
        if env_url:
            return env_url

        try:
            settings = get_settings()
            return settings.postgres_uri
        except Exception as exc:
            logger.error("Contributor logger could not resolve database URL: %s", exc)
            return None

    def _get_session_factory(self) -> SessionFactory | None:
        if self._session_factory:
            return self._session_factory

        database_url = self._resolve_database_url()
        if not database_url:
            return None

        return _session_factory_from_url(database_url)

    @contextmanager
    def _session_scope(self):
        session_factory = self._get_session_factory()
        if session_factory is None:
            raise RuntimeError("No database session factory available for contributor logger")

        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    @staticmethod
    def new_inference_log_id() -> UUID:
        """Return a correlation UUID for inference logs."""
        return uuid4()

    def log_inference(
        self,
        api_token_id: str,
        model_name: str,
        model_version: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any] | None,
        trace_metadata: dict[str, Any] | None,
        inference_log_id: UUID | None = None,
    ) -> UUID:
        """Create an inference log row and return its id.

        This method is intentionally failure-tolerant and never raises to callers.
        """
        log_id = inference_log_id or uuid4()

        try:
            payload = InferenceLogCreate(
                api_token_id=api_token_id,
                model_name=model_name,
                model_version=model_version,
                input_payload=input_payload,
                output_payload=output_payload,
                trace_metadata=trace_metadata,
            )
        except Exception as exc:
            logger.error("Inference log payload validation failed for %s: %s", log_id, exc)
            return log_id

        try:
            with self._session_scope() as session:
                session.add(
                    InferenceLog(
                        id=log_id,
                        api_token_id=payload.api_token_id,
                        model_name=payload.model_name,
                        model_version=payload.model_version,
                        input_payload=payload.input_payload,
                        output_payload=payload.output_payload,
                        trace_metadata=payload.trace_metadata,
                    )
                )
                session.commit()
        except Exception as exc:
            logger.error("Failed to persist inference log %s: %s", log_id, exc)

        return log_id

    def record_outcome(
        self,
        inference_log_id: UUID,
        api_token_id: str,
        outcome_score: float,
        outcome_type: str,
    ) -> None:
        """Patch deferred outcome fields on an existing inference log row."""
        with self._session_scope() as session:
            inference_log = session.query(InferenceLog).filter_by(id=inference_log_id).first()
            if inference_log is None:
                raise InferenceLogNotFoundError(str(inference_log_id))

            if inference_log.api_token_id != api_token_id:
                raise InferenceLogOwnershipError(str(inference_log_id))

            inference_log.outcome_score = outcome_score
            inference_log.outcome_type = outcome_type
            inference_log.outcome_recorded_at = datetime.now(timezone.utc)
            session.commit()
