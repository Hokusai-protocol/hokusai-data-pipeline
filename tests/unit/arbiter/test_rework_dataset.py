"""HOK-2818: dataset assembly with time-split and leave-repo-out enforced in code."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.arbiter import assemble_rework_dataset as cli
from src.arbiter.feature_audit import (
    ColumnLeakageError,
    LeakageError,
    ValidatorUnavailableError,
)
from src.arbiter.rework_dataset import (
    FEATURE_MANIFEST_VERSION,
    META_COLUMNS,
    LeaveRepoOut,
    TimeSplit,
    assemble,
    check_split,
    load_dataset,
)
from tests.unit.arbiter.conftest import (
    DEV_REPOS,
    FAKE_VALIDATOR,
    SEALED_REPO,
    build_corpus,
)

TRAIN_UNTIL = date(2026, 2, 1)


def _assemble(corpus: dict[str, Path], split=None, **kwargs):
    return assemble(
        features_root=corpus["root"],
        labels_root=corpus["root"],
        slice_file=corpus["slice"],
        split=split or TimeSplit(train_until=TRAIN_UNTIL),
        **kwargs,
    )


# --------------------------------------------------------------------------- assembly


def test_time_split_assembles_development_repos_only(corpus):
    ds = _assemble(corpus)
    assert sorted(set(ds.rows["repo"])) == list(DEV_REPOS)
    assert SEALED_REPO not in ds.base_rates["by_repo"]
    assert ds.provenance["evaluation_slice"]["excluded_repos"] == 1
    assert all(i["repo"] != SEALED_REPO for i in ds.provenance["inputs"])
    # Default columns are every declared input except content hashes.
    assert ds.feature_columns == (
        "feature.shape.loc_touched",
        "feature.history.file_commits_90d",
        "feature.agent.tool_family",
    )


def test_rejected_rows_are_counted_with_reasons(corpus):
    ds = _assemble(corpus)
    reasons = ds.provenance["counts"]["rejected_by_reason"]
    assert reasons == {
        "feature_row_missing": 1,
        "label_immature": 3,
        "label_missing": 1,
        "label_null:base_label_missing": 1,
        "merge_sha_mismatch": 1,
    }
    assert len(ds.rejected) == sum(reasons.values())
    assert ds.provenance["counts"]["accepted"] == 3 * 40 - 4
    assert {r["reason"] for r in ds.rejected if r["pr_number"] == 1040} == {"label_immature"}


def test_time_split_embargoes_training_rows_whose_label_window_crosses(corpus):
    ds = _assemble(corpus)
    (split,) = list(ds.splits())
    cut = pd.Timestamp("2026-02-01", tz="UTC")
    assert (split.train["as_of"] < cut).all()
    assert (split.train["label_observed_until"] <= cut).all()
    assert (split.evaluation["as_of"] >= cut).all()
    roles = ds.provenance["counts"]["by_role"]
    assert roles["embargo"] > 0
    assert roles["train"] == len(split.train) and roles["eval"] == len(split.evaluation)
    assert set(ds.base_rates["by_role"]) == set(roles)


def test_x_holds_audited_feature_columns_only(corpus):
    ds = _assemble(
        corpus,
        segment_columns=["segment.ci.checks_failed_by_merge"],
        allow_segments=True,
    )
    assert "segment.ci.checks_failed_by_merge" in ds.rows.columns
    (split,) = list(ds.splits())
    assert list(split.X("train").columns) == list(ds.feature_columns)
    assert "label" not in split.X("eval").columns
    assert split.y("train").isin([0, 1]).all()
    assert (split.weights("train") == 1.0).all()


def test_leave_repo_out_gives_one_fold_per_repo(corpus):
    ds = _assemble(corpus, split=LeaveRepoOut())
    folds = list(ds.splits())
    assert [f.name for f in folds] == list(DEV_REPOS)
    for fold in folds:
        assert set(fold.evaluation["repo"]) == {fold.name}
        assert fold.name not in set(fold.train["repo"])


def test_leave_repo_out_with_chosen_repos(corpus):
    split = LeaveRepoOut(eval_repos=("acme/beta",), train_repos=("acme/alpha",))
    (fold,) = list(_assemble(corpus, split=split).splits())
    assert set(fold.train["repo"]) == {"acme/alpha"}


def test_base_rates_by_repo_and_horizon(corpus):
    rates = _assemble(corpus).base_rates
    assert set(rates["by_repo"]["acme/beta"]) == {"14", "30", "60"}
    beta = rates["by_repo"]["acme/beta"]["30"]
    assert beta["rows"] == 41 and beta["null"] == 0
    assert rates["pooled"]["30"]["rows"] == 41 * 3 - 1


def test_provenance_records_versions_and_split(corpus):
    prov = _assemble(corpus).provenance
    assert prov["feature_manifest_version"] == FEATURE_MANIFEST_VERSION
    assert prov["target"] == {
        "name": "corrective_rework",
        "horizon_days": 30,
        "label_schema_version": "1.1.0",
        "definition_version": "cr-0.1.0",
        "labeller_version": "1.0.0",
        "survival_labeller_version": "1.4.0",
        "label_as_of": "2026-10-20T00:00:00Z",
    }
    assert prov["split"] == {"mode": "time", "train_until": "2026-02-01", "eval_from": "2026-02-01"}
    assert prov["decision_record_contract"].startswith("wavemill:")
    assert prov["columns"]["audit"]["ok"] is True
    assert len(prov["evaluation_slice"]["sha256"]) == 64


def test_write_and_load_round_trip(corpus, tmp_path):
    ds = _assemble(corpus)
    out = ds.write(tmp_path / "ds")
    loaded = load_dataset(out, slice_file=corpus["slice"])
    assert set(loaded.provenance["files"]) == {
        "rows.parquet",
        "rejected.jsonl.gz",
        "base_rates.json",
    }
    assert len(loaded.rows) == len(ds.rows)
    assert list(loaded.rows.columns) == [*META_COLUMNS, *ds.feature_columns]
    assert len(list(loaded.splits())[0].evaluation) == len(list(ds.splits())[0].evaluation)
    with pytest.raises(FileExistsError):
        ds.write(out)


def test_load_rejects_a_changed_file(corpus, tmp_path):
    out = _assemble(corpus).write(tmp_path / "ds")
    rows = pd.read_parquet(out / "rows.parquet")
    rows.loc[0, "label"] = 1 - rows.loc[0, "label"]
    rows.to_parquet(out / "rows.parquet", index=False)
    with pytest.raises(LeakageError, match="hash"):
        load_dataset(out)


def test_load_rejects_a_different_slice(corpus, tmp_path):
    out = _assemble(corpus).write(tmp_path / "ds")
    other = tmp_path / "other-slice.json"
    other.write_text(json.dumps({"procedure": "hok-3028-evaluation-slice", "repos": ["x/y"]}))
    with pytest.raises(LeakageError, match="different evaluation slice"):
        load_dataset(out, slice_file=other)


def test_unweighted_label_provenance_is_rejected_not_trained(tmp_path, fake_validator):
    c = build_corpus(tmp_path / "c", provenance="owner_corrected")
    with pytest.raises(LeakageError, match="No rows survived"):
        _assemble(c)
    ds = _assemble(c, provenance_weights={"owner_corrected": 3.0})
    assert (ds.rows["sample_weight"] == 3.0).all()


# --------------------------------------------------------------------------- leaky configurations


def test_overlapping_time_periods_are_rejected():
    with pytest.raises(LeakageError, match="overlap"):
        TimeSplit(train_until=date(2026, 3, 1), eval_from=date(2026, 2, 1))


def test_time_boundaries_must_be_dates():
    from datetime import datetime

    with pytest.raises(LeakageError, match="calendar dates"):
        TimeSplit(train_until=datetime(2026, 2, 1, 12))


def test_repo_on_both_sides_of_leave_repo_out_is_rejected():
    with pytest.raises(LeakageError, match="both sides"):
        LeaveRepoOut(eval_repos=("acme/alpha",), train_repos=("acme/alpha", "acme/beta"))


def test_asking_for_a_sealed_repo_is_rejected(corpus):
    with pytest.raises(LeakageError, match="evaluation slice"):
        _assemble(corpus, repos=["acme/alpha", SEALED_REPO])


def test_missing_slice_file_is_rejected(corpus, tmp_path):
    with pytest.raises(LeakageError, match="not found"):
        assemble(
            features_root=corpus["root"],
            labels_root=corpus["root"],
            slice_file=tmp_path / "absent.json",
            split=TimeSplit(train_until=TRAIN_UNTIL),
        )


@pytest.mark.parametrize(
    ("columns", "code"),
    [
        (
            ["feature.shape.loc_touched", "segment.ci.checks_failed_by_merge"],
            "segment_in_arm_input",
        ),
        (["label.corrective"], "label_field"),
        (["feature.process.reviews_after_merge"], "undeclared_column"),
    ],
)
def test_rejected_feature_columns_stop_assembly(corpus, columns, code):
    with pytest.raises(ColumnLeakageError) as caught:
        _assemble(corpus, feature_columns=columns)
    assert caught.value.codes == [code]


def test_segment_columns_need_allow_segments(corpus):
    with pytest.raises(LeakageError, match="allow_segments"):
        _assemble(corpus, segment_columns=["segment.ci.checks_failed_by_merge"])
    with pytest.raises(LeakageError, match="Not segment columns"):
        _assemble(corpus, segment_columns=["feature.shape.loc_touched"], allow_segments=True)


def test_rows_from_another_manifest_are_rejected(tmp_path, fake_validator):
    c = build_corpus(tmp_path / "c", manifest_version="rr-merge-features/0.4.0")
    with pytest.raises(LeakageError, match="0.4.0"):
        _assemble(c)


def test_unpinned_target_definition_is_rejected(tmp_path, fake_validator):
    c = build_corpus(tmp_path / "c", definition_version="cr-0.2.0")
    with pytest.raises(LeakageError, match="not pinned"):
        _assemble(c)


def test_validator_on_another_manifest_is_rejected(corpus, monkeypatch):
    monkeypatch.setenv(
        "HOKUSAI_SCAN_CMD", f"{sys.executable} {FAKE_VALIDATOR} rr-merge-features/0.4.0"
    )
    with pytest.raises(LeakageError, match="0.4.0"):
        _assemble(corpus)


def test_missing_validator_fails_rather_than_passes(corpus, monkeypatch):
    monkeypatch.setenv("HOKUSAI_SCAN_CMD", "/nonexistent/hokusai-scan")
    with pytest.raises(ValidatorUnavailableError):
        _assemble(corpus)


def test_hand_built_time_split_with_crossing_labels_is_rejected(corpus):
    ds = _assemble(corpus)
    split = TimeSplit(train_until=TRAIN_UNTIL)
    leaky_train = ds.rows[ds.rows["as_of"] < pd.Timestamp("2026-02-01", tz="UTC")]
    evaluation = ds.rows[ds.rows["as_of"] >= pd.Timestamp("2026-02-01", tz="UTC")]
    with pytest.raises(LeakageError, match="labels observed after"):
        check_split(leaky_train, evaluation, split, label_as_of=ds.label_as_of)


def test_hand_built_leave_repo_out_with_shared_repo_is_rejected(corpus):
    ds = _assemble(corpus, split=LeaveRepoOut())
    train = ds.rows[ds.rows["repo"] != "acme/beta"]
    evaluation = ds.rows[ds.rows["repo"].isin(["acme/beta", "acme/alpha"])].drop_duplicates()
    with pytest.raises(LeakageError):
        check_split(train, evaluation, LeaveRepoOut(), label_as_of=ds.label_as_of)


def test_hand_built_split_sharing_rows_is_rejected(corpus):
    ds = _assemble(corpus)
    with pytest.raises(LeakageError, match="both train and evaluation"):
        check_split(
            ds.rows, ds.rows, TimeSplit(train_until=TRAIN_UNTIL), label_as_of=ds.label_as_of
        )


# --------------------------------------------------------------------------- CLI


def test_cli_assembles_and_prints_pooled_counts(corpus, tmp_path, capsys):
    code = cli.main(
        [
            "--features-root",
            str(corpus["root"]),
            "--labels-root",
            str(corpus["root"]),
            "--slice",
            str(corpus["slice"]),
            "--split",
            "time",
            "--train-until",
            "2026-02-01",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["development_repos"] == 3
    assert "acme/" not in json.dumps(summary)


def test_cli_exits_1_on_leaky_configuration(corpus, tmp_path, capsys):
    code = cli.main(
        [
            "--features-root",
            str(corpus["root"]),
            "--labels-root",
            str(corpus["root"]),
            "--slice",
            str(corpus["slice"]),
            "--split",
            "time",
            "--train-until",
            "2026-03-01",
            "--eval-from",
            "2026-02-01",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == 1
    assert "overlap" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
