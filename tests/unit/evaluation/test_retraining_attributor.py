from __future__ import annotations

import json
from pathlib import Path
from random import Random

import jsonschema
import pytest

from src.evaluation.attribution.retraining_attributor import (
    Cohort,
    RetrainingConfig,
    attribute,
)


def _wallet(index: int) -> str:
    return f"0x{index:040x}"


def _cohort(
    cohort_id: str,
    *,
    wallet: str | None,
    submission_ids: tuple[str, ...] | None = None,
    row_count: int = 1,
) -> Cohort:
    return Cohort(
        cohort_id=cohort_id,
        wallet=wallet,
        submission_ids=submission_ids or (f"sub-{cohort_id}",),
        row_count=row_count,
    )


def _schema() -> dict[str, object]:
    return json.loads(Path("schema/attribution_report.v1.json").read_text(encoding="utf-8"))


def _run_attribute(
    cohorts: list[Cohort],
    *,
    eval_fn,
    config: RetrainingConfig,
    dataset_hash: str = "sha256:" + "1" * 64,
    manifest_hash: str = "sha256:" + "2" * 64,
) -> dict[str, object]:
    return attribute(
        cohorts=cohorts,
        train_fn=lambda included_ids, seed: {"included_ids": frozenset(included_ids), "seed": seed},
        eval_fn=eval_fn,
        model_id="30",
        baseline_run_id="baseline-run",
        candidate_run_id="candidate-run",
        created_at="2026-06-05T00:00:00Z",
        dataset_hash=dataset_hash,
        manifest_hash=manifest_hash,
        total_rows_evaluated=256,
        config=config,
    )


def test_loco_additive_lift_and_bps_normalization() -> None:
    cohorts = [
        _cohort("A", wallet=_wallet(1)),
        _cohort("B", wallet=_wallet(2)),
        _cohort("C", wallet=_wallet(3)),
    ]

    def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
        included_ids = handle["included_ids"]
        return (
            0.5
            + (0.1 if "A" in included_ids else 0.0)
            + (0.2 if "B" in included_ids else 0.0)
            + (0.05 if "C" in included_ids else 0.0)
            + eval_seed * 0.0
        )

    report = _run_attribute(cohorts, eval_fn=eval_fn, config=RetrainingConfig())

    contributors = {item["wallet"]: item for item in report["contributors"]}
    assert report["method_details"]["tier"] == "loco"
    assert report["method_details"]["efficiency_gap"] == pytest.approx(0.0)
    assert contributors[_wallet(1)]["weight_bps"] == 2857
    assert contributors[_wallet(2)]["weight_bps"] == 5714
    assert contributors[_wallet(3)]["weight_bps"] == 1429
    assert report["weight_bps_total"] == 10000


def test_negative_lift_is_clamped_to_zero_bps() -> None:
    cohorts = [
        _cohort("A", wallet=_wallet(1)),
        _cohort("B", wallet=_wallet(2)),
        _cohort("C", wallet=_wallet(3)),
    ]

    def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
        included_ids = handle["included_ids"]
        return (
            0.5
            + (0.1 if "A" in included_ids else 0.0)
            + (-0.05 if "B" in included_ids else 0.0)
            + (0.15 if "C" in included_ids else 0.0)
            + eval_seed * 0.0
        )

    report = _run_attribute(cohorts, eval_fn=eval_fn, config=RetrainingConfig())
    contributors = {item["wallet"]: item["weight_bps"] for item in report["contributors"]}

    assert contributors[_wallet(2)] == 0
    assert contributors[_wallet(1)] == 4000
    assert contributors[_wallet(3)] == 6000
    assert report["weight_bps_total"] == 10000


def test_all_zero_lifts_equal_weight_fallback() -> None:
    cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]
    report = _run_attribute(
        cohorts,
        eval_fn=lambda handle, eval_seed: 1.0 + eval_seed * 0.0,
        config=RetrainingConfig(),
    )

    assert report["method_details"]["fallback"] == "equal_weight"
    assert [item["weight_bps"] for item in report["contributors"]] == [5000, 5000]


def test_interaction_triggers_exact_shapley() -> None:
    cohorts = [
        _cohort("A", wallet=_wallet(1)),
        _cohort("B", wallet=_wallet(2)),
        _cohort("C", wallet=_wallet(3)),
    ]

    def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
        included_ids = handle["included_ids"]
        return 0.4 if {"A", "B"}.issubset(included_ids) else 0.0

    report = _run_attribute(
        cohorts,
        eval_fn=eval_fn,
        config=RetrainingConfig(tau=0.10, budget=16),
    )

    assert report["method_details"]["tier"] == "shapley_exact"
    assert report["method_details"]["retrain_count"] == 8
    contributors = {item["wallet"]: item["raw_score"] for item in report["contributors"]}
    assert contributors[_wallet(1)] == pytest.approx(0.2)
    assert contributors[_wallet(2)] == pytest.approx(0.2)
    assert contributors[_wallet(3)] == pytest.approx(0.0)


def test_interaction_with_add_one_in_stays_in_loco() -> None:
    cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]

    def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
        included_ids = handle["included_ids"]
        return 0.4 if included_ids == frozenset({"A", "B"}) else 0.0

    report = _run_attribute(
        cohorts,
        eval_fn=eval_fn,
        config=RetrainingConfig(enable_add_one_in=True, budget=8),
    )

    assert report["method_details"]["tier"] == "loco+addone"
    assert report["method_details"]["efficiency_gap"] == pytest.approx(0.0)


def test_grouping_to_max_groups_when_too_many_cohorts() -> None:
    cohorts = [
        _cohort(f"C{index:02d}", wallet=_wallet(index + 1), row_count=index + 1)
        for index in range(20)
    ]

    def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
        return float(len(handle["included_ids"]))

    report = _run_attribute(
        cohorts,
        eval_fn=eval_fn,
        config=RetrainingConfig(max_groups=12, budget=32),
    )

    assert len(report["method_details"]["sample_plan"]["groups"]) == 12
    assert len(report["contributors"]) == 20
    assert report["weight_bps_total"] == 10000
    assert len(report["method_details"]["sample_plan"]["groups"][0]["member_cohort_ids"]) == 9


def test_budget_too_small_for_loco_raises() -> None:
    cohorts = [_cohort(f"C{index}", wallet=_wallet(index + 1)) for index in range(5)]
    with pytest.raises(ValueError, match="retrain budget too small for LOCO"):
        _run_attribute(
            cohorts,
            eval_fn=lambda handle, eval_seed: float(len(handle["included_ids"])),
            config=RetrainingConfig(budget=3),
        )


def test_budget_forces_tmc_when_exact_would_exceed() -> None:
    cohorts = [_cohort(f"C{index}", wallet=_wallet(index + 1)) for index in range(10)]

    def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
        return 1.0 if len(handle["included_ids"]) >= 5 else 0.0

    report = _run_attribute(
        cohorts,
        eval_fn=eval_fn,
        config=RetrainingConfig(tau=0.10, budget=50, eval_seeds=(0, 1, 2)),
    )

    assert report["method_details"]["tier"] == "shapley_tmc"
    assert report["method_details"]["retrain_count"] <= 50
    assert report["method_details"]["sample_plan"]["method"] == "tmc"
    assert report["method_details"]["sample_plan"]["permutations"]
    assert "truncation_eps" in report["method_details"]["sample_plan"]


def test_noise_floor_flag_when_eval_is_noisy() -> None:
    cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]
    noise = {0: -0.3, 1: 0.4, 2: 0.1}

    def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
        included_ids = handle["included_ids"]
        base = 0.8 if included_ids == frozenset({"A", "B"}) else 0.0
        return base + noise[eval_seed]

    report = _run_attribute(
        cohorts,
        eval_fn=eval_fn,
        config=RetrainingConfig(eval_seeds=(0, 1, 2)),
    )

    assert report["method_details"]["noise_floor_ok"] is False
    assert report["method_details"]["tier"] == "loco"


def test_determinism_byte_identical_reports() -> None:
    cohorts = [_cohort("A", wallet=_wallet(1)), _cohort("B", wallet=_wallet(2))]

    def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
        included_ids = sorted(handle["included_ids"])
        return float(sum(ord(name[0]) for name in included_ids)) / 1000.0

    config = RetrainingConfig(enable_add_one_in=True, budget=16)
    first = _run_attribute(cohorts, eval_fn=eval_fn, config=config)
    second = _run_attribute(list(reversed(cohorts)), eval_fn=eval_fn, config=config)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_report_schema_validates_against_attribution_report_v1() -> None:
    report = _run_attribute(
        [_cohort("A", wallet=_wallet(1))],
        eval_fn=lambda handle, eval_seed: 1.0 if "A" in handle["included_ids"] else 0.0,
        config=RetrainingConfig(),
    )
    jsonschema.validate(instance=report, schema=_schema())


def test_cohort_ordering_invariance() -> None:
    cohorts = [
        _cohort("B", wallet=_wallet(2)),
        _cohort("A", wallet=_wallet(1)),
        _cohort("C", wallet=_wallet(3)),
    ]

    def eval_fn(handle: dict[str, object], eval_seed: int) -> float:
        included_ids = handle["included_ids"]
        return (
            (0.1 if "A" in included_ids else 0.0)
            + (0.2 if "B" in included_ids else 0.0)
            + (0.3 if "C" in included_ids else 0.0)
        )

    first = _run_attribute(cohorts, eval_fn=eval_fn, config=RetrainingConfig())
    second = _run_attribute(
        [cohorts[index] for index in Random(0).sample(range(len(cohorts)), len(cohorts))],
        eval_fn=eval_fn,
        config=RetrainingConfig(),
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_dataset_and_manifest_hash_recorded() -> None:
    report = _run_attribute(
        [_cohort("A", wallet=_wallet(1))],
        eval_fn=lambda handle, eval_seed: 1.0 if "A" in handle["included_ids"] else 0.0,
        config=RetrainingConfig(),
        dataset_hash="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "b" * 64,
    )

    assert report["method_details"]["dataset_hash"] == "sha256:" + "a" * 64
    assert report["method_details"]["manifest_hash"] == "sha256:" + "b" * 64
