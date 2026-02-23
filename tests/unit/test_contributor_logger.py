"""Unit tests for contributor attribution utilities."""

from uuid import uuid4

import pytest

from src.api.services.contributor_logger import (
    ContributorLogger,
    InferenceLogNotFoundError,
    InferenceLogOwnershipError,
)
from src.utils.contributor_logger import build_contributor_attribution


def test_build_contributor_attribution_from_explicit_inputs() -> None:
    attribution = build_contributor_attribution(
        contributor_id="author-1",
        contributor_role="prompt_author",
        contributors_by_role={
            "training_data_uploader": "uploader-1",
            "human_labeler": "labeler-1",
        },
    )

    assert attribution.primary_contributor_id == "author-1"
    assert attribution.contributors_by_role == {
        "prompt_author": "author-1",
        "training_data_uploader": "uploader-1",
        "human_labeler": "labeler-1",
    }

    tags = attribution.to_mlflow_tags()
    assert tags["contributor_id"] == "author-1"
    assert tags["hokusai.contributor.prompt_author_id"] == "author-1"
    assert tags["hokusai.contributor.training_data_uploader_id"] == "uploader-1"
    assert tags["hokusai.contributor.human_labeler_id"] == "labeler-1"


def test_build_contributor_attribution_merges_from_inputs() -> None:
    attribution = build_contributor_attribution(
        contributor_id="author-1",
        contributor_role="prompt_author",
        inputs={
            "training_data_uploader_id": "uploader-2",
            "human_labeler_id": "labeler-2",
            "contributor_id": "author-override",
            "contributor_role": "prompt_author",
        },
    )

    assert attribution.contributors_by_role["prompt_author"] == "author-override"
    assert attribution.contributors_by_role["training_data_uploader"] == "uploader-2"
    assert attribution.contributors_by_role["human_labeler"] == "labeler-2"


def test_log_inference_persists_with_expected_fields() -> None:
    added_rows = []

    class FakeSession:
        def add(self, row):
            added_rows.append(row)

        def commit(self):
            return None

        def close(self):
            return None

    logger = ContributorLogger(session_factory=lambda: FakeSession())
    log_id = uuid4()
    returned_id = logger.log_inference(
        api_token_id="key-123",
        model_name="Model A",
        model_version="v1",
        input_payload={"inputs": {"text": "hi"}},
        output_payload={"answer": "hello"},
        trace_metadata={"latency_ms": 9},
        inference_log_id=log_id,
    )

    assert returned_id == log_id
    assert len(added_rows) == 1
    assert added_rows[0].api_token_id == "key-123"
    assert added_rows[0].model_name == "Model A"
    assert added_rows[0].model_version == "v1"
    assert added_rows[0].trace_metadata["latency_ms"] == 9


def test_log_inference_swallows_db_errors() -> None:
    class ExplodingSession:
        def add(self, _row):
            raise RuntimeError("db down")

        def commit(self):
            return None

        def close(self):
            return None

    logger = ContributorLogger(session_factory=lambda: ExplodingSession())
    log_id = logger.log_inference(
        api_token_id="key-123",
        model_name="Model A",
        model_version="v1",
        input_payload={"inputs": {"text": "hi"}},
        output_payload={"answer": "hello"},
        trace_metadata={"latency_ms": 11},
    )

    assert log_id is not None


def test_record_outcome_not_found_raises() -> None:
    class QueryResult:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return None

    class FakeSession:
        def query(self, _model):
            return QueryResult()

        def commit(self):
            return None

        def close(self):
            return None

    logger = ContributorLogger(session_factory=lambda: FakeSession())
    with pytest.raises(InferenceLogNotFoundError):
        logger.record_outcome(uuid4(), "key-123", 0.9, "engagement")


def test_record_outcome_ownership_check_raises() -> None:
    class ExistingRow:
        api_token_id = "different-key"

    class QueryResult:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return ExistingRow()

    class FakeSession:
        def query(self, _model):
            return QueryResult()

        def commit(self):
            return None

        def close(self):
            return None

    logger = ContributorLogger(session_factory=lambda: FakeSession())
    with pytest.raises(InferenceLogOwnershipError):
        logger.record_outcome(uuid4(), "key-123", 0.8, "reply_rate")


def test_record_outcome_updates_row() -> None:
    class ExistingRow:
        api_token_id = "key-123"
        outcome_score = None
        outcome_type = None
        outcome_recorded_at = None

    row = ExistingRow()

    class QueryResult:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return row

    class FakeSession:
        committed = False

        def query(self, _model):
            return QueryResult()

        def commit(self):
            self.committed = True

        def close(self):
            return None

    session = FakeSession()
    logger = ContributorLogger(session_factory=lambda: session)
    logger.record_outcome(uuid4(), "key-123", 0.95, "engagement")

    assert session.committed is True
    assert row.outcome_score == 0.95
    assert row.outcome_type == "engagement"
    assert row.outcome_recorded_at is not None
