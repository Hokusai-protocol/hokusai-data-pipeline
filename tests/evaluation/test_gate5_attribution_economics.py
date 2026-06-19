"""Gate 5 soundness coverage for attribution determinism and economics.

Auth note: this suite uses fake MLflow clients only; no live MLflow requests are made.
Production auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import fakeredis

from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.attribution.retraining_attributor import (
    Cohort,
    RetrainingConfig,
    attribute,
)
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.evaluation.reward_cap import BudgetConfig, compute_reward
from src.events.publishers.mint_request_publisher import QUEUE_NAME, MintRequestPublisher

SEED = 42
CREATED_AT = "2026-06-05T00:00:00Z"
HASH_D = "sha256:" + "d" * 64
HASH_M = "sha256:" + "m" * 64
_CONTRIBUTORS_TAG = json.dumps(
    [{"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}]
)


def _wallet(i: int) -> str:
    return f"0x{i:040x}"


def _cohort(cid: str, *, wallet: str, row_count: int = 1) -> Cohort:
    return Cohort(
        cohort_id=cid,
        wallet=wallet,
        submission_ids=(f"sub-{cid}",),
        row_count=row_count,
    )


def _run_attr(cohorts, eval_fn, config=None):
    return attribute(
        cohorts=cohorts,
        train_fn=lambda ids, seed: {"ids": frozenset(ids), "seed": seed},
        eval_fn=eval_fn,
        model_id="30",
        baseline_run_id="base",
        candidate_run_id="cand",
        created_at=CREATED_AT,
        dataset_hash=HASH_D,
        manifest_hash=HASH_M,
        total_rows_evaluated=100,
        config=config or RetrainingConfig(rng_seed=SEED),
    )


def _weight_by_wallet(report: dict[str, object]) -> dict[str, int]:
    contributors = report["contributors"]
    assert isinstance(contributors, list)
    return {item["wallet"]: item["weight_bps"] for item in contributors}


class _FakeRewardNotifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def notify_reward_entitlement(
        self, *, mint_request, status, mint_result=None, recipient_kinds=None, reward_tokens=None
    ):
        self.calls.append(
            {"mint_request": mint_request, "status": status, "mint_result": mint_result}
        )
        return True, None


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


def _accepted_decision(delta_pp: float = 1.5) -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=True,
        reason="accepted",
        run_id="run-candidate",
        baseline_run_id="run-baseline",
        model_id="model-a",
        dataset_hash="sha256:" + "a" * 64,
        metric_name="accuracy",
        delta_percentage_points=delta_pp,
        ci95_low_percentage_points=0.9,
        ci95_high_percentage_points=2.1,
        n_current=1000,
        n_baseline=1000,
        evaluated_at=datetime.now(timezone.utc),
    )


def _default_tags() -> dict[str, str]:
    return {
        "hokusai.eval_id": "eval-123",
        "hokusai.benchmark_spec_id": "spec-123",
        "hokusai.model_id_uint": "123",
        "hokusai.contributors": _CONTRIBUTORS_TAG,
    }


def _make_orchestrator(budget_config: BudgetConfig, monkeypatch, *, delta_pp: float = 1.5):
    decision = _accepted_decision(delta_pp=delta_pp)
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0
    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-1",
        timestamp=datetime.now(timezone.utc),
    )
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    dispatch_mock = Mock(return_value=[])
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        dispatch_mock,
    )
    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
        reward_entitlement_notifier=_FakeRewardNotifier(),
        budget_config=budget_config,
    )
    return orchestrator, mint_hook, redis_client, client, dispatch_mock


class TestDeterminism:
    def test_identical_inputs_produce_identical_weights(self) -> None:
        cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]

        def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
            included_ids = handle["ids"]
            assert isinstance(included_ids, frozenset)
            return (
                (0.0 if not included_ids else 0.1)
                + (0.3 if "A" in included_ids else 0.0)
                + (0.1 if "B" in included_ids else 0.0)
            )

        config = RetrainingConfig(rng_seed=SEED, budget=16, enable_add_one_in=True)
        first = _run_attr(cohorts, eval_fn=eval_fn, config=config)
        second = _run_attr(cohorts, eval_fn=eval_fn, config=config)

        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_global_rng_reseed_does_not_affect_result(self) -> None:
        cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]

        def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
            included_ids = handle["ids"]
            assert isinstance(included_ids, frozenset)
            return (
                (0.0 if not included_ids else 0.05)
                + (0.25 if "A" in included_ids else 0.0)
                + (0.1 if "B" in included_ids else 0.0)
            )

        config = RetrainingConfig(rng_seed=SEED, budget=16, enable_add_one_in=True)
        random.seed(7)
        first = _run_attr(cohorts, eval_fn=eval_fn, config=config)
        random.seed(99999)
        second = _run_attr(list(reversed(cohorts)), eval_fn=eval_fn, config=config)

        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_single_cohort_determinism(self) -> None:
        cohort = [_cohort("A", wallet=_wallet(1))]

        def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
            included_ids = handle["ids"]
            assert isinstance(included_ids, frozenset)
            return 0.9 if "A" in included_ids else 0.0

        first = _run_attr(cohort, eval_fn=eval_fn)
        second = _run_attr(cohort, eval_fn=eval_fn)

        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


class TestSoundness:
    def test_no_effect_cohort_gets_zero_weight(self) -> None:
        cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]

        def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
            included_ids = handle["ids"]
            assert isinstance(included_ids, frozenset)
            return 0.8 if "A" in included_ids else 0.0

        report = _run_attr(cohorts, eval_fn=eval_fn)
        weights = _weight_by_wallet(report)

        assert weights[_wallet(1)] == 10000
        assert weights[_wallet(2)] == 0

    def test_strongly_helpful_cohort_dominates(self) -> None:
        cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]

        def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
            included_ids = handle["ids"]
            assert isinstance(included_ids, frozenset)
            return (0.8 if "A" in included_ids else 0.0) + (0.1 if "B" in included_ids else 0.0)

        report = _run_attr(cohorts, eval_fn=eval_fn)
        weights = _weight_by_wallet(report)

        assert weights[_wallet(1)] > weights[_wallet(2)]
        assert weights[_wallet(1)] >= 8000

    def test_two_equally_helpful_cohorts_split_evenly(self) -> None:
        cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]

        def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
            included_ids = handle["ids"]
            assert isinstance(included_ids, frozenset)
            return (0.5 if "A" in included_ids else 0.0) + (0.5 if "B" in included_ids else 0.0)

        report = _run_attr(cohorts, eval_fn=eval_fn)
        weights = _weight_by_wallet(report)

        assert weights[_wallet(1)] == 5000
        assert weights[_wallet(2)] == 5000

    def test_negative_effect_cohort_clamped_to_zero(self) -> None:
        cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]

        def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
            included_ids = handle["ids"]
            assert isinstance(included_ids, frozenset)
            return (1.0 if "A" in included_ids else 0.0) + (-0.4 if "B" in included_ids else 0.0)

        report = _run_attr(cohorts, eval_fn=eval_fn)
        weights = _weight_by_wallet(report)

        assert weights[_wallet(1)] == 10000
        assert weights[_wallet(2)] == 0


class TestEconomicGuardrail:
    def test_normal_reward_not_capped(self) -> None:
        result = compute_reward(2.0, tokens_per_delta_one=100.0, max_reward_per_eval=500.0)
        assert result.reward_tokens == 200.0
        assert result.capped is False

    def test_above_cap_is_clamped_with_flag(self) -> None:
        result = compute_reward(10.0, tokens_per_delta_one=100.0, max_reward_per_eval=500.0)
        assert result.reward_tokens == 500.0
        assert result.capped is True

    def test_boundary_exactly_at_cap_is_not_clamped(self) -> None:
        result = compute_reward(5.0, tokens_per_delta_one=100.0, max_reward_per_eval=500.0)
        assert result.reward_tokens == 500.0
        assert result.capped is False

    def test_zero_delta_one_yields_zero_tokens(self) -> None:
        result = compute_reward(0.0, tokens_per_delta_one=100.0, max_reward_per_eval=500.0)
        assert result.reward_tokens == 0.0
        assert result.capped is False

    def test_negative_delta_one_floors_to_zero(self) -> None:
        result = compute_reward(-2.0, tokens_per_delta_one=100.0, max_reward_per_eval=500.0)
        assert result.reward_tokens == 0.0
        assert result.capped is False

    def test_no_cap_configured_returns_linear(self) -> None:
        result = compute_reward(1.25, tokens_per_delta_one=80.0)
        assert result.reward_tokens == 100.0
        assert result.capped is False

    def test_no_tokens_per_delta_one_returns_delta_unchanged(self) -> None:
        result = compute_reward(1.25, max_reward_per_eval=50.0)
        assert result.reward_tokens == 1.25
        assert result.capped is False


class TestKillSwitch:
    def test_paused_returns_paused_status_no_mint(self, monkeypatch) -> None:
        orchestrator, mint_hook, redis_client, client, dispatch_mock = _make_orchestrator(
            BudgetConfig(mint_paused=True),
            monkeypatch,
        )

        outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

        assert outcome.status == "paused"
        assert outcome.reward_tokens is None
        assert outcome.reward_capped is False
        assert redis_client.llen(QUEUE_NAME) == 0
        assert "hokusai.mint.status" not in client.tags
        mint_hook.mint.assert_not_called()
        dispatch_mock.assert_not_called()

    def test_unpaused_proceeds_normally(self, monkeypatch) -> None:
        orchestrator, mint_hook, redis_client, client, dispatch_mock = _make_orchestrator(
            BudgetConfig(tokens_per_delta_one=100.0, max_reward_per_eval=120.0),
            monkeypatch,
            delta_pp=1.5,
        )

        outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

        assert outcome.status == "success"
        assert outcome.reward_tokens == 120.0
        assert outcome.reward_capped is True
        assert redis_client.llen(QUEUE_NAME) == 1
        assert client.tags["hokusai.mint.status"] == "published"
        mint_hook.mint.assert_called_once()
        assert dispatch_mock.call_count == 2

    def test_fail_closed_on_malformed_config(self, tmp_path: Path) -> None:
        bad_config = tmp_path / "budget.yaml"
        bad_config.write_text("mint_paused: nope\n", encoding="utf-8")

        config = BudgetConfig.from_yaml_safe(bad_config)

        assert config.mint_paused is True

    def test_fail_closed_on_negative_budget_field(self, tmp_path: Path) -> None:
        bad_config = tmp_path / "budget.yaml"
        bad_config.write_text("tokensPerDeltaOne: -10\n", encoding="utf-8")

        config = BudgetConfig.from_yaml_safe(bad_config)

        assert config.mint_paused is True
