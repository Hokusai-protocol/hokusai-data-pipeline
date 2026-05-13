"""Integration coverage for the launch sales lead-scoring benchmark spec.

Auth note: tests use fake MLflow clients only; no live MLflow requests are made.
Production auth relies on MLFLOW_TRACKING_TOKEN / Authorization env wiring.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.evaluation.scorers import resolve_scorer
from src.events.schemas import MintRequest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "schema" / "examples"
RUN_ID = "sales-lead-scoring-candidate-run"
BASELINE_RUN_ID = "sales-lead-scoring-baseline-run"
MODEL_ID = "sales-lead-scorer-launch"
MODEL_ID_UINT = "99001"
SPEC_ID = "bspec-sales-lead-scoring-launch-v1"
EVAL_ID = "eval-sales-lead-scoring-launch-001"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _score_rows(rows: list[dict], scorer_ref: str) -> float:
    scorer = resolve_scorer(scorer_ref)
    return float(scorer.callable_(rows))


def _build_spec() -> dict:
    return {
        "spec_id": SPEC_ID,
        "model_id": MODEL_ID,
        "model_id_uint": MODEL_ID_UINT,
        "contributors": [
            {
                "contributor_id": MODEL_ID,
                "wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341",
                "weight_bps": 10000,
            }
        ],
        "eval_spec": _load_example("sales_eval_spec.lead_scoring.v1.json"),
    }


class _TrackingPublisher:
    def __init__(self) -> None:
        self.messages: list[MintRequest] = []

    def publish(self, message: MintRequest) -> None:
        self.messages.append(message)


class _FakeMlflowClient:
    def __init__(self, runs: dict[str, SimpleNamespace]) -> None:
        self._runs = runs
        self.tags_set: dict[str, dict[str, str]] = {}

    def get_run(self, run_id: str) -> SimpleNamespace:
        return self._runs[run_id]

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        self.tags_set.setdefault(run_id, {})[key] = value
        run = self._runs[run_id]
        run.data.tags[key] = value


def _make_run(metrics: dict[str, float], tags: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        data=SimpleNamespace(
            metrics=metrics,
            tags={
                "hokusai.eval_id": EVAL_ID,
                "hokusai.actual_cost_usd": "2.25",
                **(tags or {}),
            },
        )
    )


def _make_decision(
    candidate_score: float,
    baseline_score: float,
    accepted: bool,
) -> DeltaOneDecision:
    delta_pp = (candidate_score - baseline_score) * 100.0
    return DeltaOneDecision(
        accepted=accepted,
        reason="accepted" if accepted else "delta_below_threshold",
        run_id=RUN_ID,
        baseline_run_id=BASELINE_RUN_ID,
        model_id=MODEL_ID,
        dataset_hash="sha256:" + "a" * 64,
        metric_name="sales:qualified_meeting_rate",
        delta_percentage_points=delta_pp,
        ci95_low_percentage_points=max(delta_pp - 2.0, 0.0),
        ci95_high_percentage_points=max(delta_pp + 2.0, 0.0),
        n_current=3,
        n_baseline=3,
        evaluated_at=datetime.now(timezone.utc),
    )


def test_above_threshold_rows_emit_valid_acceptance_event_and_mint_request(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    spec = _build_spec()
    rows = [_load_example("sales_outcome_row.lead_scoring_qualified.v1.json") for _ in range(3)]
    primary_ref = spec["eval_spec"]["primary_metric"]["scorer_ref"]
    candidate_score = _score_rows(rows, primary_ref)
    baseline_score = 0.70

    decision = _make_decision(candidate_score, baseline_score, accepted=True)
    evaluator = Mock()
    evaluator.evaluate_for_model.return_value = decision
    evaluator.delta_threshold_pp = 15.0

    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-sales-lead-scoring",
        timestamp=datetime.now(timezone.utc),
    )
    publisher = _TrackingPublisher()
    client = _FakeMlflowClient(
        {
            RUN_ID: _make_run(
                metrics={
                    "sales:qualified_meeting_rate": candidate_score,
                    "sales_qualified_meeting_rate": candidate_score,
                    "sales:unsubscribe_rate": 0.0,
                    "sales:spam_complaint_rate": 0.0,
                }
            ),
            BASELINE_RUN_ID: _make_run(
                metrics={
                    "sales:qualified_meeting_rate": baseline_score,
                    "sales_qualified_meeting_rate": baseline_score,
                },
                tags={},
            ),
        }
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=publisher,
    )

    outcome = orchestrator.process_evaluation_with_spec(RUN_ID, BASELINE_RUN_ID, spec)

    assert outcome.status == "success"
    assert outcome.acceptance_event is not None
    assert outcome.acceptance_event.primary_metric_name == "sales:qualified_meeting_rate"
    assert outcome.acceptance_event.metric_family == "proportion"
    assert outcome.acceptance_event.candidate_score_bps == 10000
    assert outcome.acceptance_event.baseline_score_bps == 7000
    assert outcome.acceptance_event.delta_bps == 3000
    assert outcome.acceptance_event.delta_threshold_bps == 1500
    assert outcome.acceptance_event.guardrail_summary.total_guardrails == 2
    assert outcome.acceptance_event.guardrail_summary.guardrails_passed == 2

    assert len(publisher.messages) == 1
    published = MintRequest.model_validate_json(publisher.messages[0].model_dump_json())
    assert published.model_id == MODEL_ID
    assert published.eval_id == EVAL_ID
    assert published.evaluation.metric_name == "sales:qualified_meeting_rate"
    assert published.evaluation.metric_family == "proportion"
    assert published.evaluation.new_score_bps == 10000
    assert published.evaluation.baseline_score_bps == 7000
    assert len(published.contributors) == 1
    assert published.contributors[0].weight_bps == 10000


def test_below_threshold_rows_do_not_emit_mint_request(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    spec = _build_spec()
    rows = [
        _load_example("sales_outcome_row.lead_scoring_qualified.v1.json"),
        _load_example("sales_outcome_row.lead_scoring_unqualified.v1.json"),
        _load_example("sales_outcome_row.lead_scoring_unqualified.v1.json"),
    ]
    primary_ref = spec["eval_spec"]["primary_metric"]["scorer_ref"]
    candidate_score = _score_rows(rows, primary_ref)
    baseline_score = 0.20

    decision = _make_decision(candidate_score, baseline_score, accepted=False)
    evaluator = Mock()
    evaluator.evaluate_for_model.return_value = decision
    evaluator.delta_threshold_pp = 15.0

    mint_hook = Mock()
    publisher = _TrackingPublisher()
    client = _FakeMlflowClient(
        {
            RUN_ID: _make_run(
                metrics={
                    "sales:qualified_meeting_rate": candidate_score,
                    "sales_qualified_meeting_rate": candidate_score,
                    "sales:unsubscribe_rate": 0.0,
                    "sales:spam_complaint_rate": 0.0,
                }
            ),
            BASELINE_RUN_ID: _make_run(
                metrics={
                    "sales:qualified_meeting_rate": baseline_score,
                    "sales_qualified_meeting_rate": baseline_score,
                },
                tags={},
            ),
        }
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=publisher,
    )

    outcome = orchestrator.process_evaluation_with_spec(RUN_ID, BASELINE_RUN_ID, spec)

    assert outcome.status == "not_eligible"
    assert outcome.acceptance_event is None
    assert publisher.messages == []
    mint_hook.mint.assert_not_called()
