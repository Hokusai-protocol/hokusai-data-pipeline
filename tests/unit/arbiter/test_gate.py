"""HOK-3028 gate runner: data rules, scoring-once rules and the §6 outcome logic."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.arbiter.feature_audit import LeakageError
from src.arbiter.gate import (
    COMPELLING,
    DEPENDENCY_BOT_COLUMN,
    HALF_WIN,
    INCONCLUSIVE,
    LOSS,
    TABLE_STAKES_FAIL,
    TIE,
    ArmContext,
    GateData,
    Slice,
    VariantScores,
    build_gate_data,
    evaluate_gate,
    public_summary,
    read_sealed_slice,
    rehearsal_slice,
    score_once,
)
from src.arbiter.gate_arms import RehearsalStandIns
from tests.unit.arbiter.conftest import DEV_REPOS, SEALED_REPO, build_corpus

WINDOW = {"merged_from": "2026-01-01", "merged_until": "2026-04-01"}


def _sealed(root: Path) -> tuple[Path, str]:
    """Rewrite the fixture slice with a time window, and return its path and hash."""
    path = root / "slice.json"
    manifest = {
        "procedure": "hok-3028-evaluation-slice",
        "procedure_version": "1.0.0",
        "salt": "00" * 32,
        "repos": [SEALED_REPO],
        "time_window": WINDOW,
    }
    data = (json.dumps(manifest, indent=2) + "\n").encode()
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


@pytest.fixture
def gate_corpus(tmp_path, fake_validator):
    corpus = build_corpus(tmp_path / "c")
    path, sha = _sealed(corpus["root"])
    return {"root": corpus["root"], "slice": path, "sha": sha}


def _data(gate_corpus) -> GateData:
    sealed = read_sealed_slice(gate_corpus["slice"], expected_sha256=gate_corpus["sha"])
    return build_gate_data(
        features_root=gate_corpus["root"],
        labels_root=gate_corpus["root"],
        sealed_slice_file=gate_corpus["slice"],
        evaluation_slice=sealed,
    )


# --------------------------------------------------------------------------- slice and rows


def test_slice_must_match_the_registered_hash(gate_corpus):
    with pytest.raises(LeakageError, match="pre-registered holdout"):
        read_sealed_slice(gate_corpus["slice"])
    sealed = read_sealed_slice(gate_corpus["slice"], expected_sha256=gate_corpus["sha"])
    assert SEALED_REPO not in repr(sealed) and "2026" not in repr(sealed)


def test_training_and_evaluation_rows_follow_the_rule(gate_corpus):
    data = _data(gate_corpus)
    start = pd.Timestamp(WINDOW["merged_from"], tz="UTC")
    end = pd.Timestamp(WINDOW["merged_until"], tz="UTC")
    assert set(data.train["repo"]) == set(DEV_REPOS)
    assert (data.train["as_of"] + pd.Timedelta(days=30) <= start).all()
    assert set(data.evaluation["repo"]) == {SEALED_REPO}
    assert data.evaluation["as_of"].between(start, end, inclusive="left").all()
    assert data.content_columns == ("feature.content.title_sha256",)
    assert data.target_definition == "cr-0.2.0"
    prov = json.dumps(data.provenance)
    assert SEALED_REPO not in prov and "acme/alpha" not in prov


def test_dependency_bots_leave_the_primary_rows(gate_corpus):
    data = _data(gate_corpus)
    bots = data.evaluation[DEPENDENCY_BOT_COLUMN].astype(bool).to_numpy()
    assert bots.any()
    assert (data.primary == ~bots).all()


def test_rehearsal_slice_never_holds_sealed_repos(gate_corpus):
    rehearsal = rehearsal_slice(
        gate_corpus["root"], gate_corpus["slice"], repos=2, merged_until=date(2026, 4, 1)
    )
    assert rehearsal.rehearsal and len(rehearsal.repos) == 2
    assert SEALED_REPO not in rehearsal.repos
    data = build_gate_data(
        features_root=gate_corpus["root"],
        labels_root=gate_corpus["root"],
        sealed_slice_file=gate_corpus["slice"],
        evaluation_slice=rehearsal,
    )
    assert set(data.train["repo"]) == set(DEV_REPOS) - rehearsal.repos
    assert SEALED_REPO not in set(data.train["repo"]) | set(data.evaluation["repo"])


# --------------------------------------------------------------------------- scoring once


def _context(data: GateData) -> ArmContext:
    return ArmContext(
        feature_columns=data.feature_columns,
        categories={"feature.agent.tool_family": ["none", "claude", "codex"]},
        content_columns=data.content_columns,
    )


def test_sealed_slice_is_scored_once_and_reruns_keep_the_original(gate_corpus, tmp_path):
    data = _data(gate_corpus)
    arms = [_ComparatorArms(), _FixedArms()]
    records = tmp_path / "records"
    first = score_once(
        data, arms, _context(data), record_dir=records, resamples=20, allow_dirty=True
    )
    assert first["attempt"] == 1 and Path(first["record_path"]).exists()
    with pytest.raises(LeakageError, match="already been scored"):
        score_once(data, arms, _context(data), record_dir=records, resamples=20, allow_dirty=True)
    second = score_once(
        data,
        arms,
        _context(data),
        record_dir=records,
        resamples=20,
        allow_dirty=True,
        rerun_reason="test: a bug found after scoring",
    )
    assert second["attempt"] == 2 and Path(first["record_path"]).exists()
    summary = json.dumps(public_summary(second), default=str)
    assert SEALED_REPO not in summary and "per_repo" not in summary


def test_stand_ins_cannot_score_the_sealed_slice(gate_corpus, tmp_path):
    data = _data(gate_corpus)
    with pytest.raises(LeakageError, match="stand-in"):
        score_once(
            data,
            [_ComparatorArms(), RehearsalStandIns()],
            _context(data),
            record_dir=tmp_path,
            allow_dirty=True,
        )


def test_arm_code_never_sees_labels_when_scoring(gate_corpus, tmp_path):
    data = _data(gate_corpus)
    spy = _FixedArms()
    score_once(
        data,
        [_ComparatorArms(), spy],
        _context(data),
        record_dir=tmp_path,
        resamples=5,
        allow_dirty=True,
    )
    assert "label" in spy.fit_columns and "label" not in spy.score_columns
    assert not any(c.startswith("segment.") for c in spy.score_columns)
    assert "feature.content.title_sha256" in spy.score_columns


class _ComparatorArms:
    """Arm 1 and arm 2 test doubles: rankings on one fixture column."""

    arm_id = "test-comparators"
    version = "test/1"

    def variants(self):
        return {"cmp.arm1": "arm1", "cmp.arm2": "arm2"}

    def fit(self, train, context):
        return None

    def score(self, fitted, rows, context):
        churn = rows["feature.history.file_commits_90d"].astype(float)
        return {
            "cmp.arm1": pd.DataFrame({"score": churn}),
            "cmp.arm2": pd.DataFrame({"score": -churn}),
        }


class _FixedArms:
    """Arm 4 and arm 5 test doubles that record what they were shown."""

    arm_id = "test-fixed"
    version = "test/1"

    def variants(self):
        return {"fixed.arm4": "arm4", "fixed.arm5": "arm5"}

    def fit(self, train, context):
        self.fit_columns = list(train.columns)
        return None

    def score(self, fitted, rows, context):
        self.score_columns = list(rows.columns)
        base = rows["feature.shape.loc_touched"].astype(float)
        p = (base.rank(pct=True) * 0.1).clip(0.001, 0.999)
        return {
            "fixed.arm4": pd.DataFrame({"score": -base, "probability": p}),
            "fixed.arm5": pd.DataFrame({"score": base, "probability": p}),
        }


# --------------------------------------------------------------------------- §6 logic


def _synthetic(repos: int = 6, n: int = 2000, rate: float = 0.06, seed: int = 1):
    rng = np.random.default_rng(seed)
    repo = np.repeat([f"r{i}" for i in range(repos)], n)
    y = (rng.random(repos * n) < rate).astype(float)
    return rng, repo, y


def _variant(name, role, score, probability=None):
    return VariantScores(name, role, "test", "1", np.asarray(score, float), probability)


def _arms(rng, y, *, strength5, strength4, comparator=0.3, p5=None, p4=None, same_as_arm2=False):
    noise = lambda: rng.normal(size=len(y))  # noqa: E731
    base = np.full(len(y), y.mean())
    s5 = strength5 * y + noise()
    arms = [
        _variant("a5", "arm5", s5, base if p5 is None else p5),
        _variant("a4", "arm4", strength4 * y + noise(), base if p4 is None else p4),
        _variant("a1", "arm1", comparator * y + noise()),
        _variant("a2", "arm2", s5 if same_as_arm2 else comparator * y + noise()),
    ]
    return arms


def test_compelling_when_every_condition_holds():
    rng, repo, y = _synthetic()
    result = evaluate_gate(repo, y, _arms(rng, y, strength5=3.0, strength4=0.5), resamples=200)
    assert result["outcome"] == COMPELLING
    assert result["ranking"]["delta"] >= 0.10 and result["calibration_ok"]


def test_half_win_when_calibration_fails():
    rng, repo, y = _synthetic()
    bad = np.full(len(y), 0.5)
    result = evaluate_gate(
        repo, y, _arms(rng, y, strength5=3.0, strength4=0.5, p5=bad), resamples=200
    )
    assert result["outcome"] == HALF_WIN and not result["calibration"]["brier"]["ok"]


def test_table_stakes_fail_when_arm_5_does_not_beat_arm_2():
    rng, repo, y = _synthetic()
    arms = _arms(rng, y, strength5=3.0, strength4=0.5, same_as_arm2=True)
    result = evaluate_gate(repo, y, arms, resamples=200)
    assert result["outcome"] == TABLE_STAKES_FAIL
    assert not result["beats"]["a2"]["beaten"] and result["beats"]["a1"]["beaten"]


def test_loss_when_arm_4_wins():
    rng, repo, y = _synthetic()
    result = evaluate_gate(
        repo, y, _arms(rng, y, strength5=1.0, strength4=3.0, comparator=0.0), resamples=200
    )
    assert result["outcome"] == LOSS


def test_tie_when_the_gap_is_small():
    rng, repo, y = _synthetic()
    result = evaluate_gate(
        repo, y, _arms(rng, y, strength5=1.6, strength4=1.5, comparator=0.0), resamples=200
    )
    assert result["outcome"] == TIE


def test_inconclusive_below_minimum_power():
    rng, repo, y = _synthetic(repos=4)
    result = evaluate_gate(repo, y, _arms(rng, y, strength5=3.0, strength4=0.5), resamples=50)
    assert result["outcome"] == INCONCLUSIVE and not result["power"]["ok"]


def test_resamples_are_paired_and_repeatable():
    rng, repo, y = _synthetic()
    arms = _arms(rng, y, strength5=3.0, strength4=0.5)
    a = evaluate_gate(repo, y, arms, resamples=100, seed=7)
    b = evaluate_gate(repo, y, arms, resamples=100, seed=7)
    assert a["ranking"]["delta_ci95"] == b["ranking"]["delta_ci95"]
    same = [arms[0], _variant("a4", "arm4", arms[0].score, arms[0].probability), *arms[2:]]
    tied = evaluate_gate(repo, y, same, resamples=100)
    assert tied["ranking"]["delta_ci95"] == [0.0, 0.0]


def test_gate_requires_probabilities_for_arms_4_and_5():
    rng, repo, y = _synthetic()
    arms = _arms(rng, y, strength5=3.0, strength4=0.5)
    arms[1] = _variant("a4", "arm4", arms[1].score, None)
    with pytest.raises(ValueError, match="probability"):
        evaluate_gate(repo, y, arms, resamples=10)


def test_slice_repr_hides_contents():
    s = Slice(
        frozenset({"x/y"}), date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=90), "ab" * 32
    )
    assert "x/y" not in repr(s) and "2026" not in repr(s)


def test_stand_ins_fill_only_the_roles_asked_for():
    assert RehearsalStandIns(("arm4",)).variants() == {"stand_in.arm4": "arm4"}
    assert set(RehearsalStandIns().variants().values()) == {"arm4", "arm5"}
    with pytest.raises(ValueError):
        RehearsalStandIns(("arm6",))
