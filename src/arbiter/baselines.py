# ruff: noqa: ANN101 - self needs no annotation
"""Trivial and classical JIT defect-prediction baselines for Rework Risk (HOK-3024).

Arms 1-2 of the baseline ladder, trained and evaluated only through
``src.arbiter.rework_dataset`` splits:

* ``prior``: the training base rate for every PR (the Brier reference)
* ``trivial.<feature>``: one trivial input alone as a ranking, with its
  direction fixed in advance (bigger and busier is riskier, a more experienced
  author is safer)
* ``trivial_lr``: logistic regression on the four trivial inputs
* ``jit_lr``: logistic regression on every arm input
* ``jit_gbm``: gradient boosting on every arm input

Hyperparameters are fixed here and never tuned on evaluation rows.

Metrics: share of eventual rework in the top-risk decile, AUC, Brier score (and
skill over ``prior``) and expected calibration error over equal-mass bins.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

# Direction fixed before any evaluation: +1 means a higher value is riskier.
TRIVIAL_FEATURES: Mapping[str, int] = {
    "feature.shape.loc_touched": 1,
    "feature.shape.files_touched": 1,
    "feature.history.file_commits_90d": 1,
    "feature.author.repo_commits_prior": -1,
}
LR_PARAMS = {"C": 1.0, "max_iter": 2000}
GBM_PARAMS = {
    "max_iter": 300,
    "learning_rate": 0.05,
    "early_stopping": True,
    "validation_fraction": 0.1,
    "random_state": 0,
}
TOP_FRACTION = 0.10
ECE_BINS = 10
SEED = 20261111


# --------------------------------------------------------------------------- metrics


def top_capture(y: np.ndarray, score: np.ndarray, fraction: float = TOP_FRACTION) -> float | None:
    """Share of all positives that fall in the top ``fraction`` of scores.

    Ties at the cut are shared in proportion, so an integer feature gets the
    capture it would get on average under random tie-breaking.
    """
    y = np.asarray(y, dtype=float)
    score = np.asarray(score, dtype=float)
    positives = y.sum()
    if positives == 0 or len(y) == 0:
        return None
    k = fraction * len(y)
    cut = np.sort(score)[::-1][max(int(math.ceil(k)) - 1, 0)]
    above = score > cut
    tied = score == cut
    room = k - above.sum()
    share_tied = min(max(room / tied.sum(), 0.0), 1.0) if tied.any() else 0.0
    return float((y[above].sum() + share_tied * y[tied].sum()) / positives)


def auc(y: np.ndarray, score: np.ndarray) -> float | None:
    """ROC AUC, or None when only one class is present."""
    if len(set(np.asarray(y).tolist())) < 2:
        return None
    return float(roc_auc_score(y, score))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    """Mean squared error of predicted probabilities."""
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def ece(y: np.ndarray, p: np.ndarray, bins: int = ECE_BINS) -> float:
    """Return the expected calibration error over equal-mass bins of predicted probability.

    Bin edges are quantiles of ``p``, so equal predictions always share a bin and
    row order never decides which bin a tied row lands in.
    """
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    edges = np.quantile(p, np.linspace(0, 1, bins + 1)[1:-1])
    which = np.searchsorted(edges, p, side="right")
    total = 0.0
    for b in np.unique(which):
        m = which == b
        total += m.sum() * abs(p[m].mean() - y[m].mean())
    return float(total / len(y))


@dataclass(frozen=True)
class Scores:
    """One arm's scores on one evaluation set. ``probability`` is False for rankings."""

    arm: str
    score: np.ndarray
    probability: bool


def metrics(y: np.ndarray, scores: Scores, prior_rate: float) -> dict[str, float | None]:
    """Every metric the arm supports. Rankings get AUC and top-decile capture only."""
    out: dict[str, float | None] = {
        "rows": int(len(y)),
        "positives": int(np.sum(y)),
        "auc": auc(y, scores.score),
        "top_decile_capture": top_capture(y, scores.score),
    }
    if scores.probability:
        b = brier(y, scores.score)
        reference = brier(y, np.full(len(y), prior_rate))
        out.update(
            brier=b,
            brier_skill=None if reference == 0 else 1 - b / reference,
            ece=ece(y, scores.score),
            mean_predicted=float(np.mean(scores.score)),
            observed_rate=float(np.mean(y)),
        )
    return out


def bootstrap(
    y: np.ndarray,
    scores: Scores,
    prior_rate: float,
    *,
    resamples: int,
    seed: int = SEED,
) -> dict[str, list[float]]:
    """95% percentile intervals for AUC, top-decile capture and (probabilities) Brier skill."""
    rng = np.random.default_rng(seed)
    keys = ["auc", "top_decile_capture"] + (["brier_skill", "ece"] if scores.probability else [])
    draws: dict[str, list[float]] = {k: [] for k in keys}
    n = len(y)
    for _ in range(resamples):
        idx = rng.integers(0, n, n)
        m = metrics(y[idx], Scores(scores.arm, scores.score[idx], scores.probability), prior_rate)
        for k in keys:
            if m[k] is not None:
                draws[k].append(m[k])
    return {
        k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
        for k, v in draws.items()
        if v
    }


# --------------------------------------------------------------------------- features


def _numeric(frame: pd.DataFrame, categories: Mapping[str, Sequence[str]]) -> pd.DataFrame:
    """Floats with NaN for nulls; categories one-hot over their closed list."""
    out = {}
    for column in frame.columns:
        values = frame[column]
        if column in categories:
            for c in categories[column]:
                out[f"{column}={c}"] = np.where(values.isna(), np.nan, (values == c).astype(float))
        else:
            out[column] = pd.to_numeric(values.map(lambda v: np.nan if v is None else float(v)))
    return pd.DataFrame(out, index=frame.index)


def _signed_log(x: pd.DataFrame) -> pd.DataFrame:
    return np.sign(x) * np.log1p(np.abs(x))


class LinearPrep:
    """Signed log, median imputation with missing indicators, standardization. Fit on train."""

    def fit(self, X: pd.DataFrame) -> LinearPrep:  # noqa: N803
        logged = _signed_log(X)
        self.columns = list(X.columns)
        self.missing = [c for c in self.columns if X[c].isna().any()]
        self.median = logged.median()
        filled = logged.fillna(self.median).fillna(0.0)
        self.mean = filled.mean()
        self.std = filled.std(ddof=0).replace(0, 1.0)
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:  # noqa: N803
        logged = _signed_log(X[self.columns])
        filled = (logged.fillna(self.median).fillna(0.0) - self.mean) / self.std
        flags = X[self.missing].isna().astype(float).to_numpy()
        return np.hstack([filled.to_numpy(), flags])


def fit_and_score(
    X_train: pd.DataFrame,  # noqa: N803
    y_train: pd.Series,
    X_eval: pd.DataFrame,  # noqa: N803
    categories: Mapping[str, Sequence[str]],
    *,
    weights: pd.Series | None = None,
) -> list[Scores]:
    """Fit every arm on the training rows and score the evaluation rows."""
    y = y_train.to_numpy()
    w = None if weights is None else weights.to_numpy()
    train = _numeric(X_train, categories)
    evaluation = _numeric(X_eval, categories)
    prior_rate = float(np.average(y, weights=w))
    out = [Scores("prior", np.full(len(X_eval), prior_rate), True)]

    for column, direction in TRIVIAL_FEATURES.items():
        median = train[column].median()
        out.append(
            Scores(
                f"trivial.{column}", direction * evaluation[column].fillna(median).to_numpy(), False
            )
        )

    def lr(columns: list[str]) -> np.ndarray:
        prep = LinearPrep().fit(train[columns])
        model = LogisticRegression(**LR_PARAMS).fit(
            prep.transform(train[columns]), y, sample_weight=w
        )
        return model.predict_proba(prep.transform(evaluation[columns]))[:, 1]

    out.append(Scores("trivial_lr", lr(list(TRIVIAL_FEATURES)), True))
    out.append(Scores("jit_lr", lr(list(train.columns)), True))
    gbm = HistGradientBoostingClassifier(**GBM_PARAMS).fit(train.to_numpy(), y, sample_weight=w)
    out.append(Scores("jit_gbm", gbm.predict_proba(evaluation.to_numpy())[:, 1], True))
    return out


# --------------------------------------------------------------------------- label-quality gate

# Written before any baseline ran (HOK-3024). The label passes if the pre-declared
# check arm discriminates on the time split and across most held-out repos.
LABEL_CHECK_ARM = "jit_gbm"
GATE = {
    "time_auc_ci_low_min": 0.55,
    "time_top_decile_ci_low_min": 0.15,
    "lro_repo_auc_min": 0.55,
    "lro_repo_share_min": 0.75,
}


def label_quality(time_result: Mapping, lro_result: Mapping) -> dict[str, object]:
    """Apply the pre-declared go/no-go rule to the check arm's results."""
    pooled = time_result["pooled"][LABEL_CHECK_ARM]
    ci = pooled["ci95"]
    repo_aucs = [
        fold[LABEL_CHECK_ARM]["auc"]
        for fold in lro_result["by_repo"].values()
        if fold[LABEL_CHECK_ARM]["auc"] is not None
    ]
    share = sum(a >= GATE["lro_repo_auc_min"] for a in repo_aucs) / len(repo_aucs)
    checks = {
        "time_auc_ci_low": [ci["auc"][0], ci["auc"][0] >= GATE["time_auc_ci_low_min"]],
        "time_top_decile_ci_low": [
            ci["top_decile_capture"][0],
            ci["top_decile_capture"][0] >= GATE["time_top_decile_ci_low_min"],
        ],
        "lro_repo_share_auc_ge_min": [share, share >= GATE["lro_repo_share_min"]],
    }
    return {
        "arm": LABEL_CHECK_ARM,
        "rule": GATE,
        "checks": checks,
        "decision": "go" if all(ok for _, ok in checks.values()) else "no_go",
    }
