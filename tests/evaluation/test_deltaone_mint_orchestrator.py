"""Unit tests for DeltaOne -> token mint orchestration."""

from __future__ import annotations

# Auth-hook note: this suite uses fake MLflow clients and patched webhook/mint
# calls only; no live MLflow requests are made.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator


class _FakeMlflowClient:
    def __init__(
        self,
        run_metrics: dict[str, float],
        initial_tags: dict[str, str] | None = None,
    ) -> None:
        self._run_metrics = run_metrics
        self.tags = dict(initial_tags or {})

    def get_run(self, _run_id: str):
        return SimpleNamespace(
            data=SimpleNamespace(
                metrics=self._run_metrics,
                tags=self.tags,
            )
        )

    def set_tag(self, _run_id: str, key: str, value: str) -> None:
        self.tags[key] = value


def _accepted_decision() -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=True,
        reason="accepted",
        run_id="run-candidate",
        baseline_run_id="run-baseline",
        model_id="model-a",
        dataset_hash="sha256:" + "a" * 64,
        metric_name="accuracy",
        delta_percentage_points=1.5,
        ci95_low_percentage_points=0.9,
        ci95_high_percentage_points=2.1,
        n_current=1000,
        n_baseline=1000,
        evaluated_at=datetime.now(timezone.utc),
    )


def test_acceptance_mint_success_advances_canonical_score(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision

    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-1",
        timestamp=datetime.now(timezone.utc),
    )

    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92})
    dispatch_mock = Mock(return_value=[])
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        dispatch_mock,
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "success"
    assert outcome.canonical_score_advanced is True
    assert client.tags["hokusai.canonical_score"] == "0.92"
    assert client.tags["hokusai.canonical_score_run_id"] == "run-candidate"
    assert client.tags["hokusai.mint.status"] == "success"
    mint_hook.mint.assert_called_once()
    assert mint_hook.mint.call_args.kwargs["idempotency_key"] == outcome.attestation_hash
    assert dispatch_mock.call_count == 2
    assert dispatch_mock.call_args_list[0].kwargs["event_type"] == "deltaone.achieved"
    assert dispatch_mock.call_args_list[1].kwargs["event_type"] == "deltaone.minted"


def test_acceptance_mint_failure_does_not_advance_canonical_score(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision

    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="failed",
        audit_ref="audit-2",
        timestamp=datetime.now(timezone.utc),
        error="upstream error",
    )

    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92})
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "failed"
    assert outcome.canonical_score_advanced is False
    assert "hokusai.canonical_score" not in client.tags
    assert client.tags["hokusai.mint.status"] == "failed"


def test_rejection_skips_mint(monkeypatch) -> None:
    decision = _accepted_decision()
    decision.accepted = False
    decision.reason = "delta_below_threshold"

    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    mint_hook = Mock()

    client = _FakeMlflowClient(run_metrics={"accuracy": 0.85})
    dispatch_mock = Mock(return_value=[])
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        dispatch_mock,
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "not_eligible"
    assert outcome.mint_result is None
    mint_hook.mint.assert_not_called()
    dispatch_mock.assert_not_called()
