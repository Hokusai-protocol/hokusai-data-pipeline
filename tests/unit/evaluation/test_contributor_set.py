from __future__ import annotations

from copy import deepcopy

import pytest

from src.evaluation.attribution.contributor_set import (
    ContributorDerivationError,
    derive_contributor_set,
)


def _wallet(seed: str) -> str:
    return f"0x{seed * 40}"[:42]


def _report(contributors: list[dict], **overrides) -> dict:
    report = {
        "schema_version": "attribution_report/v1",
        "model_id": "model-a",
        "baseline_run_id": "run-base",
        "candidate_run_id": "run-cand",
        "contributors": contributors,
        "weight_bps_total": sum(int(item.get("weight_bps", 0)) for item in contributors),
    }
    report.update(overrides)
    return report


def test_happy_path_multiple_contributors() -> None:
    result = derive_contributor_set(
        _report(
            [
                {"wallet": _wallet("1"), "raw_score": 3.0, "submission_ids": ["sub-a"]},
                {"wallet": _wallet("2"), "raw_score": 1.0, "submission_ids": ["sub-b"]},
            ]
        )
    )

    assert result == [
        {"wallet": _wallet("1"), "weight_bps": 7500, "submission_ids": ["sub-a"]},
        {"wallet": _wallet("2"), "weight_bps": 2500, "submission_ids": ["sub-b"]},
    ]


def test_happy_path_single_contributor_gets_full_weight() -> None:
    result = derive_contributor_set(
        _report([{"wallet": _wallet("1"), "raw_score": 2.5, "submission_ids": ["sub-a"]}])
    )

    assert result == [{"wallet": _wallet("1"), "weight_bps": 10000, "submission_ids": ["sub-a"]}]


def test_largest_remainder_is_deterministic() -> None:
    result = derive_contributor_set(
        _report(
            [
                {"wallet": _wallet("1"), "raw_score": 1.0, "submission_ids": []},
                {"wallet": _wallet("2"), "raw_score": 1.0, "submission_ids": []},
                {"wallet": _wallet("3"), "raw_score": 1.0, "submission_ids": []},
            ]
        )
    )

    assert [item["weight_bps"] for item in result] == [3334, 3333, 3333]


def test_zero_lift_contributors_are_excluded_and_renormalized() -> None:
    result = derive_contributor_set(
        _report(
            [
                {"wallet": _wallet("1"), "raw_score": 3.0, "submission_ids": ["sub-a"]},
                {"wallet": _wallet("2"), "raw_score": 0.0, "submission_ids": ["sub-b"]},
                {"wallet": _wallet("3"), "raw_score": 2.0, "submission_ids": ["sub-c"]},
            ]
        )
    )

    assert result == [
        {"wallet": _wallet("1"), "weight_bps": 6000, "submission_ids": ["sub-a"]},
        {"wallet": _wallet("3"), "weight_bps": 4000, "submission_ids": ["sub-c"]},
    ]


def test_negative_lift_contributors_are_excluded() -> None:
    result = derive_contributor_set(
        _report(
            [
                {"wallet": _wallet("1"), "raw_score": 3.0, "submission_ids": ["sub-a"]},
                {"wallet": _wallet("2"), "raw_score": -1.0, "submission_ids": ["sub-b"]},
                {"wallet": _wallet("3"), "raw_score": 1.0, "submission_ids": ["sub-c"]},
            ]
        )
    )

    assert result == [
        {"wallet": _wallet("1"), "weight_bps": 7500, "submission_ids": ["sub-a"]},
        {"wallet": _wallet("3"), "weight_bps": 2500, "submission_ids": ["sub-c"]},
    ]


def test_all_zero_or_negative_raises() -> None:
    with pytest.raises(ContributorDerivationError, match="no positive-lift contributors"):
        derive_contributor_set(
            _report(
                [
                    {"wallet": _wallet("1"), "raw_score": 0.0, "submission_ids": []},
                    {"wallet": _wallet("2"), "raw_score": -1.0, "submission_ids": []},
                ]
            )
        )


@pytest.mark.parametrize(
    "wallet",
    ["0x1234", "not-hex", "742d35cc6634c0532925a3b844bc9e7595f62341"],
)
def test_invalid_wallet_raises(wallet: str) -> None:
    with pytest.raises(ContributorDerivationError, match="invalid contributor wallet"):
        derive_contributor_set(
            _report([{"wallet": wallet, "raw_score": 1.0, "submission_ids": ["sub-a"]}])
        )


def test_schema_version_mismatch_raises() -> None:
    with pytest.raises(ContributorDerivationError, match="schema_version"):
        derive_contributor_set(
            _report(
                [{"wallet": _wallet("1"), "raw_score": 1.0, "submission_ids": []}],
                schema_version="attribution_report/v2",
            )
        )


def test_candidate_run_id_guard_match_is_accepted() -> None:
    result = derive_contributor_set(
        _report([{"wallet": _wallet("1"), "raw_score": 1.0, "submission_ids": []}]),
        candidate_run_id="run-cand",
    )
    assert result[0]["weight_bps"] == 10000


def test_candidate_run_id_guard_mismatch_raises() -> None:
    with pytest.raises(ContributorDerivationError, match="candidate_run_id mismatch"):
        derive_contributor_set(
            _report([{"wallet": _wallet("1"), "raw_score": 1.0, "submission_ids": []}]),
            candidate_run_id="other-run",
        )


def test_derivation_is_deterministic_for_equivalent_reports() -> None:
    report = _report(
        [
            {"wallet": _wallet("2"), "raw_score": 1.0, "submission_ids": ["sub-b"]},
            {"wallet": _wallet("1"), "raw_score": 3.0, "submission_ids": ["sub-a"]},
        ]
    )
    shuffled = deepcopy(report)
    shuffled["contributors"] = list(reversed(shuffled["contributors"]))

    assert derive_contributor_set(report) == derive_contributor_set(shuffled)


def test_equal_scores_tie_break_by_wallet() -> None:
    result = derive_contributor_set(
        _report(
            [
                {"wallet": _wallet("b"), "raw_score": 1.0, "submission_ids": []},
                {"wallet": _wallet("a"), "raw_score": 1.0, "submission_ids": []},
            ]
        )
    )

    assert [item["wallet"] for item in result] == [_wallet("a"), _wallet("b")]
    assert [item["weight_bps"] for item in result] == [5000, 5000]
