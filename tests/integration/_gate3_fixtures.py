"""Shared fixtures for the Gate 3 off-chain fakeredis integration suite.

Auth note: tests use fake MLflow clients only; no live MLflow requests are made.
Production auth relies on MLFLOW_TRACKING_TOKEN / Authorization env wiring.
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import fakeredis
import jsonschema
import pandas as pd
import pytest

from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.attribution.contributor_set import derive_contributor_set
from src.evaluation.attribution.neighbor_provenance import attribute as attribute_neighbors
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.evaluation.tags import (
    WEIGHT_COMMITMENT_BASELINE_TAG,
    WEIGHT_COMMITMENT_CANDIDATE_TAG,
)
from src.events.publishers.mint_request_publisher import MintRequestPublisher
from src.lineage.weight_commitment import compute_weight_commitment
from src.utils.metric_naming import derive_mlflow_name

MODEL_ID = "model-30"
MODEL_ID_UINT = "99002"
BASELINE_RUN_ID = "run-baseline"
CANDIDATE_RUN_ID = "run-candidate"
EVAL_ID = "eval-gate3-001"
SPEC_ID = "spec-gate3-offchain-v1"
PRIMARY_METRIC = "workflow_success_rate_under_budget"
DATASET_HASH = "sha256:" + "d" * 64
MANIFEST_HASH = "sha256:" + "m" * 64
WEIGHT_ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "model_30_weight_artifact"
WEIGHT_CANDIDATE_COMMITMENT = f"0x{compute_weight_commitment(WEIGHT_ARTIFACT_DIR).root}"
WEIGHT_BASELINE_ONCHAIN_HEAD = "0x" + ("12ab" * 16)
GATE3_ATTESTER_SIGNATURE = "0x" + ("1" * 128) + "1b"


def _wallet(index: int) -> str:
    return f"0x{index:040x}"


@dataclass(frozen=True)
class SeededFrames:
    baseline: pd.DataFrame
    candidate: pd.DataFrame
    created_at: str
    seed: int


class FakeRewardNotifier:
    def __init__(self, fail_statuses: set[str] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_statuses = fail_statuses or set()

    def notify_reward_entitlement(
        self,
        *,
        mint_request,
        status,
        mint_result=None,
        recipient_kinds=None,
        reward_tokens=None,
        token_address=None,
    ):
        self.calls.append(
            {"mint_request": mint_request, "status": status, "mint_result": mint_result}
        )
        if status in self.fail_statuses:
            return False, f"{status} failed"
        return True, None


class FakeMlflowClient:
    def __init__(self, runs: dict[str, SimpleNamespace]) -> None:
        self._runs = runs

    def get_run(self, run_id: str):
        return self._runs[run_id]

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        self._runs[run_id].data.tags[key] = value

    def tags_for(self, run_id: str) -> dict[str, str]:
        return self._runs[run_id].data.tags


def load_validator(schema_name: str) -> jsonschema.Draft202012Validator:
    schema_path = Path(__file__).resolve().parents[2] / "schema" / schema_name
    with schema_path.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    return jsonschema.Draft202012Validator(schema)


@pytest.fixture(scope="session")
def schema_validators() -> dict[str, jsonschema.Draft202012Validator]:
    return {
        "attribution_report": load_validator("attribution_report.v1.json"),
        "mint_request": load_validator("mint_request.v1.json"),
        "mint_request_consumer": load_validator("mint_request.consumer.v1.json"),
    }


@pytest.fixture()
def fake_redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


def seeded_per_row_frames(seed: int = 1729) -> SeededFrames:
    rng = random.Random(seed)
    created_at = (
        datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
        .replace(second=seed % 60)
        .isoformat()
        .replace("+00:00", "Z")
    )
    suffix = f"{seed:04d}"
    baseline_rows = []
    candidate_rows = []
    row_ids = [f"row-{index}" for index in range(1, 6)]
    improved_neighbors = {
        "row-1": [
            {"wallet": _wallet(1), "weight": 0.8, "submission_id": f"sub-a-{suffix}"},
            {"wallet": _wallet(2), "weight": 0.2, "submission_id": f"sub-b-{suffix}"},
        ],
        "row-2": [
            {"wallet": _wallet(1), "weight": 0.1, "submission_id": f"sub-a-{suffix}"},
            {"wallet": _wallet(3), "weight": 0.9, "submission_id": f"sub-c-{suffix}"},
        ],
        "row-3": [
            {"wallet": _wallet(2), "weight": 0.3, "submission_id": f"sub-b-{suffix}"},
            {"wallet": _wallet(3), "weight": 0.7, "submission_id": f"sub-c-{suffix}"},
        ],
    }
    baseline_outcomes = {
        "row-1": False,
        "row-2": False,
        "row-3": False,
        "row-4": bool(rng.randint(0, 0)),
        "row-5": True,
    }
    candidate_outcomes = {
        "row-1": True,
        "row-2": True,
        "row-3": True,
        "row-4": False,
        "row-5": True,
    }
    for row_id in row_ids:
        baseline_rows.append(
            {
                "row_id": row_id,
                "completed_successfully": baseline_outcomes[row_id],
            }
        )
        candidate_rows.append(
            {
                "row_id": row_id,
                "completed_successfully": candidate_outcomes[row_id],
                "neighbor_provenance": json.dumps(improved_neighbors.get(row_id, [])),
            }
        )
    return SeededFrames(
        baseline=pd.DataFrame(baseline_rows),
        candidate=pd.DataFrame(candidate_rows),
        created_at=created_at,
        seed=seed,
    )


def attribution_report(frames: SeededFrames) -> dict[str, object]:
    return attribute_neighbors(
        frames.baseline,
        frames.candidate,
        model_id=MODEL_ID,
        baseline_run_id=BASELINE_RUN_ID,
        candidate_run_id=CANDIDATE_RUN_ID,
        created_at=frames.created_at,
    )


def gate3_spec(
    report: dict[str, object],
    *,
    model_id_uint: str = MODEL_ID_UINT,
    guardrails: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "model_id": MODEL_ID,
        "model_id_uint": model_id_uint,
        "spec_id": SPEC_ID,
        "eval_spec": {
            "primary_metric": {
                "name": PRIMARY_METRIC,
                "direction": "higher_is_better",
            },
            "metric_family": "proportion",
            "measurement_policy": {"max_cost_usd": 5.0},
            "guardrails": list(guardrails or []),
        },
        "contributors": derive_contributor_set(report, candidate_run_id=CANDIDATE_RUN_ID),
    }


def make_decision(
    *,
    accepted: bool = True,
    reason: str | None = None,
    delta_percentage_points: float = 2.5,
    n_current: int = 1000,
) -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=accepted,
        reason=reason or ("accepted" if accepted else "delta_below_threshold"),
        run_id=CANDIDATE_RUN_ID,
        baseline_run_id=BASELINE_RUN_ID,
        model_id=MODEL_ID,
        dataset_hash=DATASET_HASH,
        metric_name=PRIMARY_METRIC,
        delta_percentage_points=delta_percentage_points,
        ci95_low_percentage_points=0.5,
        ci95_high_percentage_points=4.5,
        n_current=n_current,
        n_baseline=1000,
        evaluated_at=datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc),
    )


def build_orchestrator(
    *,
    fake_redis_client,
    monkeypatch,
    spec: dict[str, object],
    decision: DeltaOneDecision | None = None,
    candidate_metrics: dict[str, float] | None = None,
    baseline_metrics: dict[str, float] | None = None,
    candidate_tags: dict[str, str] | None = None,
    baseline_tags: dict[str, str] | None = None,
    attribution_report_loader=None,
):
    monkeypatch.setattr(
        "src.cli.attestation.uuid4",
        lambda: UUID("00000000-0000-0000-0000-000000000001"),
    )
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.read_current_model_head",
        Mock(return_value=WEIGHT_BASELINE_ONCHAIN_HEAD),
    )
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.DeltaOneMintOrchestrator._resolve_attester_signatures",
        Mock(return_value=[GATE3_ATTESTER_SIGNATURE]),
    )
    evaluator = Mock()
    evaluator.evaluate_for_model.return_value = decision or make_decision()
    evaluator.delta_threshold_pp = 1.0
    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-gate3",
        timestamp=datetime.now(timezone.utc),
    )
    metric_key = derive_mlflow_name(PRIMARY_METRIC)
    cand_metrics = {
        PRIMARY_METRIC: 0.87,
        metric_key: 0.87,
        "safety_violation_rate": 0.01,
    }
    if candidate_metrics:
        cand_metrics.update(candidate_metrics)
    base_metrics = {
        PRIMARY_METRIC: 0.62,
        metric_key: 0.62,
    }
    if baseline_metrics:
        base_metrics.update(baseline_metrics)
    candidate_run_tags = {
        "hokusai.eval_id": EVAL_ID,
        "hokusai.actual_cost_usd": "2.34",
        "hokusai.model_id_uint": str(spec["model_id_uint"]),
        WEIGHT_COMMITMENT_BASELINE_TAG: WEIGHT_BASELINE_ONCHAIN_HEAD,
        WEIGHT_COMMITMENT_CANDIDATE_TAG: WEIGHT_CANDIDATE_COMMITMENT,
    }
    if candidate_tags:
        candidate_run_tags.update(candidate_tags)
    runs = {
        CANDIDATE_RUN_ID: SimpleNamespace(
            data=SimpleNamespace(metrics=cand_metrics, tags=candidate_run_tags)
        ),
        BASELINE_RUN_ID: SimpleNamespace(
            data=SimpleNamespace(metrics=base_metrics, tags=dict(baseline_tags or {}))
        ),
    }
    client = FakeMlflowClient(runs)
    notifier = FakeRewardNotifier()
    publisher = MintRequestPublisher(redis_client=fake_redis_client)
    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=publisher,
        reward_entitlement_notifier=notifier,
        attribution_report_loader=attribution_report_loader,
    )
    return orchestrator, client, notifier, publisher


def report_loader(report: dict[str, object]):
    def _load(_candidate_tags: dict[str, str]):
        return copy.deepcopy(report)

    return _load
