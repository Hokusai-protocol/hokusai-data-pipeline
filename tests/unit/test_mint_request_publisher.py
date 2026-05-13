"""Tests for MintRequest schema, publisher, and orchestrator integration.

Auth note: tests use fake MLflow clients only; no live MLflow requests are made.
Production auth relies on MLFLOW_TRACKING_TOKEN / Authorization env wiring.

Tests cover:
- MintRequestContributor, MintRequestEvaluation, MintRequest Pydantic validation
- JSON schema drift against schema/mint_request.v1.json
- Example fixture round-trip through Pydantic
- MintRequestPublisher writes raw JSON to hokusai:mint_requests
- Redis errors propagate from publisher
- Idempotency key matches HOK-1266 make_idempotency_key helper
- Orchestrator publishes on acceptance before canonical score advancement
- Orchestrator requires a publisher for accepted DeltaOne mint handoff
- No publish on rejection or guardrail breach
- Publisher failure prevents canonical score advancement
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import fakeredis
import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import (
    DeltaOneMintOrchestrator,
    _build_mint_request,
    _EventContext,
    _extract_contributors_from_spec,
    _extract_contributors_from_tags,
    _normalize_weights_to_10000,
)
from src.evaluation.event_payload import (
    DeltaOneAcceptanceEvent,
    DeltaOneGuardrailSummary,
    EventPayloadError,
    make_idempotency_key,
)
from src.events.publishers.mint_request_publisher import QUEUE_NAME, MintRequestPublisher
from src.events.schemas import (
    MintRequest,
    MintRequestContributor,
    MintRequestEvaluation,
)

REPO_ROOT = Path(__file__).parents[2]
SCHEMA_FILE = REPO_ROOT / "schema" / "mint_request.v1.json"
EXAMPLE_FILE = REPO_ROOT / "schema" / "examples" / "mint_request.v1.json"

_ATT_HASH = "0x" + "a" * 64
_IDEMPOTENCY_KEY = "0x" + "b" * 64
_MODEL_ID_UINT = "12345678901234567890"
_EVAL_ID = "eval-test-001"
_SPEC_ID = "spec-test-v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_contributor(**overrides) -> MintRequestContributor:
    defaults = {"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}
    defaults.update(overrides)
    return MintRequestContributor(**defaults)


def _valid_evaluation(**overrides) -> MintRequestEvaluation:
    defaults = {
        "metric_name": "accuracy",
        "metric_family": "proportion",
        "baseline_score_bps": 7800,
        "new_score_bps": 8100,
        "max_cost_usd_micro": 5_000_000,
        "actual_cost_usd_micro": 2_340_000,
    }
    defaults.update(overrides)
    return MintRequestEvaluation(**defaults)


def _valid_mint_request(**overrides) -> MintRequest:
    defaults = {
        "message_id": "test-msg-001",
        "timestamp": "2026-05-05T12:00:00+00:00",
        "model_id": "model-a",
        "model_id_uint": _MODEL_ID_UINT,
        "eval_id": _EVAL_ID,
        "attestation_hash": _ATT_HASH,
        "idempotency_key": _IDEMPOTENCY_KEY,
        "evaluation": _valid_evaluation(),
        "contributors": [_valid_contributor()],
    }
    defaults.update(overrides)
    return MintRequest(**defaults)


# ---------------------------------------------------------------------------
# MintRequestContributor validation
# ---------------------------------------------------------------------------


class TestMintRequestContributor:
    def test_valid_lowercase_wallet(self) -> None:
        c = MintRequestContributor(
            wallet_address="0x742d35cc6634c0532925a3b844bc9e7595f62341",
            weight_bps=5000,
        )
        assert c.wallet_address == "0x742d35cc6634c0532925a3b844bc9e7595f62341"

    def test_wallet_normalized_to_lowercase(self) -> None:
        c = MintRequestContributor(
            wallet_address="0x742D35CC6634C0532925A3B844BC9E7595F62341",
            weight_bps=5000,
        )
        assert c.wallet_address == "0x742d35cc6634c0532925a3b844bc9e7595f62341"

    def test_invalid_wallet_too_short(self) -> None:
        with pytest.raises(ValidationError, match="wallet_address"):
            MintRequestContributor(wallet_address="0x1234", weight_bps=5000)

    def test_invalid_wallet_no_prefix(self) -> None:
        with pytest.raises(ValidationError, match="wallet_address"):
            MintRequestContributor(
                wallet_address="742d35cc6634c0532925a3b844bc9e7595f62341", weight_bps=5000
            )

    def test_weight_bps_zero(self) -> None:
        c = MintRequestContributor(
            wallet_address="0x742d35cc6634c0532925a3b844bc9e7595f62341", weight_bps=0
        )
        assert c.weight_bps == 0

    def test_weight_bps_max(self) -> None:
        c = MintRequestContributor(
            wallet_address="0x742d35cc6634c0532925a3b844bc9e7595f62341", weight_bps=10000
        )
        assert c.weight_bps == 10000

    def test_weight_bps_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            MintRequestContributor(
                wallet_address="0x742d35cc6634c0532925a3b844bc9e7595f62341", weight_bps=10001
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            MintRequestContributor(
                wallet_address="0x742d35cc6634c0532925a3b844bc9e7595f62341",
                weight_bps=5000,
                extra_field="nope",
            )


# ---------------------------------------------------------------------------
# MintRequest validation
# ---------------------------------------------------------------------------


class TestMintRequest:
    def test_valid_round_trip(self) -> None:
        msg = _valid_mint_request()
        assert msg.model_id == "model-a"
        assert msg.message_type == "mint_request"
        assert msg.schema_version == "1.0"

    def test_contributors_must_sum_to_10000(self) -> None:
        with pytest.raises(ValidationError, match="10000"):
            _valid_mint_request(
                contributors=[
                    MintRequestContributor(
                        wallet_address="0x742d35cc6634c0532925a3b844bc9e7595f62341",
                        weight_bps=5000,
                    ),
                    MintRequestContributor(
                        wallet_address="0x6c3e007f281f6948b37c511a11e43c8026d2f069",
                        weight_bps=3000,
                    ),
                ]
            )

    def test_contributors_two_summing_to_10000(self) -> None:
        msg = _valid_mint_request(
            contributors=[
                MintRequestContributor(
                    wallet_address="0x742d35cc6634c0532925a3b844bc9e7595f62341",
                    weight_bps=7000,
                ),
                MintRequestContributor(
                    wallet_address="0x6c3e007f281f6948b37c511a11e43c8026d2f069",
                    weight_bps=3000,
                ),
            ]
        )
        assert sum(c.weight_bps for c in msg.contributors) == 10000

    def test_contributors_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _valid_mint_request(contributors=[])

    def test_contributors_max_100(self) -> None:
        contribs = [
            MintRequestContributor(wallet_address=f"0x{'0' * 38}{i:02x}", weight_bps=99)
            for i in range(101)
        ]
        contribs[0] = MintRequestContributor(
            wallet_address="0x" + "0" * 40, weight_bps=10000 - 99 * 100
        )
        with pytest.raises(ValidationError, match="100"):
            _valid_mint_request(contributors=contribs)

    def test_model_id_required_nonempty(self) -> None:
        with pytest.raises(ValidationError):
            _valid_mint_request(model_id="")

    def test_model_id_uint_must_be_decimal(self) -> None:
        with pytest.raises(ValidationError, match="model_id_uint"):
            _valid_mint_request(model_id_uint="not_a_number")

    def test_model_id_uint_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _valid_mint_request(model_id_uint="-1")

    def test_model_id_uint_above_uint256_rejected(self) -> None:
        over = str(2**256)
        with pytest.raises(ValidationError):
            _valid_mint_request(model_id_uint=over)

    def test_attestation_hash_must_be_0x_lowercase_64hex(self) -> None:
        with pytest.raises(ValidationError, match="attestation_hash"):
            _valid_mint_request(attestation_hash="0x" + "A" * 64)

    def test_attestation_hash_bare_rejected(self) -> None:
        with pytest.raises(ValidationError, match="attestation_hash"):
            _valid_mint_request(attestation_hash="a" * 64)

    def test_idempotency_key_matches_hok1266_helper(self) -> None:
        model_id_uint_int = int(_MODEL_ID_UINT)
        key = make_idempotency_key(model_id_uint_int, _EVAL_ID, _ATT_HASH)
        msg = _valid_mint_request(idempotency_key=key)
        assert msg.idempotency_key == key

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            _valid_mint_request(unknown_field="x")

    def test_frozen_cannot_mutate(self) -> None:
        from pydantic import ValidationError as PydanticError  # noqa: PLC0415

        msg = _valid_mint_request()
        with pytest.raises((PydanticError, TypeError)):
            msg.model_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# JSON Schema drift test
# ---------------------------------------------------------------------------


class TestJsonSchemaDrift:
    def test_schema_file_exists(self) -> None:
        assert SCHEMA_FILE.exists(), f"Schema file not found: {SCHEMA_FILE}"

    def test_example_file_exists(self) -> None:
        assert EXAMPLE_FILE.exists(), f"Example file not found: {EXAMPLE_FILE}"

    def test_schema_matches_pydantic_model(self) -> None:
        with SCHEMA_FILE.open() as f:
            committed = json.load(f)
        live = MintRequest.model_json_schema()
        assert committed == live, (
            "schema/mint_request.v1.json is out of date with the Pydantic MintRequest model. "
            'Regenerate it with: python -c "from src.events.schemas import MintRequest; '
            'import json; print(json.dumps(MintRequest.model_json_schema(), indent=2))" '
            "> schema/mint_request.v1.json"
        )

    def test_example_validates_against_pydantic(self) -> None:
        with EXAMPLE_FILE.open() as f:
            data = json.load(f)
        msg = MintRequest.model_validate(data)
        assert msg.model_id == data["model_id"]
        assert sum(c.weight_bps for c in msg.contributors) == 10000

    def test_example_json_round_trip(self) -> None:
        with EXAMPLE_FILE.open() as f:
            data = json.load(f)
        msg = MintRequest.model_validate(data)
        dumped = json.loads(msg.model_dump_json())
        # Verify key fields survive the round-trip
        assert dumped["model_id"] == data["model_id"]
        assert dumped["idempotency_key"] == data["idempotency_key"]
        assert dumped["attestation_hash"] == data["attestation_hash"]


# ---------------------------------------------------------------------------
# MintRequestPublisher
# ---------------------------------------------------------------------------


class TestMintRequestPublisher:
    def _make_publisher(self) -> tuple[MintRequestPublisher, fakeredis.FakeRedis]:
        client = fakeredis.FakeRedis(decode_responses=True)
        pub = MintRequestPublisher(redis_client=client)
        return pub, client

    def test_publish_writes_to_correct_queue(self) -> None:
        pub, client = self._make_publisher()
        msg = _valid_mint_request()
        pub.publish(msg)
        assert client.llen(QUEUE_NAME) == 1

    def test_published_payload_is_valid_json(self) -> None:
        pub, client = self._make_publisher()
        msg = _valid_mint_request()
        pub.publish(msg)
        raw = client.lindex(QUEUE_NAME, 0)
        parsed = json.loads(raw)
        assert parsed["model_id"] == "model-a"
        assert parsed["message_type"] == "mint_request"

    def test_published_payload_round_trips_through_pydantic(self) -> None:
        pub, client = self._make_publisher()
        msg = _valid_mint_request()
        pub.publish(msg)
        raw = client.lindex(QUEUE_NAME, 0)
        recovered = MintRequest.model_validate_json(raw)
        assert recovered.model_id == msg.model_id
        assert recovered.idempotency_key == msg.idempotency_key

    def test_publish_multiple_messages_ordered_lifo_lpush(self) -> None:
        pub, client = self._make_publisher()
        msg1 = _valid_mint_request(message_id="msg-1", eval_id="eval-1")
        msg2 = _valid_mint_request(message_id="msg-2", eval_id="eval-2")
        pub.publish(msg1)
        pub.publish(msg2)
        assert client.llen(QUEUE_NAME) == 2
        # LPUSH means last pushed is at index 0
        first = json.loads(client.lindex(QUEUE_NAME, 0))
        assert first["message_id"] == "msg-2"

    def test_redis_error_propagates(self) -> None:
        broken_client = Mock()
        broken_client.lpush.side_effect = RedisConnectionError("connection refused")
        pub = MintRequestPublisher(redis_client=broken_client)
        msg = _valid_mint_request()
        with pytest.raises(RedisConnectionError):
            pub.publish(msg)

    def test_get_queue_depth(self) -> None:
        pub, client = self._make_publisher()
        assert pub.get_queue_depth() == 0
        pub.publish(_valid_mint_request())
        assert pub.get_queue_depth() == 1

    def test_close_does_not_raise(self) -> None:
        pub, _ = self._make_publisher()
        pub.close()

    def test_no_envelope_wrapping(self) -> None:
        """MintRequest is published as-is, not wrapped in a MessageEnvelope."""
        pub, client = self._make_publisher()
        pub.publish(_valid_mint_request())
        raw = client.lindex(QUEUE_NAME, 0)
        parsed = json.loads(raw)
        assert "payload" not in parsed
        assert parsed["message_type"] == "mint_request"


# ---------------------------------------------------------------------------
# Contributor extraction helpers
# ---------------------------------------------------------------------------


_WALLET_A = "0x742d35cc6634c0532925a3b844bc9e7595f62341"
_WALLET_B = "0x6c3e007f281f6948b37c511a11e43c8026d2f069"


class TestExtractContributorsFromSpec:
    def test_extracts_weight_bps_directly(self) -> None:
        spec = {
            "contributors": [
                {"wallet_address": _WALLET_A, "weight_bps": 7000},
                {"wallet_address": _WALLET_B, "weight_bps": 3000},
            ]
        }
        result = _extract_contributors_from_spec(spec)
        assert len(result) == 2
        assert result[0]["weight_bps"] == 7000

    def test_extracts_fractional_weight(self) -> None:
        spec = {
            "contributors": [
                {"wallet_address": _WALLET_A, "weight": 0.7},
                {"wallet_address": _WALLET_B, "weight": 0.3},
            ]
        }
        result = _extract_contributors_from_spec(spec)
        assert len(result) == 2
        assert result[0]["weight_bps"] == 7000
        assert result[1]["weight_bps"] == 3000

    def test_invalid_wallet_skipped(self) -> None:
        spec = {
            "contributors": [
                {"wallet_address": "not-an-address", "weight_bps": 5000},
                {"wallet_address": _WALLET_A, "weight_bps": 5000},
            ]
        }
        result = _extract_contributors_from_spec(spec)
        assert len(result) == 1
        assert result[0]["weight_bps"] == 5000

    def test_missing_contributors_key_returns_empty(self) -> None:
        result = _extract_contributors_from_spec({"model_id": "x"})
        assert result == []

    def test_empty_contributors_returns_empty(self) -> None:
        result = _extract_contributors_from_spec({"contributors": []})
        assert result == []


class TestExtractContributorsFromTags:
    def test_extracts_from_json_tag(self) -> None:
        tags = {
            "hokusai.contributors": json.dumps([{"wallet_address": _WALLET_A, "weight_bps": 10000}])
        }
        result = _extract_contributors_from_tags(tags)
        assert len(result) == 1
        assert result[0]["weight_bps"] == 10000

    def test_missing_tag_returns_empty(self) -> None:
        assert _extract_contributors_from_tags({}) == []

    def test_malformed_json_returns_empty(self) -> None:
        assert _extract_contributors_from_tags({"hokusai.contributors": "not-json{{"}) == []


class TestNormalizeWeightsTo10000:
    def test_already_sums_to_10000_unchanged(self) -> None:
        contribs = [
            {"wallet_address": "0x" + "a" * 40, "weight_bps": 6000},
            {"wallet_address": "0x" + "b" * 40, "weight_bps": 4000},
        ]
        result = _normalize_weights_to_10000(contribs)
        assert sum(c["weight_bps"] for c in result) == 10000

    def test_adjusts_largest_for_remainder(self) -> None:
        contribs = [
            {"wallet_address": "0x" + "a" * 40, "weight_bps": 6001},
            {"wallet_address": "0x" + "b" * 40, "weight_bps": 4000},
        ]
        result = _normalize_weights_to_10000(contribs)
        assert sum(c["weight_bps"] for c in result) == 10000

    def test_empty_list_unchanged(self) -> None:
        assert _normalize_weights_to_10000([]) == []


# ---------------------------------------------------------------------------
# _build_mint_request
# ---------------------------------------------------------------------------


def _make_acceptance_event(**overrides) -> DeltaOneAcceptanceEvent:
    defaults = {
        "model_id": "model-a",
        "model_id_uint": _MODEL_ID_UINT,
        "eval_id": _EVAL_ID,
        "mlflow_run_id": "run-abc",
        "benchmark_spec_id": _SPEC_ID,
        "primary_metric_name": "accuracy",
        "primary_metric_mlflow_name": "accuracy",
        "metric_family": "proportion",
        "baseline_score_bps": 7800,
        "candidate_score_bps": 8100,
        "delta_bps": 300,
        "delta_threshold_bps": 100,
        "attestation_hash": _ATT_HASH,
        "idempotency_key": _IDEMPOTENCY_KEY,
        "guardrail_summary": DeltaOneGuardrailSummary(
            total_guardrails=0, guardrails_passed=0, breaches=[]
        ),
        "max_cost_usd_micro": 5_000_000,
        "actual_cost_usd_micro": 2_340_000,
    }
    defaults.update(overrides)
    return DeltaOneAcceptanceEvent(**defaults)


class TestBuildMintRequest:
    def _make_ctx_with_contributors(self, contributors):
        decision = DeltaOneDecision(
            accepted=True,
            reason="accepted",
            run_id="run-cand",
            baseline_run_id="run-base",
            model_id="model-a",
            dataset_hash="sha256:" + "a" * 64,
            metric_name="accuracy",
            delta_percentage_points=3.0,
            ci95_low_percentage_points=0.5,
            ci95_high_percentage_points=5.5,
            n_current=1000,
            n_baseline=900,
            evaluated_at=datetime.now(timezone.utc),
        )
        return _EventContext(
            decision=decision,
            baseline_score=0.78,
            candidate_score=0.81,
            contributors=contributors,
        )

    def test_builds_valid_mint_request(self) -> None:
        event = _make_acceptance_event()
        contribs = [
            {"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}
        ]
        ctx = self._make_ctx_with_contributors(contribs)
        msg = _build_mint_request(event, ctx)
        assert isinstance(msg, MintRequest)
        assert msg.model_id == "model-a"
        assert msg.evaluation.baseline_score_bps == 7800
        assert msg.evaluation.new_score_bps == 8100
        assert len(msg.contributors) == 1

    def test_scores_match_acceptance_event(self) -> None:
        event = _make_acceptance_event(
            baseline_score_bps=5000, candidate_score_bps=6000, delta_bps=1000
        )
        contribs = [
            {"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}
        ]
        ctx = self._make_ctx_with_contributors(contribs)
        msg = _build_mint_request(event, ctx)
        assert msg.evaluation.baseline_score_bps == 5000
        assert msg.evaluation.new_score_bps == 6000

    def test_cost_fields_match_acceptance_event(self) -> None:
        event = _make_acceptance_event(max_cost_usd_micro=1_000_000, actual_cost_usd_micro=500_000)
        contribs = [
            {"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}
        ]
        ctx = self._make_ctx_with_contributors(contribs)
        msg = _build_mint_request(event, ctx)
        assert msg.evaluation.max_cost_usd_micro == 1_000_000
        assert msg.evaluation.actual_cost_usd_micro == 500_000

    def test_no_contributors_raises_event_payload_error(self) -> None:
        event = _make_acceptance_event()
        ctx = self._make_ctx_with_contributors([])
        with pytest.raises(EventPayloadError, match="contributors"):
            _build_mint_request(event, ctx)

    def test_no_context_raises_on_empty_contributors(self) -> None:
        event = _make_acceptance_event()
        with pytest.raises(EventPayloadError, match="contributors"):
            _build_mint_request(event, None)

    def test_idempotency_key_preserved_from_acceptance_event(self) -> None:
        event = _make_acceptance_event()
        contribs = [
            {"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}
        ]
        ctx = self._make_ctx_with_contributors(contribs)
        msg = _build_mint_request(event, ctx)
        assert msg.idempotency_key == event.idempotency_key

    def test_sample_sizes_from_decision(self) -> None:
        event = _make_acceptance_event()
        contribs = [
            {"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}
        ]
        ctx = self._make_ctx_with_contributors(contribs)
        msg = _build_mint_request(event, ctx)
        assert msg.evaluation.sample_size_baseline == 900
        assert msg.evaluation.sample_size_candidate == 1000


# ---------------------------------------------------------------------------
# Orchestrator integration tests
# ---------------------------------------------------------------------------


def _make_decision(accepted: bool = True, reason: str = "accepted") -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=accepted,
        reason=reason,
        run_id="run-cand",
        baseline_run_id="run-base",
        model_id="model-x",
        dataset_hash="sha256:" + "a" * 64,
        metric_name="workflow_success_rate_under_budget",
        delta_percentage_points=2.0,
        ci95_low_percentage_points=0.5,
        ci95_high_percentage_points=3.5,
        n_current=1000,
        n_baseline=1000,
        evaluated_at=datetime.now(timezone.utc),
    )


class _FakeMlflowClient:
    def __init__(self, run_metrics=None, initial_tags=None) -> None:
        self._run_metrics = run_metrics or {}
        self.tags = dict(initial_tags or {})

    def get_run(self, _run_id):
        return SimpleNamespace(data=SimpleNamespace(metrics=self._run_metrics, tags=self.tags))

    def set_tag(self, _run_id, key, value):
        self.tags[key] = value


def _make_spec_with_contributors(contributors=None, **extra) -> dict:
    spec = {
        "model_id": "model-x",
        "model_id_uint": "99001",
        "spec_id": _SPEC_ID,
        "eval_spec": {
            "primary_metric": {
                "name": "workflow_success_rate_under_budget",
                "direction": "higher_is_better",
            },
            "metric_family": "proportion",
            "guardrails": [],
        },
    }
    if contributors is not None:
        spec["contributors"] = contributors
    spec.update(extra)
    return spec


def _make_orchestrator_with_publisher(
    decision,
    publisher=None,
    run_metrics=None,
    extra_tags=None,
):
    evaluator = Mock()
    evaluator.evaluate_for_model.return_value = decision
    evaluator.delta_threshold_pp = 1.0
    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-ok",
        timestamp=datetime.now(timezone.utc),
    )
    tags = {"hokusai.eval_id": _EVAL_ID}
    if extra_tags:
        tags.update(extra_tags)
    client = _FakeMlflowClient(run_metrics=run_metrics or {}, initial_tags=tags)
    orch = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=publisher,
    )
    return orch, mint_hook, client


class TestOrchestratorPublishesOnAcceptance:
    def _spec_with_contributors(self):
        return _make_spec_with_contributors(
            contributors=[{"wallet_address": _WALLET_A, "weight_bps": 10000}]
        )

    def test_publishes_on_accepted_evaluation(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        fake_client = fakeredis.FakeRedis(decode_responses=True)
        publisher = MintRequestPublisher(redis_client=fake_client)
        decision = _make_decision(accepted=True)
        orch, _, _ = _make_orchestrator_with_publisher(
            decision,
            publisher=publisher,
            run_metrics={"workflow_success_rate_under_budget": 0.87},
        )

        outcome = orch.process_evaluation_with_spec(
            "run-cand", "run-base", self._spec_with_contributors()
        )

        assert outcome.status == "success"
        assert fake_client.llen(QUEUE_NAME) == 1

    def test_published_message_has_correct_scores(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        fake_client = fakeredis.FakeRedis(decode_responses=True)
        publisher = MintRequestPublisher(redis_client=fake_client)
        decision = _make_decision(accepted=True)
        orch, _, _ = _make_orchestrator_with_publisher(
            decision,
            publisher=publisher,
            run_metrics={"workflow_success_rate_under_budget": 0.87},
        )

        orch.process_evaluation_with_spec("run-cand", "run-base", self._spec_with_contributors())

        raw = fake_client.lindex(QUEUE_NAME, 0)
        data = json.loads(raw)
        assert "evaluation" in data
        eval_data = data["evaluation"]
        assert 0 <= eval_data["baseline_score_bps"] <= 10000
        assert 0 <= eval_data["new_score_bps"] <= 10000

    def test_no_publish_when_no_publisher_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        decision = _make_decision(accepted=True)
        orch, _, _ = _make_orchestrator_with_publisher(
            decision,
            publisher=None,
            run_metrics={"workflow_success_rate_under_budget": 0.87},
        )
        with pytest.raises(RuntimeError, match="MintRequestPublisher is required"):
            orch.process_evaluation_with_spec(
                "run-cand",
                "run-base",
                self._spec_with_contributors(),
            )

    def test_no_publish_on_primary_rejection(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        fake_client = fakeredis.FakeRedis(decode_responses=True)
        publisher = MintRequestPublisher(redis_client=fake_client)
        decision = _make_decision(accepted=False, reason="delta_below_threshold")
        orch, _, _ = _make_orchestrator_with_publisher(decision, publisher=publisher)

        outcome = orch.process_evaluation_with_spec(
            "run-cand", "run-base", self._spec_with_contributors()
        )

        assert outcome.status == "not_eligible"
        assert fake_client.llen(QUEUE_NAME) == 0

    def test_no_publish_on_guardrail_breach(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        fake_client = fakeredis.FakeRedis(decode_responses=True)
        publisher = MintRequestPublisher(redis_client=fake_client)
        decision = _make_decision(accepted=True)
        spec = _make_spec_with_contributors(
            contributors=[{"wallet_address": _WALLET_A, "weight_bps": 10000}]
        )
        spec["eval_spec"]["guardrails"] = [
            {"name": "cost_per_call", "direction": "lower_is_better", "threshold": 0.10}
        ]
        orch, _, _ = _make_orchestrator_with_publisher(
            decision,
            publisher=publisher,
            run_metrics={"cost_per_call": 0.50},
        )

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        assert outcome.status == "guardrail_breach"
        assert fake_client.llen(QUEUE_NAME) == 0

    def test_publish_failure_prevents_canonical_score_advance(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        broken_client = Mock()
        broken_client.lpush.side_effect = RedisConnectionError("refused")
        publisher = MintRequestPublisher(redis_client=broken_client)

        decision = _make_decision(accepted=True)
        orch, _, mlflow_client = _make_orchestrator_with_publisher(
            decision,
            publisher=publisher,
            run_metrics={"workflow_success_rate_under_budget": 0.87},
        )

        with pytest.raises(RedisConnectionError):
            orch.process_evaluation_with_spec(
                "run-cand", "run-base", self._spec_with_contributors()
            )

        # Canonical score tag must NOT have been set
        assert "hokusai.canonical_score" not in mlflow_client.tags
        assert mlflow_client.tags["hokusai.mint.status"] == "requested"
        orch.mint_hook.mint.assert_not_called()

    def test_publish_occurs_before_canonical_score_advance(self, monkeypatch) -> None:
        """Verify that publish() is called before _advance_canonical_score via call order."""
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        call_order: list[str] = []

        fake_client = fakeredis.FakeRedis(decode_responses=True)

        class TrackingPublisher:
            def publish(self, message: MintRequest) -> None:
                call_order.append("publish")
                fake_client.lpush(QUEUE_NAME, message.model_dump_json())

        decision = _make_decision(accepted=True)
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success",
            audit_ref="audit-ok",
            timestamp=datetime.now(timezone.utc),
        )

        tags = {"hokusai.eval_id": _EVAL_ID}

        class TrackingMlflowClient(_FakeMlflowClient):
            def set_tag(self, run_id, key, value):
                if key == "hokusai.canonical_score":
                    call_order.append("canonical_score_advance")
                super().set_tag(run_id, key, value)

        mlflow_client = TrackingMlflowClient(
            run_metrics={"workflow_success_rate_under_budget": 0.87},
            initial_tags=tags,
        )

        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator,
            mint_hook=mint_hook,
            mlflow_client=mlflow_client,
            mint_request_publisher=TrackingPublisher(),
        )

        orch.process_evaluation_with_spec("run-cand", "run-base", self._spec_with_contributors())

        assert "publish" in call_order
        assert "canonical_score_advance" in call_order
        assert call_order.index("publish") < call_order.index("canonical_score_advance")

    def test_secondary_dry_run_keeps_primary_success(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        fake_client = fakeredis.FakeRedis(decode_responses=True)
        publisher = MintRequestPublisher(redis_client=fake_client)
        decision = _make_decision(accepted=True)
        orch, mint_hook, mlflow_client = _make_orchestrator_with_publisher(
            decision,
            publisher=publisher,
            run_metrics={"workflow_success_rate_under_budget": 0.87},
        )
        mint_hook.mint.return_value = TokenMintResult(
            status="dry_run",
            audit_ref="audit-dry-run",
            timestamp=datetime.now(timezone.utc),
        )

        outcome = orch.process_evaluation_with_spec(
            "run-cand", "run-base", self._spec_with_contributors()
        )

        assert outcome.status == "success"
        assert outcome.mint_result is not None
        assert outcome.mint_result.status == "dry_run"
        assert mlflow_client.tags["hokusai.mint.status"] == "published"
        assert mlflow_client.tags["hokusai.mint.legacy_status"] == "dry_run"
        assert fake_client.llen(QUEUE_NAME) == 1

    def test_secondary_failure_keeps_primary_success(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        fake_client = fakeredis.FakeRedis(decode_responses=True)
        publisher = MintRequestPublisher(redis_client=fake_client)
        decision = _make_decision(accepted=True)
        orch, mint_hook, mlflow_client = _make_orchestrator_with_publisher(
            decision,
            publisher=publisher,
            run_metrics={"workflow_success_rate_under_budget": 0.87},
        )
        mint_hook.mint.side_effect = RuntimeError("legacy hook exploded")

        outcome = orch.process_evaluation_with_spec(
            "run-cand", "run-base", self._spec_with_contributors()
        )

        assert outcome.status == "success"
        assert outcome.mint_result is not None
        assert outcome.mint_result.status == "failed"
        assert mlflow_client.tags["hokusai.mint.status"] == "published"
        assert mlflow_client.tags["hokusai.mint.legacy_status"] == "failed"
        assert fake_client.llen(QUEUE_NAME) == 1
