from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from src.cli.attestation import build_attestation_payload, create_attestation
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.evaluation.event_payload import make_idempotency_key
from src.evaluation.manifest import HokusaiEvaluationManifest
from src.evaluation.validation import validate_manifest


def _base_attestation_inputs() -> dict[str, object]:
    return {
        "model_id": "model-a",
        "eval_spec": "deltaone",
        "provider": "mlflow",
        "seed": None,
        "temperature": None,
        "results": {"accepted": True, "delta_percentage_points": 1.5},
        "attestation_nonce": "nonce-123",
    }


def _base_manifest_kwargs() -> dict[str, object]:
    return {
        "model_id": "model-a",
        "eval_id": "eval-001",
        "dataset": {"id": "dataset-1", "hash": "sha256:abc123", "num_samples": 100},
        "primary_metric": {"name": "accuracy", "value": 0.95, "higher_is_better": True},
        "metrics": [{"name": "accuracy", "value": 0.95, "higher_is_better": True}],
        "mlflow_run_id": "run-123",
        "created_at": "2026-01-01T00:00:00Z",
    }


def _attribution_block(
    *,
    method: str = "neighbor_provenance",
    report_hash: str = "a" * 64,
) -> dict[str, object]:
    return {
        "method": method,
        "report_hash": report_hash,
        "efficiency_gap": 0.0,
        "seed": 7,
        "sample_plan": {"permutations": 128, "truncation_tolerance": 0.001},
        "contributors": [
            {"wallet": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 6000},
            {"wallet": "0x6c3e007f281f6948b37c511a11e43c8026d2f069", "weight_bps": 4000},
        ],
    }


def _decision() -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=True,
        reason="accepted",
        run_id="run-candidate",
        baseline_run_id="run-baseline",
        model_id="model-a",
        dataset_hash="sha256:" + "b" * 64,
        metric_name="accuracy",
        delta_percentage_points=1.5,
        ci95_low_percentage_points=0.9,
        ci95_high_percentage_points=2.1,
        n_current=1000,
        n_baseline=1000,
        evaluated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_attribution_report_hash_changes_attestation_hash() -> None:
    first_hash, _ = create_attestation(
        **_base_attestation_inputs(),
        attribution_report_hash="1" * 64,
    )
    second_hash, _ = create_attestation(
        **_base_attestation_inputs(),
        attribution_report_hash="2" * 64,
    )

    assert first_hash != second_hash


def test_no_attribution_is_backward_compat() -> None:
    attestation_hash, payload = create_attestation(**_base_attestation_inputs())

    expected_payload = build_attestation_payload(**_base_attestation_inputs())

    assert payload == expected_payload
    assert "attribution_report_hash" not in payload
    assert "benchmark_spec_id" not in payload
    assert "dataset_hash" not in payload
    assert attestation_hash == create_attestation(**_base_attestation_inputs())[0]


def test_benchmark_spec_id_changes_attestation_hash() -> None:
    first_hash, _ = create_attestation(**_base_attestation_inputs())
    second_hash, payload = create_attestation(
        **_base_attestation_inputs(),
        benchmark_spec_id="spec-001",
    )

    assert first_hash != second_hash
    assert payload["benchmark_spec_id"] == "spec-001"


def test_dataset_hash_changes_attestation_hash() -> None:
    first_hash, _ = create_attestation(**_base_attestation_inputs())
    second_hash, payload = create_attestation(
        **_base_attestation_inputs(),
        dataset_hash="sha256:" + "c" * 64,
    )

    assert first_hash != second_hash
    assert payload["dataset_hash"] == "sha256:" + "c" * 64


def test_attestation_hash_propagates_to_idempotency_key() -> None:
    first_hash, _ = create_attestation(
        **_base_attestation_inputs(),
        attribution_report_hash="1" * 64,
    )
    second_hash, _ = create_attestation(
        **_base_attestation_inputs(),
        attribution_report_hash="2" * 64,
    )

    assert make_idempotency_key(123, first_hash) != make_idempotency_key(123, second_hash)


def test_hem_attribution_field_roundtrip() -> None:
    manifest = HokusaiEvaluationManifest(
        **_base_manifest_kwargs(),
        attribution=_attribution_block(),
    )

    payload = manifest.to_dict()
    restored = HokusaiEvaluationManifest.from_dict(payload)

    assert restored.attribution == _attribution_block()
    assert restored.to_dict() == payload


def test_hem_compute_hash_changes_with_attribution() -> None:
    first = HokusaiEvaluationManifest(**_base_manifest_kwargs())
    second = HokusaiEvaluationManifest(
        **_base_manifest_kwargs(),
        attribution=_attribution_block(),
    )

    assert first.compute_hash() != second.compute_hash()


def test_hem_attribution_backward_compat() -> None:
    manifest = HokusaiEvaluationManifest(**_base_manifest_kwargs())
    payload = manifest.to_dict()

    assert "attribution" not in payload
    assert validate_manifest(payload) == []
    assert HokusaiEvaluationManifest.from_dict(payload).attribution is None


@pytest.mark.parametrize("method", ["neighbor_provenance", "loco_shapley", "shapley"])
def test_method_agnostic_attribution_block(method: str) -> None:
    payload = HokusaiEvaluationManifest(
        **_base_manifest_kwargs(),
        attribution=_attribution_block(method=method),
    ).to_dict()

    assert validate_manifest(payload) == []


def test_orchestrator_create_signed_attestation_includes_benchmark_spec() -> None:
    orchestrator = DeltaOneMintOrchestrator(
        evaluator=Mock(),
        mint_hook=Mock(),
        mlflow_client=Mock(),
        mint_request_publisher=Mock(),
        reward_entitlement_notifier=Mock(),
    )

    _, payload = orchestrator._create_signed_attestation(
        _decision(),
        benchmark_spec_id="spec-001",
    )

    assert payload["benchmark_spec_id"] == "spec-001"
    assert payload["dataset_hash"] == _decision().dataset_hash


def test_orchestrator_attribution_report_changes_attestation_hash() -> None:
    orchestrator = DeltaOneMintOrchestrator(
        evaluator=Mock(),
        mint_hook=Mock(),
        mlflow_client=Mock(),
        mint_request_publisher=Mock(),
        reward_entitlement_notifier=Mock(),
    )
    first_report = {
        "method": "neighbor_provenance",
        "contributors": [
            {"wallet": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}
        ],
    }
    second_report = {
        "method": "neighbor_provenance",
        "contributors": [
            {"wallet": "0x6c3e007f281f6948b37c511a11e43c8026d2f069", "weight_bps": 10000}
        ],
    }

    first_hash, first_payload = orchestrator._create_signed_attestation(
        _decision(),
        attribution_report=first_report,
    )
    second_hash, second_payload = orchestrator._create_signed_attestation(
        _decision(),
        attribution_report=second_report,
    )

    assert first_hash != second_hash
    assert (
        first_payload["attribution_report_hash"]
        == hashlib.sha256(
            b'{"contributors":[{"wallet":"0x742d35cc6634c0532925a3b844bc9e7595f62341","weight_bps":10000}],"method":"neighbor_provenance"}'
        ).hexdigest()
    )
    assert (
        second_payload["attribution_report_hash"]
        == hashlib.sha256(
            b'{"contributors":[{"wallet":"0x6c3e007f281f6948b37c511a11e43c8026d2f069","weight_bps":10000}],"method":"neighbor_provenance"}'
        ).hexdigest()
    )
