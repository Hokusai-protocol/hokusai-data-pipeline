"""HOK-3024: baseline metrics and arms."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.arbiter import baselines as bl


def test_top_capture_counts_positives_in_top_decile():
    y = np.array([1] + [0] * 9 + [1] * 0 + [0] * 10)
    score = np.arange(20, 0, -1, dtype=float)  # first row scores highest
    assert bl.top_capture(y, score) == 1.0


def test_top_capture_shares_ties_at_the_cut():
    y = np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    score = np.zeros(10)  # all tied: random tie-breaking expects 10%
    assert bl.top_capture(y, score) == pytest.approx(0.1)


def test_top_capture_without_positives_is_none():
    assert bl.top_capture(np.zeros(10), np.arange(10.0)) is None


def test_brier_and_ece_on_a_calibrated_constant():
    y = np.array([1] * 10 + [0] * 90)
    p = np.full(100, 0.1)
    assert bl.brier(y, p) == pytest.approx(0.09)
    assert bl.ece(y, p) == pytest.approx(0.0)
    m = bl.metrics(y, bl.Scores("prior", p, True), prior_rate=0.1)
    assert m["brier_skill"] == pytest.approx(0.0)
    assert m["auc"] == 0.5


def test_ece_of_a_miscalibrated_model():
    y = np.array([0] * 100)
    assert bl.ece(y, np.full(100, 0.3)) == pytest.approx(0.3)


def test_rankings_report_no_probability_metrics():
    m = bl.metrics(np.array([0, 1, 0, 1]), bl.Scores("t", np.array([1.0, 2, 3, 4]), False), 0.5)
    assert "brier" not in m and m["auc"] == 0.75


def _synthetic(n: int, seed: int) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    loc = rng.lognormal(4, 1.5, n)
    frame = pd.DataFrame(
        {
            "feature.shape.loc_touched": loc,
            "feature.shape.files_touched": rng.integers(1, 30, n),
            "feature.history.file_commits_90d": [None if i % 7 == 0 else i % 40 for i in range(n)],
            "feature.author.repo_commits_prior": rng.integers(0, 500, n),
            "feature.shape.tests_changed": [bool(i % 2) for i in range(n)],
            "feature.agent.tool_family": [["none", "claude", None][i % 3] for i in range(n)],
        }
    )
    y = pd.Series((rng.random(n) < 1 / (1 + np.exp(-(np.log(loc) - 7)))).astype(int))
    return frame, y


def test_fit_and_score_returns_every_arm_with_signal():
    X_train, y_train = _synthetic(4000, 1)  # noqa: N806
    X_eval, y_eval = _synthetic(2000, 2)  # noqa: N806
    categories = {"feature.agent.tool_family": ["none", "claude", "other"]}
    scores = bl.fit_and_score(X_train, y_train, X_eval, categories)
    arms = [s.arm for s in scores]
    assert arms == [
        "prior",
        "trivial.feature.shape.loc_touched",
        "trivial.feature.shape.files_touched",
        "trivial.feature.history.file_commits_90d",
        "trivial.feature.author.repo_commits_prior",
        "trivial_lr",
        "jit_lr",
        "jit_gbm",
    ]
    by_arm = {s.arm: s for s in scores}
    assert bl.auc(y_eval, by_arm["trivial.feature.shape.loc_touched"].score) > 0.7
    assert bl.auc(y_eval, by_arm["jit_lr"].score) > 0.7
    assert all(0 <= p <= 1 for p in by_arm["jit_gbm"].score)


def test_label_quality_gate():
    def arm(auc_low: float, top_low: float) -> dict:
        return {"jit_gbm": {"ci95": {"auc": [auc_low, 0.7], "top_decile_capture": [top_low, 0.3]}}}

    lro = {"by_repo": {f"r{i}": {"jit_gbm": {"auc": 0.6 if i < 9 else 0.5}} for i in range(12)}}
    assert bl.label_quality({"pooled": arm(0.6, 0.2)}, lro)["decision"] == "go"
    assert bl.label_quality({"pooled": arm(0.5, 0.2)}, lro)["decision"] == "no_go"
    weak = {"by_repo": {f"r{i}": {"jit_gbm": {"auc": 0.6 if i < 8 else 0.5}} for i in range(12)}}
    assert bl.label_quality({"pooled": arm(0.6, 0.2)}, weak)["decision"] == "no_go"
