# ruff: noqa: ANN101, C901, A003, D101, D401, E501
"""HOK-3028 gate runner: score every arm once on the evaluation slice and apply §6.

The rules come from ``hokusai-sdk/docs/arbiter/rework-risk-preregistration.md``
(gate frozen 2026-10-28, target pinned 2026-11-13, scoring clarifications
2026-11-14). Every threshold below is a copy of that document, not a choice made
here.

How the runner keeps arm builders blind:

* The runner reads the evaluation slice file itself. It checks the file's
  SHA-256 against the commitment in §4 and never prints the repos, the window
  or the salt.
* It builds the training rows (development repos, label windows closed before
  the evaluation window starts) and the evaluation rows (slice repos, inside the
  window), and gives them to frozen arm code through :class:`ArmAdapter`. So
  arm code never needs the dates or the repo names.
* :func:`score_once` refuses a second scoring of the same slice unless it is
  given a reason, which follows the §8.1 rule: every arm is re-run and the
  original record is kept.

:func:`rehearsal_slice` builds a stand-in slice from development repos, so the
whole pipeline can be exercised end to end before the real slice is unsealed.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from src.arbiter.baselines import brier, ece, top_capture
from src.arbiter.feature_audit import LeakageError, print_manifest
from src.arbiter.rework_dataset import (
    DEFAULT_PROVENANCE_WEIGHTS,
    FEATURE_MANIFEST_VERSION,
    SLICE_PROCEDURE,
    _code_version,
    _repo_dirs,
    audit_feature_columns,
    load_repo_rows,
    read_slice,
)

# --------------------------------------------------------------------------- frozen rules

GATE_SCHEMA_VERSION = "rework_risk_gate/1.0.0"
PREREGISTRATION = "hokusai-sdk:docs/arbiter/rework-risk-preregistration.md"
HOLDOUT_SHA256 = "a1a436e57183aa141cfe1b45bc7a7f50f393c648c24139dd6703ee4abdb09886"
GATE_TARGET_DEFINITION = "cr-0.2.0"
PRIMARY_HORIZON = 30
SECONDARY_HORIZONS = (14, 60)

DELTA_MIN = 0.10  # Δ ≥ 10 pp of macro top-decile capture
RATIO_MIN = 1.25  # arm 5 / arm 4 capture ≥ 1.25×
REPO_SHARE_MIN = 2 / 3  # Δ > 0 in ≥ ⅔ of evaluation repos
BRIER_MARGIN = 0.002  # CI upper bound of Brier(5) − Brier(4) ≤ 0.002
ECE_MARGIN = 0.01  # CI upper bound of ECE(5) − ECE(4) ≤ 0.01
MIN_REPOS = 5
MIN_POSITIVES = 500
RESAMPLES = 10_000
CI = (2.5, 97.5)
DEPENDENCY_BOT_COLUMN = "segment.author.dependency_bot"

REHEARSAL_VERSION = "rehearsal-only"  # arms with this version never score the sealed slice
ROLES = ("arm1", "arm2", "arm3", "arm4", "arm5", "arm6")
COMPARATOR_ROLES = ("arm1", "arm2")  # arm 5 must beat every variant of these

INCONCLUSIVE = "INCONCLUSIVE (underpowered)"
TABLE_STAKES_FAIL = "TABLE-STAKES FAIL"
LOSS = "LOSS"
COMPELLING = "COMPELLING"
HALF_WIN = "HALF-WIN"
TIE = "TIE"


# --------------------------------------------------------------------------- arms


@dataclass(frozen=True)
class ArmContext:
    """What the runner tells arm code. It never holds slice repos or dates."""

    feature_columns: tuple[str, ...]
    categories: Mapping[str, Sequence[str]]
    content_columns: tuple[str, ...] = ()
    content_root: Path | None = None
    seed: int = 0


class ArmAdapter(Protocol):
    """A frozen arm. ``fit`` sees training rows only; ``score`` sees evaluation rows.

    ``score`` returns one frame per variant, indexed like ``rows``, with a float
    ``score`` column (ranking) and an optional ``probability`` column
    (calibration). For arm 4 the probability is the recalibrated one (§3).
    """

    arm_id: str
    version: str

    def variants(self) -> Mapping[str, str]:
        """Variant id -> role (one of ``ROLES``)."""
        ...

    def fit(self, train: pd.DataFrame, context: ArmContext) -> Any: ...

    def score(
        self, fitted: Any, rows: pd.DataFrame, context: ArmContext
    ) -> Mapping[str, pd.DataFrame]: ...


@dataclass(frozen=True)
class VariantScores:
    variant: str
    role: str
    arm_id: str
    arm_version: str
    score: np.ndarray
    probability: np.ndarray | None


# --------------------------------------------------------------------------- slice and rows


@dataclass(frozen=True)
class Slice:
    """The evaluation slice. ``__repr__`` hides everything but the hash."""

    repos: frozenset[str]
    merged_from: date
    merged_until: date
    sha256: str
    rehearsal: bool = False

    def __repr__(self) -> str:
        kind = "rehearsal" if self.rehearsal else "sealed"
        return f"Slice({kind}, sha256={self.sha256[:12]}…)"


def read_sealed_slice(slice_file: str | Path, expected_sha256: str = HOLDOUT_SHA256) -> Slice:
    """Read the slice manifest, checking it against the §4 commitment. Never echoes it."""
    path = Path(slice_file).expanduser()
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != expected_sha256:
        raise LeakageError(
            "Evaluation slice file does not match the pre-registered holdout SHA-256"
        )
    manifest = json.loads(data)
    if manifest.get("procedure") != SLICE_PROCEDURE:
        raise LeakageError("Evaluation slice file has the wrong procedure")
    window = manifest["time_window"]
    return Slice(
        repos=frozenset(manifest["repos"]),
        merged_from=date.fromisoformat(window["merged_from"]),
        merged_until=date.fromisoformat(window["merged_until"]),
        sha256=sha,
    )


def rehearsal_slice(
    features_root: str | Path,
    sealed_slice_file: str | Path,
    *,
    repos: int = 6,
    window_months: int = 6,
    merged_until: date,
    salt: str = "hok-3028-rehearsal",
) -> Slice:
    """A stand-in slice drawn from development repos only, for end-to-end rehearsal.

    Repos are ordered by ``sha256(salt ‖ repo)``. The real slice's repos are
    excluded first, and the drawn names are never printed.
    """
    sealed, _ = read_slice(sealed_slice_file)
    development = sorted(r for r in _repo_dirs(Path(features_root).expanduser()) if r not in sealed)
    if len(development) <= repos:
        raise LeakageError("Too few development repos for a rehearsal slice")
    ranked = sorted(development, key=lambda r: hashlib.sha256(f"{salt}\0{r}".encode()).hexdigest())
    merged_from = (pd.Timestamp(merged_until) - pd.DateOffset(months=window_months)).date()
    digest = hashlib.sha256(
        json.dumps({"salt": salt, "repos": ranked[:repos], "until": str(merged_until)}).encode()
    ).hexdigest()
    return Slice(frozenset(ranked[:repos]), merged_from, merged_until, digest, rehearsal=True)


@dataclass
class GateData:
    """Training rows (development repos) and evaluation rows (slice repos, in window)."""

    train: pd.DataFrame
    evaluation: pd.DataFrame
    slice: Slice
    horizon_days: int
    target_definition: str
    feature_columns: tuple[str, ...]
    content_columns: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def primary(self) -> np.ndarray:
        """Evaluation rows in the primary analysis: dependency-bot PRs are segmented out."""
        bot = self.evaluation[DEPENDENCY_BOT_COLUMN]
        return ~bot.fillna(False).astype(bool).to_numpy()


def _midnight(day: date) -> pd.Timestamp:
    return pd.Timestamp(datetime(day.year, day.month, day.day, tzinfo=timezone.utc))


def build_gate_data(
    *,
    features_root: str | Path,
    labels_root: str | Path,
    sealed_slice_file: str | Path,
    evaluation_slice: Slice,
    horizon_days: int = PRIMARY_HORIZON,
    target_definition: str = GATE_TARGET_DEFINITION,
    feature_columns: Sequence[str] | None = None,
) -> GateData:
    """Build the gate's rows under the 2026-11-14 training-data rule.

    Training: development repos only, rows whose label window closes on or before
    the evaluation window starts (``as_of + horizon <= merged_from``). Evaluation:
    slice repos, merged in ``[merged_from, merged_until)``. Development repos never
    give evaluation rows and slice repos never give training rows.
    """
    features_root = Path(features_root).expanduser()
    labels_root = Path(labels_root).expanduser()
    sealed, sealed_sha = read_slice(sealed_slice_file)
    available = set(_repo_dirs(features_root))
    eval_repos = set(evaluation_slice.repos)
    if not eval_repos <= available:
        raise FileNotFoundError(f"{len(eval_repos - available)} slice repo(s) have no feature rows")
    if evaluation_slice.rehearsal and eval_repos & sealed:
        raise LeakageError("A rehearsal slice must not contain sealed repos")
    train_repos = sorted(available - sealed - eval_repos)
    if not train_repos:
        raise LeakageError("No development repos to train on")

    columns, audit = audit_feature_columns(feature_columns)
    content = tuple(e["name"] for e in print_manifest()["entries"] if e["kind"] == "content_sha256")
    load = {
        "features_root": features_root,
        "labels_root": labels_root,
        "target_definition": target_definition,
        "horizon_days": horizon_days,
        "columns": (*columns, *content, DEPENDENCY_BOT_COLUMN),
        "weights": dict(DEFAULT_PROVENANCE_WEIGHTS),
    }
    train_loaded = load_repo_rows(train_repos, **load)
    eval_loaded = load_repo_rows(sorted(eval_repos), **load)
    for loaded in (train_loaded, eval_loaded):
        if loaded.versions["definition_version"] != target_definition:
            raise LeakageError(f"Label files do not hold {target_definition}")

    start = _midnight(evaluation_slice.merged_from)
    end = _midnight(evaluation_slice.merged_until)
    horizon = pd.Timedelta(days=horizon_days)
    train = train_loaded.rows
    train = train[train["as_of"] + horizon <= start].reset_index(drop=True)
    evaluation = eval_loaded.rows
    evaluation = evaluation[(evaluation["as_of"] >= start) & (evaluation["as_of"] < end)]
    evaluation = evaluation.reset_index(drop=True)
    if train.empty or evaluation.empty:
        raise LeakageError("Gate rows are empty after the window rules")

    provenance = {
        "gate_schema_version": GATE_SCHEMA_VERSION,
        "preregistration": PREREGISTRATION,
        "code": _code_version(),
        "feature_manifest_version": FEATURE_MANIFEST_VERSION,
        "columns": {
            "features": list(columns),
            "content": list(content),
            "audit_ok": bool(audit.ok),
        },
        "target": {
            "name": "corrective_rework",
            "horizon_days": horizon_days,
            **eval_loaded.versions,
        },
        "evaluation_slice": {
            "sha256": evaluation_slice.sha256,
            "rehearsal": evaluation_slice.rehearsal,
            "sealed_sha256": sealed_sha,
        },
        "training_rule": "development repos only; as_of + horizon <= evaluation window start",
        "inputs": {
            "train": _inputs_digest(train_loaded.inputs),
            "evaluation": _inputs_digest(eval_loaded.inputs),
        },
        "counts": {
            "train_rows": int(len(train)),
            "train_positives": int(train["label"].sum()),
            "evaluation_rows": int(len(evaluation)),
            "evaluation_positives": int(evaluation["label"].sum()),
        },
    }
    return GateData(
        train=train,
        evaluation=evaluation,
        slice=evaluation_slice,
        horizon_days=horizon_days,
        target_definition=target_definition,
        feature_columns=tuple(columns),
        content_columns=content,
        provenance=provenance,
    )


def _inputs_digest(inputs: Sequence[Mapping[str, Any]]) -> str:
    """One hash over per-repo input hashes, so the record pins inputs without naming repos."""
    return hashlib.sha256(json.dumps(sorted(inputs, key=lambda i: i["repo"])).encode()).hexdigest()


def arm_frame(
    rows: pd.DataFrame, feature_columns: Sequence[str], content_columns: Sequence[str] = ()
) -> pd.DataFrame:
    """Return the columns arm code may see: identity, merge time, inputs and content hashes.

    Labels, label windows, provenance weights and segment columns are withheld
    from ``score``; ``fit`` additionally gets ``label`` and ``sample_weight``.
    """
    return rows[
        ["repo", "pr_number", "merge_sha", "as_of", *feature_columns, *content_columns]
    ].copy()


# --------------------------------------------------------------------------- scoring arms


def run_arms(
    data: GateData, arms: Sequence[ArmAdapter], context: ArmContext
) -> list[VariantScores]:
    """Fit every arm on the training rows and score every evaluation row."""
    out: list[VariantScores] = []
    train = arm_frame(data.train, data.feature_columns, data.content_columns)
    train["label"] = data.train["label"].to_numpy()
    train["sample_weight"] = data.train["sample_weight"].to_numpy()
    rows = arm_frame(data.evaluation, data.feature_columns, data.content_columns)
    seen: set[str] = set()
    for arm in arms:
        variants = dict(arm.variants())
        bad = {v: r for v, r in variants.items() if r not in ROLES}
        if bad:
            raise ValueError(f"{arm.arm_id}: unknown roles {bad}")
        fitted = arm.fit(train, context)
        scored = arm.score(fitted, rows, context)
        if set(scored) != set(variants):
            raise ValueError(f"{arm.arm_id}: scored {sorted(scored)}, declared {sorted(variants)}")
        for variant, frame in scored.items():
            if variant in seen:
                raise ValueError(f"Variant {variant} is declared twice")
            seen.add(variant)
            frame = frame.reindex(rows.index)
            score = frame["score"].to_numpy(dtype=float)
            role = variants[variant]
            if role != "arm3" and np.isnan(score).any():
                raise ValueError(f"{variant}: every evaluation row needs a score")
            probability = None
            if "probability" in frame:
                probability = frame["probability"].to_numpy(dtype=float)
                finite = probability[~np.isnan(probability)]
                if ((finite < 0) | (finite > 1)).any():
                    raise ValueError(f"{variant}: probabilities must lie in [0, 1]")
            out.append(VariantScores(variant, role, arm.arm_id, arm.version, score, probability))
    return out


# --------------------------------------------------------------------------- metrics


def _per_repo(groups: Sequence[np.ndarray], y: np.ndarray, values: np.ndarray, fn: Any) -> list:
    return [fn(y[ix], values[ix]) if y[ix].sum() > 0 else None for ix in groups]


def _macro(values: Sequence[float | None]) -> float | None:
    kept = [v for v in values if v is not None and not math.isnan(v)]
    return float(np.mean(kept)) if kept else None


def _precision_at_decile(y: np.ndarray, score: np.ndarray) -> float | None:
    capture = top_capture(y, score)
    if capture is None:
        return None
    return float(capture * y.sum() / (0.1 * len(y)))


def _ap(y: np.ndarray, score: np.ndarray) -> float | None:
    return float(average_precision_score(y, score)) if 0 < y.sum() < len(y) else None


def point_metrics(
    repo: np.ndarray, y: np.ndarray, variants: Sequence[VariantScores]
) -> dict[str, dict[str, Any]]:
    """Per-repo and macro metrics for each variant, without resampling."""
    repos = sorted(set(repo))
    groups = [np.flatnonzero(repo == r) for r in repos]
    out: dict[str, dict[str, Any]] = {}
    for v in variants:
        capture = _per_repo(groups, y, v.score, top_capture)
        result: dict[str, Any] = {
            "role": v.role,
            "arm_id": v.arm_id,
            "arm_version": v.arm_version,
            "macro": {
                "top_decile_capture": _macro(capture),
                "average_precision": _macro(_per_repo(groups, y, v.score, _ap)),
                "precision_at_decile": _macro(_per_repo(groups, y, v.score, _precision_at_decile)),
            },
            "per_repo": {"top_decile_capture": dict(zip(repos, capture))},
        }
        if v.probability is not None:
            b = _per_repo(groups, y, v.probability, brier)
            e = _per_repo(groups, y, v.probability, ece)
            result["macro"]["brier"] = _macro(b)
            result["macro"]["ece"] = _macro(e)
            result["per_repo"]["brier"] = dict(zip(repos, b))
            result["per_repo"]["ece"] = dict(zip(repos, e))
        pooled_capture = top_capture(y, v.score)
        result["pooled"] = {"top_decile_capture": pooled_capture, "rows": int(len(y))}
        out[v.variant] = result
    return out


@dataclass
class Replicates:
    """Macro metrics per bootstrap resample, shared across variants (paired)."""

    capture: dict[str, np.ndarray]
    brier: dict[str, np.ndarray]
    ece: dict[str, np.ndarray]


def paired_bootstrap(
    repo: np.ndarray,
    y: np.ndarray,
    variants: Sequence[VariantScores],
    *,
    resamples: int = RESAMPLES,
    seed: int = 0,
    calibrated: Sequence[str] = (),
) -> Replicates:
    """Two-stage cluster bootstrap: repos with replacement, then PRs within each repo.

    Every variant is scored on the same resampled rows. A drawn repo with no
    positives in a resample is left out of that resample's macro average.
    """
    rng = np.random.default_rng(seed)
    repos = sorted(set(repo))
    groups = [np.flatnonzero(repo == r) for r in repos]
    by_name = {v.variant: v for v in variants}
    capture = {v.variant: np.full(resamples, np.nan) for v in variants}
    brier_r = {name: np.full(resamples, np.nan) for name in calibrated}
    ece_r = {name: np.full(resamples, np.nan) for name in calibrated}
    for b in range(resamples):
        drawn = rng.integers(0, len(groups), len(groups))
        sums = {name: [] for name in capture}
        bsums = {name: [] for name in calibrated}
        esums = {name: [] for name in calibrated}
        for j in drawn:
            ix = groups[j]
            rows = ix[rng.integers(0, len(ix), len(ix))]
            yb = y[rows]
            if yb.sum() == 0:
                continue
            for name, v in by_name.items():
                sums[name].append(top_capture(yb, v.score[rows]))
            for name in calibrated:
                p = by_name[name].probability[rows]
                bsums[name].append(brier(yb, p))
                esums[name].append(ece(yb, p))
        for name in capture:
            capture[name][b] = np.mean(sums[name]) if sums[name] else np.nan
        for name in calibrated:
            brier_r[name][b] = np.mean(bsums[name]) if bsums[name] else np.nan
            ece_r[name][b] = np.mean(esums[name]) if esums[name] else np.nan
    return Replicates(capture, brier_r, ece_r)


def _ci(values: np.ndarray) -> list[float]:
    lo, hi = np.nanpercentile(values, CI)
    return [float(lo), float(hi)]


# --------------------------------------------------------------------------- the gate


def _one(variants: Sequence[VariantScores], role: str) -> VariantScores:
    found = [v for v in variants if v.role == role]
    if len(found) != 1:
        raise ValueError(f"The gate needs exactly one {role} variant, got {len(found)}")
    return found[0]


def evaluate_gate(
    repo: np.ndarray,
    y: np.ndarray,
    variants: Sequence[VariantScores],
    *,
    resamples: int = RESAMPLES,
    seed: int = 0,
) -> dict[str, Any]:
    """Apply §6 to primary-analysis rows. Returns the outcome and every number behind it."""
    repo = np.asarray(repo)
    y = np.asarray(y, dtype=float)
    arm4, arm5 = _one(variants, "arm4"), _one(variants, "arm5")
    for v in (arm4, arm5):
        if v.probability is None or np.isnan(v.probability).any():
            raise ValueError(f"{v.variant} needs a probability on every row for calibration")
    comparators = [v for v in variants if v.role in COMPARATOR_ROLES]
    if not {v.role for v in comparators} >= set(COMPARATOR_ROLES):
        raise ValueError("The gate needs arm 1 and arm 2 variants")
    hybrid = [v for v in variants if v.role == "arm6"]
    full = [v for v in variants if v.role != "arm3"]

    repos = sorted(set(repo))
    power = {
        "repos": len(repos),
        "positives": int(y.sum()),
        "rows": int(len(y)),
        "ok": bool(len(repos) >= MIN_REPOS and y.sum() >= MIN_POSITIVES),
    }
    points = point_metrics(repo, y, full)
    reps = paired_bootstrap(
        repo, y, full, resamples=resamples, seed=seed, calibrated=(arm4.variant, arm5.variant)
    )

    c4 = points[arm4.variant]["macro"]["top_decile_capture"]
    c5 = points[arm5.variant]["macro"]["top_decile_capture"]
    delta = c5 - c4
    delta_ci = _ci(reps.capture[arm5.variant] - reps.capture[arm4.variant])
    ratio = c5 / c4 if c4 else math.inf
    per4 = points[arm4.variant]["per_repo"]["top_decile_capture"]
    per5 = points[arm5.variant]["per_repo"]["top_decile_capture"]
    compared = [r for r in repos if per4[r] is not None and per5[r] is not None]
    wins = sum(per5[r] > per4[r] for r in compared)
    repo_share = wins / len(compared) if compared else 0.0

    beats = {}
    for v in comparators:
        diff_ci = _ci(reps.capture[arm5.variant] - reps.capture[v.variant])
        beats[v.variant] = {
            "role": v.role,
            "delta": c5 - points[v.variant]["macro"]["top_decile_capture"],
            "ci95": diff_ci,
            "beaten": diff_ci[0] > 0,
        }
    beats_all = all(b["beaten"] for b in beats.values())

    brier_ci = _ci(reps.brier[arm5.variant] - reps.brier[arm4.variant])
    ece_ci = _ci(reps.ece[arm5.variant] - reps.ece[arm4.variant])
    calibration = {
        "brier": {
            "arm4": points[arm4.variant]["macro"]["brier"],
            "arm5": points[arm5.variant]["macro"]["brier"],
            "diff_ci95": brier_ci,
            "margin": BRIER_MARGIN,
            "ok": brier_ci[1] <= BRIER_MARGIN,
        },
        "ece": {
            "arm4": points[arm4.variant]["macro"]["ece"],
            "arm5": points[arm5.variant]["macro"]["ece"],
            "diff_ci95": ece_ci,
            "margin": ECE_MARGIN,
            "ok": ece_ci[1] <= ECE_MARGIN,
        },
    }
    calibration_ok = calibration["brier"]["ok"] and calibration["ece"]["ok"]

    ranking = {
        "delta": delta,
        "delta_ci95": delta_ci,
        "delta_ok": delta >= DELTA_MIN,
        "ci_low_ok": delta_ci[0] > 0,
        "ratio": ratio,
        "ratio_ok": ratio >= RATIO_MIN,
        "repo_share": repo_share,
        "repo_share_ok": repo_share >= REPO_SHARE_MIN,
        "beats_arms_1_and_2": beats_all,
    }
    ranking_ok = all(ranking[k] for k in ("delta_ok", "ci_low_ok", "ratio_ok", "repo_share_ok"))
    ranking_ok = ranking_ok and beats_all

    if not power["ok"]:
        outcome = INCONCLUSIVE
    elif not beats_all:
        outcome = TABLE_STAKES_FAIL
    elif delta_ci[1] < 0:
        outcome = LOSS
    elif ranking_ok and calibration_ok:
        outcome = COMPELLING
    elif ranking_ok:
        outcome = HALF_WIN
    else:
        outcome = TIE

    secondary: dict[str, Any] = {}
    if hybrid:
        arm6 = _one(variants, "arm6")
        best = np.fmax(reps.capture[arm4.variant], reps.capture[arm5.variant])
        diff_ci = _ci(reps.capture[arm6.variant] - best)
        secondary["hybrid"] = {
            "arm6_minus_best_of_4_5_ci95": diff_ci,
            "supported": diff_ci[0] > 0,
        }

    return {
        "outcome": outcome,
        "power": power,
        "ranking": ranking,
        "beats": beats,
        "calibration": calibration,
        "calibration_ok": calibration_ok,
        "metrics": points,
        "secondary": secondary,
        "bootstrap": {"resamples": resamples, "seed": seed, "ci": list(CI)},
    }


def evaluate_sample_pair(
    repo: np.ndarray,
    y: np.ndarray,
    variants: Sequence[VariantScores],
    *,
    resamples: int = RESAMPLES,
    seed: int = 0,
) -> dict[str, Any] | None:
    """§7 arm 3 vs arm 5 on the rows arm 3 scored. Reported, never gating."""
    arm3 = [v for v in variants if v.role == "arm3"]
    if not arm3:
        return None
    arm3 = arm3[0]
    arm5 = _one(variants, "arm5")
    keep = ~np.isnan(arm3.score)
    if keep.sum() == 0:
        return None

    def cut(v: VariantScores) -> VariantScores:
        p = None if v.probability is None else v.probability[keep]
        return VariantScores(v.variant, v.role, v.arm_id, v.arm_version, v.score[keep], p)

    pair = [cut(arm3), cut(arm5)]
    points = point_metrics(repo[keep], y[keep], pair)
    reps = paired_bootstrap(repo[keep], y[keep], pair, resamples=resamples, seed=seed)
    return {
        "rows": int(keep.sum()),
        "positives": int(y[keep].sum()),
        "arm3": points[arm3.variant]["macro"],
        "arm5": points[arm5.variant]["macro"],
        "arm5_minus_arm3_ci95": _ci(reps.capture[arm5.variant] - reps.capture[arm3.variant]),
    }


# --------------------------------------------------------------------------- one scoring


def _record_name(slice_sha: str, attempt: int) -> str:
    return f"gate-{slice_sha[:16]}-{attempt}.json"


def score_once(
    data: GateData,
    arms: Sequence[ArmAdapter],
    context: ArmContext,
    *,
    record_dir: str | Path,
    rerun_reason: str | None = None,
    resamples: int = RESAMPLES,
    seed: int = 0,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    """Score the slice and write the private gate record. The sealed slice is scored once.

    A second run on the same slice needs ``rerun_reason`` (§8.1): it re-runs
    every arm and writes a new record beside the original, which is kept.
    Rehearsal slices may be re-run freely.
    """
    record_dir = Path(record_dir).expanduser()
    record_dir.mkdir(parents=True, exist_ok=True)
    code = data.provenance["code"]
    if code.get("dirty") and not allow_dirty and not data.slice.rehearsal:
        raise LeakageError("Commit the runner and every arm before scoring the sealed slice")
    if not data.slice.rehearsal and any(a.version == REHEARSAL_VERSION for a in arms):
        raise LeakageError("Rehearsal stand-in arms cannot score the sealed slice")
    previous = sorted(record_dir.glob(f"gate-{data.slice.sha256[:16]}-*.json"))
    if previous and not data.slice.rehearsal and not rerun_reason:
        raise LeakageError(
            "This evaluation slice has already been scored. Re-running needs a reason (§8.1), "
            "and the original record is kept"
        )

    variants = run_arms(data, arms, context)
    primary = data.primary
    repo = data.evaluation["repo"].to_numpy()
    y = data.evaluation["label"].to_numpy(dtype=float)

    def subset(mask: np.ndarray) -> list[VariantScores]:
        return [
            VariantScores(
                v.variant,
                v.role,
                v.arm_id,
                v.arm_version,
                v.score[mask],
                None if v.probability is None else v.probability[mask],
            )
            for v in variants
        ]

    primary_variants = subset(primary)
    gate = evaluate_gate(
        repo[primary], y[primary], primary_variants, resamples=resamples, seed=seed
    )
    gate["secondary"]["arm3_vs_arm5"] = evaluate_sample_pair(
        repo[primary], y[primary], primary_variants, resamples=resamples, seed=seed
    )
    bots = ~primary
    gate["secondary"]["dependency_bot_segment"] = (
        {
            "rows": int(bots.sum()),
            "positives": int(y[bots].sum()),
            "metrics": {
                k: m["macro"]
                for k, m in point_metrics(
                    repo[bots], y[bots], [v for v in subset(bots) if v.role != "arm3"]
                ).items()
            },
        }
        if bots.any()
        else None
    )
    if data.horizon_days != PRIMARY_HORIZON:
        gate["outcome_applies"] = False
        gate["note"] = f"Secondary horizon {data.horizon_days}d: reported, never gating (§7)"
    else:
        gate["outcome_applies"] = data.target_definition == GATE_TARGET_DEFINITION

    attempt = len(previous) + 1
    record = {
        **gate,
        "provenance": data.provenance,
        "arms": [
            {"arm_id": a.arm_id, "version": a.version, "variants": dict(a.variants())} for a in arms
        ],
        "score_sha256": {
            v.variant: hashlib.sha256(np.ascontiguousarray(v.score).tobytes()).hexdigest()
            for v in variants
        },
        "attempt": attempt,
        "rerun_reason": rerun_reason,
        "scored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path = record_dir / _record_name(data.slice.sha256, attempt)
    path.write_text(json.dumps(record, indent=2, sort_keys=True, default=json_default) + "\n")
    record["record_path"] = str(path)
    return record


def public_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    """The record without per-repo numbers or repo names, for git before the slice is published."""

    def strip(metrics: Mapping[str, Any]) -> dict[str, Any]:
        return {k: {kk: vv for kk, vv in m.items() if kk != "per_repo"} for k, m in metrics.items()}

    keep = ("outcome", "outcome_applies", "power", "ranking", "beats", "calibration")
    out = {k: record[k] for k in keep if k in record}
    out["calibration_ok"] = record.get("calibration_ok")
    out["metrics"] = strip(record["metrics"])
    out["secondary"] = record.get("secondary")
    out["bootstrap"] = record.get("bootstrap")
    prov = dict(record["provenance"])
    out["provenance"] = {k: prov[k] for k in prov if k != "inputs"}
    out["arms"] = record.get("arms")
    return out


def json_default(value: Any) -> Any:
    """Serialise numpy and date values in gate records."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    raise TypeError(f"Not JSON serialisable: {type(value)}")
