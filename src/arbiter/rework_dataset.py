# ruff: noqa: ANN101, C901, S603 - git is called with fixed arguments; self needs no annotation; the gates read best as one sequence of refusals
"""Rework Risk training dataset assembly, with the split rules enforced in code (HOK-2818).

Rows come from two published runs, joined per repo on the PR and checked on
``(repo, merge_sha)``:

* merge-time features, ``rr-merge-features/1.0.0`` (HOK-3023), in
  ``<root>/<owner>__<name>/features.jsonl.gz``
* the ``corrective_rework`` target (HOK-3020) in ``corrective.jsonl.gz`` and the
  S2 survival rows in ``s2.jsonl.gz`` (HOK-3022), which carry the merge SHA

What this module refuses, rather than warns about:

* feature columns the shared validator rejects (post-merge sources, ``label.*``,
  denylisted label-side fields, undeclared columns, ``segment.*`` as an input)
* feature rows from any manifest other than the frozen one, and labels from an
  unpinned target definition or from mixed label runs
* any repo in the HOK-3028 evaluation slice: its rows are never read, and asking
  for one is an error
* a time split whose evaluation period starts before its training period ends,
  and training rows whose label window runs past the end of training
* a leave-repo-out split with an evaluation repo on the training side
* rows whose label window had not closed when the labels were computed

Every rejected row is written out with its reason. The assembled dataset carries
provenance (inputs and their hashes, schema versions, split, slice hash, column
audit) and base rates by repo and horizon. ``load_dataset`` checks it all again.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Union

import pandas as pd

from src.arbiter.feature_audit import (
    AuditResult,
    LeakageError,
    print_manifest,
    require_columns_pass,
)

DATASET_SCHEMA_VERSION = "rework_risk_dataset/1.0.0"
FEATURE_MANIFEST_VERSION = "rr-merge-features/1.0.0"
LABEL_SCHEMA_VERSION = "1.1.0"
TARGET_NAME = "corrective_rework"
# Definitions a dataset may be built on. A new definition must be added here on
# purpose, never picked up silently. cr-0.2.0 (reverts and repair references
# only) is the HOK-3269 candidate; HOK-3028's target is whichever one is pinned.
DEFAULT_TARGET_DEFINITION = "cr-0.1.0"
TARGET_DEFINITIONS = frozenset({"cr-0.1.0", "cr-0.2.0"})


def corrective_file(definition: str) -> str:
    """Return the label file name for a definition, as ``corpus-corrective(-derive)`` writes it."""
    if definition not in TARGET_DEFINITIONS:
        raise LeakageError(f"Target definition {definition} is not listed in TARGET_DEFINITIONS")
    if definition == DEFAULT_TARGET_DEFINITION:
        return "corrective.jsonl.gz"
    return f"corrective.{definition}.jsonl.gz"


HORIZONS = (14, 30, 60)
DECISION_RECORD_CONTRACT = "wavemill:docs/arbiter/decision-record-contract.md@4389effb"
SLICE_PROCEDURE = "hok-3028-evaluation-slice"
# Every label provenance needs a weight before its rows can train. Owner-corrected
# (Tier 2b) labels get theirs after they have been used for labeller error analysis.
DEFAULT_PROVENANCE_WEIGHTS: Mapping[str, float] = {"harvested": 1.0}

META_COLUMNS = (
    "repo",
    "pr_number",
    "merge_sha",
    "as_of",
    "label_observed_until",
    "label",
    "label_provenance",
    "sample_weight",
)
ROWS_FILE = "rows.parquet"
REJECTED_FILE = "rejected.jsonl.gz"
BASE_RATES_FILE = "base_rates.json"
PROVENANCE_FILE = "provenance.json"


# --------------------------------------------------------------------------- splits


def _as_date(value: date | str) -> date:
    if isinstance(value, datetime):
        raise LeakageError("Split boundaries are calendar dates (UTC), not times")
    return value if isinstance(value, date) else date.fromisoformat(value)


def _midnight(day: date) -> pd.Timestamp:
    return pd.Timestamp(datetime(day.year, day.month, day.day, tzinfo=timezone.utc))


@dataclass(frozen=True)
class TimeSplit:
    """Train on rows merged before ``train_until`` whose label window closed by then.

    Evaluate on rows merged on or after ``eval_from`` (default ``train_until``).
    Rows merged before ``train_until`` whose label window runs past it are held
    back (role ``embargo``): their labels saw the evaluation period.
    """

    train_until: date
    eval_from: date | None = None
    mode: str = field(default="time", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "train_until", _as_date(self.train_until))
        eval_from = self.train_until if self.eval_from is None else _as_date(self.eval_from)
        object.__setattr__(self, "eval_from", eval_from)
        if eval_from < self.train_until:
            raise LeakageError(
                f"Evaluation starts {eval_from} but training runs to {self.train_until}: "
                "the periods overlap"
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "train_until": self.train_until.isoformat(),
            "eval_from": self.eval_from.isoformat(),
        }


@dataclass(frozen=True)
class LeaveRepoOut:
    """Score each evaluation repo with a model trained only on the other repos.

    ``eval_repos`` of ``None`` means one fold per repo. ``train_repos`` of
    ``None`` means every other repo in the dataset.
    """

    eval_repos: tuple[str, ...] | None = None
    train_repos: tuple[str, ...] | None = None
    mode: str = field(default="leave_repo_out", init=False)

    def __post_init__(self) -> None:
        for name in ("eval_repos", "train_repos"):
            value = getattr(self, name)
            if value is not None:
                if isinstance(value, str):
                    raise LeakageError(f"{name} must be a list of repos, not one string")
                object.__setattr__(self, name, tuple(sorted(set(value))))
        if self.eval_repos is not None and self.train_repos is not None:
            both = set(self.eval_repos) & set(self.train_repos)
            if both:
                raise LeakageError(f"Repos on both sides of a leave-repo-out split: {sorted(both)}")

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "eval_repos": None if self.eval_repos is None else list(self.eval_repos),
            "train_repos": None if self.train_repos is None else list(self.train_repos),
        }


SplitSpec = Union[TimeSplit, LeaveRepoOut]  # noqa: UP007 - a runtime alias


def split_from_json(data: Mapping[str, Any]) -> SplitSpec:
    if data.get("mode") == "time":
        return TimeSplit(train_until=data["train_until"], eval_from=data["eval_from"])
    if data.get("mode") == "leave_repo_out":

        def opt(key: str) -> tuple[str, ...] | None:
            return None if data.get(key) is None else tuple(data[key])

        return LeaveRepoOut(eval_repos=opt("eval_repos"), train_repos=opt("train_repos"))
    raise LeakageError(f"Unknown split mode: {data.get('mode')!r}")


def time_roles(rows: pd.DataFrame, split: TimeSplit) -> pd.Series:
    """Label each row train, eval, embargo or gap under a time split."""
    train_until = _midnight(split.train_until)
    eval_from = _midnight(split.eval_from)
    role = pd.Series("gap", index=rows.index, dtype=object)
    before = rows["as_of"] < train_until
    role[before & (rows["label_observed_until"] <= train_until)] = "train"
    role[before & (rows["label_observed_until"] > train_until)] = "embargo"
    role[rows["as_of"] >= eval_from] = "eval"
    return role


@dataclass(frozen=True)
class Split:
    """One train/evaluation pair. ``X`` returns audited feature columns only."""

    name: str
    train: pd.DataFrame
    evaluation: pd.DataFrame
    feature_columns: tuple[str, ...]

    def _part(self, part: str) -> pd.DataFrame:
        if part not in ("train", "eval"):
            raise ValueError("part is 'train' or 'eval'")
        return self.train if part == "train" else self.evaluation

    def X(self, part: str) -> pd.DataFrame:  # noqa: N802 - the conventional name
        """Feature columns only: no label, weight, identity or segment columns."""
        return self._part(part).loc[:, list(self.feature_columns)]

    def y(self, part: str) -> pd.Series:
        return self._part(part)["label"]

    def weights(self, part: str) -> pd.Series:
        return self._part(part)["sample_weight"]


def check_split(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    split: SplitSpec,
    *,
    label_as_of: pd.Timestamp,
) -> None:
    """Fail if a train/evaluation pair breaks the split rules.

    Independent of how the pair was built, so it also checks pairs a caller
    assembled by hand.
    """
    if train.empty or evaluation.empty:
        raise LeakageError("A split needs rows on both sides")
    shared = set(zip(train["repo"], train["merge_sha"])) & set(
        zip(evaluation["repo"], evaluation["merge_sha"])
    )
    if shared:
        raise LeakageError(f"{len(shared)} rows are in both train and evaluation")
    for side, frame in (("train", train), ("evaluation", evaluation)):
        if (frame["label_observed_until"] > label_as_of).any():
            raise LeakageError(f"{side} has rows whose label window had not closed")
    if isinstance(split, TimeSplit):
        train_until = _midnight(split.train_until)
        if (train["as_of"] >= train_until).any():
            raise LeakageError("Training rows merged after the end of training")
        if (train["label_observed_until"] > train_until).any():
            raise LeakageError("Training labels observed after the end of training")
        if (evaluation["as_of"] < _midnight(split.eval_from)).any():
            raise LeakageError("Evaluation rows merged before the evaluation period")
    elif isinstance(split, LeaveRepoOut):
        both = set(train["repo"]) & set(evaluation["repo"])
        if both:
            raise LeakageError(f"Repos on both sides of a leave-repo-out split: {sorted(both)}")
    else:
        raise LeakageError(f"Unknown split: {split!r}")


# --------------------------------------------------------------------------- dataset


@dataclass
class AssembledDataset:
    """Accepted rows, rejected rows, the split and their provenance."""

    rows: pd.DataFrame
    rejected: list[dict[str, Any]]
    split: SplitSpec
    feature_columns: tuple[str, ...]
    segment_columns: tuple[str, ...]
    provenance: dict[str, Any]
    base_rates: dict[str, Any]

    @property
    def label_as_of(self) -> pd.Timestamp:
        return pd.Timestamp(self.provenance["target"]["label_as_of"])

    def splits(self) -> Iterator[Split]:
        """Yield every train/evaluation pair of the split, each checked first."""
        rows = self.rows
        pairs: list[tuple[str, pd.DataFrame, pd.DataFrame]] = []
        if isinstance(self.split, TimeSplit):
            role = time_roles(rows, self.split)
            pairs.append(("time", rows[role == "train"], rows[role == "eval"]))
        else:
            present = sorted(set(rows["repo"]))
            for repo in self.split.eval_repos or present:
                if repo not in present:
                    raise LeakageError(f"Evaluation repo {repo} is not in the dataset")
                train_mask = rows["repo"] != repo
                if self.split.train_repos is not None:
                    train_mask &= rows["repo"].isin(self.split.train_repos)
                pairs.append((repo, rows[train_mask], rows[rows["repo"] == repo]))
        for name, train, evaluation in pairs:
            check_split(train, evaluation, self.split, label_as_of=self.label_as_of)
            yield Split(
                name=name,
                train=train.reset_index(drop=True),
                evaluation=evaluation.reset_index(drop=True),
                feature_columns=self.feature_columns,
            )

    def write(self, out_dir: str | Path) -> Path:
        out = Path(out_dir).expanduser()
        if (out / PROVENANCE_FILE).exists():
            raise FileExistsError(f"{out} already holds a dataset; use a new directory")
        out.mkdir(parents=True, exist_ok=True)
        self.rows.to_parquet(out / ROWS_FILE, index=False)
        with gzip.open(out / REJECTED_FILE, "wt") as f:
            for entry in self.rejected:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
        _write_json(out / BASE_RATES_FILE, self.base_rates)
        provenance = dict(self.provenance)
        provenance["files"] = {
            name: _sha256_file(out / name) for name in (ROWS_FILE, REJECTED_FILE, BASE_RATES_FILE)
        }
        _write_json(out / PROVENANCE_FILE, provenance)
        self.provenance = provenance
        return out


def assemble(
    *,
    features_root: str | Path,
    labels_root: str | Path,
    slice_file: str | Path,
    split: SplitSpec,
    horizon_days: int = 30,
    target_definition: str = DEFAULT_TARGET_DEFINITION,
    feature_columns: Sequence[str] | None = None,
    segment_columns: Sequence[str] = (),
    allow_segments: bool = False,
    repos: Sequence[str] | None = None,
    provenance_weights: Mapping[str, float] | None = None,
) -> AssembledDataset:
    """Build a dataset from the development repos under the two roots."""
    label_file = corrective_file(target_definition)
    if horizon_days not in HORIZONS:
        raise ValueError(f"horizon_days must be one of {HORIZONS}")
    if not isinstance(split, (TimeSplit, LeaveRepoOut)):
        raise LeakageError(f"Unknown split: {split!r}")
    weights = dict(DEFAULT_PROVENANCE_WEIGHTS if provenance_weights is None else provenance_weights)
    features_root = Path(features_root).expanduser()
    labels_root = Path(labels_root).expanduser()

    sealed, slice_sha = read_slice(slice_file)
    available = _repo_dirs(features_root)
    if repos is not None:
        asked_sealed = sorted(set(repos) & sealed)
        if asked_sealed:
            raise LeakageError(
                f"{len(asked_sealed)} requested repo(s) are in the HOK-3028 evaluation slice"
            )
        missing = sorted(set(repos) - set(available))
        if missing:
            raise FileNotFoundError(f"No feature rows for: {missing}")
        chosen = sorted(repos)
    else:
        chosen = sorted(r for r in available if r not in sealed)
    if not chosen:
        raise LeakageError("No development repos to assemble")

    feature_columns, audit = audit_feature_columns(feature_columns)
    segment_columns, segment_audit = audit_segment_columns(segment_columns, allow_segments)

    label_meta: dict[str, set[Any]] = defaultdict(set)
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    base_rates: dict[str, Any] = {"horizon_days": list(HORIZONS), "by_repo": {}}

    for repo in chosen:
        label_dir = labels_root / _dir_name(repo)
        feature_path = available[repo]
        corrective_path = label_dir / label_file
        survival_path = label_dir / "s2.jsonl.gz"
        for path in (corrective_path, survival_path):
            if not path.exists():
                raise FileNotFoundError(f"Missing label file {path}")
        inputs.append(
            {
                "repo": repo,
                "features_sha256": _sha256_file(feature_path),
                "corrective_sha256": _sha256_file(corrective_path),
                "survival_sha256": _sha256_file(survival_path),
            }
        )
        labels, rates = _read_corrective(repo, corrective_path, horizon_days, label_meta)
        base_rates["by_repo"][repo] = rates
        merge_shas = _read_merge_shas(repo, survival_path, horizon_days, label_meta)
        label_as_of = _single(label_meta, "label_as_of")
        columns = (*feature_columns, *segment_columns)
        seen: set[int] = set()
        for row in _read_jsonl(feature_path):
            _check_feature_row(repo, feature_path, row)
            number = row["pr_number"]
            if number in seen:
                record, reason = None, "duplicate_feature_row"
            else:
                seen.add(number)
                record, reason = _join_row(
                    row,
                    labels.get(number),
                    merge_shas.get(number),
                    horizon_days=horizon_days,
                    label_as_of=label_as_of,
                    weights=weights,
                    columns=columns,
                )
            if record is None:
                rejected.append(
                    {
                        "repo": repo,
                        "pr_number": number,
                        "merge_sha": row.get("merge_sha"),
                        "reason": reason,
                    }
                )
            else:
                records.append(record)
        for number in sorted(set(labels) - seen):
            rejected.append(
                {
                    "repo": repo,
                    "pr_number": number,
                    "merge_sha": merge_shas.get(number),
                    "reason": "feature_row_missing",
                }
            )

    versions = _check_label_meta(label_meta)
    if versions["definition_version"] != target_definition:
        raise LeakageError(
            f"Asked for {target_definition}, but {label_file} holds "
            f"{versions['definition_version']} labels"
        )
    rows = pd.DataFrame.from_records(
        records, columns=[*META_COLUMNS, *feature_columns, *segment_columns]
    )
    if rows.empty:
        raise LeakageError("No rows survived assembly")
    rows["as_of"] = pd.to_datetime(rows["as_of"], utc=True)
    rows["label_observed_until"] = pd.to_datetime(rows["label_observed_until"], utc=True)
    rows = rows.sort_values(["as_of", "repo", "pr_number"], kind="mergesort").reset_index(drop=True)

    counts: dict[str, Any] = {
        "accepted": int(len(rows)),
        "positives": int(rows["label"].sum()),
        "rejected": len(rejected),
        "rejected_by_reason": dict(sorted(Counter(r["reason"] for r in rejected).items())),
    }
    base_rates["pooled"] = _pool(base_rates["by_repo"])
    base_rates["accepted"] = {"horizon_days": horizon_days, **_rate(rows["label"])}
    if isinstance(split, TimeSplit):
        role = time_roles(rows, split)
        counts["by_role"] = dict(sorted(Counter(role).items()))
        base_rates["by_role"] = {r: _rate(rows.loc[role == r, "label"]) for r in sorted(set(role))}

    provenance = {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code": _code_version(),
        "feature_manifest_version": FEATURE_MANIFEST_VERSION,
        "decision_record_contract": DECISION_RECORD_CONTRACT,
        "target": {
            "name": TARGET_NAME,
            "horizon_days": horizon_days,
            **versions,
        },
        "split": split.to_json(),
        "evaluation_slice": {
            "procedure": SLICE_PROCEDURE,
            "sha256": slice_sha,
            "excluded_repos": len(sealed),
        },
        "columns": {
            "features": list(feature_columns),
            "segments": list(segment_columns),
            "audit": _audit_json(audit),
            "segment_audit": None if segment_audit is None else _audit_json(segment_audit),
        },
        "sample_weights": weights,
        "inputs": inputs,
        "counts": counts,
    }
    dataset = AssembledDataset(
        rows=rows,
        rejected=rejected,
        split=split,
        feature_columns=tuple(feature_columns),
        segment_columns=tuple(segment_columns),
        provenance=provenance,
        base_rates=base_rates,
    )
    for _ in dataset.splits():
        pass
    return dataset


def load_dataset(
    path: str | Path,
    *,
    slice_file: str | Path | None = None,
    verify_columns: bool = True,
) -> AssembledDataset:
    """Load an assembled dataset and check it again before anyone trains on it."""
    root = Path(path).expanduser()
    provenance = json.loads((root / PROVENANCE_FILE).read_text())
    if provenance.get("dataset_schema_version") != DATASET_SCHEMA_VERSION:
        raise LeakageError(f"Unsupported dataset schema {provenance.get('dataset_schema_version')}")
    if provenance.get("feature_manifest_version") != FEATURE_MANIFEST_VERSION:
        raise LeakageError(f"Dataset built from {provenance.get('feature_manifest_version')}")
    for name, expected in provenance.get("files", {}).items():
        if _sha256_file(root / name) != expected:
            raise LeakageError(f"{name} does not match its recorded hash")
    if set(provenance.get("files", {})) != {ROWS_FILE, REJECTED_FILE, BASE_RATES_FILE}:
        raise LeakageError("Dataset provenance does not list its files")
    columns = provenance["columns"]
    if verify_columns:
        require_columns_pass(columns["features"], manifest_version=FEATURE_MANIFEST_VERSION)
    rows = pd.read_parquet(root / ROWS_FILE)
    expected_columns = [*META_COLUMNS, *columns["features"], *columns["segments"]]
    if list(rows.columns) != expected_columns:
        raise LeakageError("Row columns differ from the recorded columns")
    if slice_file is not None:
        sealed, sha = read_slice(slice_file)
        if sha != provenance["evaluation_slice"]["sha256"]:
            raise LeakageError("Dataset was assembled against a different evaluation slice")
        if set(rows["repo"]) & sealed:
            raise LeakageError("Dataset holds evaluation-slice rows")
    with gzip.open(root / REJECTED_FILE, "rt") as f:
        rejected = [json.loads(line) for line in f]
    dataset = AssembledDataset(
        rows=rows,
        rejected=rejected,
        split=split_from_json(provenance["split"]),
        feature_columns=tuple(columns["features"]),
        segment_columns=tuple(columns["segments"]),
        provenance=provenance,
        base_rates=json.loads((root / BASE_RATES_FILE).read_text()),
    )
    for _ in dataset.splits():
        pass
    return dataset


# --------------------------------------------------------------------------- inputs


def read_slice(slice_file: str | Path) -> tuple[set[str], str]:
    """Return the sealed repos and the slice file's SHA-256. The file is required."""
    path = Path(slice_file).expanduser()
    if not path.exists():
        raise LeakageError(
            f"Evaluation slice file {path} not found: without it the sealed repos "
            "cannot be excluded"
        )
    data = path.read_bytes()
    slice_def = json.loads(data)
    if slice_def.get("procedure") != SLICE_PROCEDURE or not slice_def.get("repos"):
        raise LeakageError(f"{path} is not a {SLICE_PROCEDURE} file")
    return set(slice_def["repos"]), hashlib.sha256(data).hexdigest()


def default_feature_columns(manifest: Mapping[str, Any]) -> list[str]:
    """Every arm input the manifest declares, except content hashes."""
    return [
        e["name"] for e in manifest["entries"] if not e["segment"] and e["kind"] != "content_sha256"
    ]


def audit_feature_columns(columns: Sequence[str] | None) -> tuple[list[str], AuditResult]:
    """Gate every arm input through the validator. ``None`` means every declared input."""
    if columns is None:
        manifest = print_manifest()
        if manifest.get("manifest_version") != FEATURE_MANIFEST_VERSION:
            raise LeakageError(f"Validator manifest is {manifest.get('manifest_version')}")
        columns = default_feature_columns(manifest)
    columns = list(columns)
    if len(set(columns)) != len(columns):
        raise LeakageError("Feature columns repeat")
    audit = require_columns_pass(columns, manifest_version=FEATURE_MANIFEST_VERSION)
    return columns, audit


def audit_segment_columns(
    columns: Sequence[str], allow_segments: bool
) -> tuple[list[str], AuditResult | None]:
    """Gate segment.* columns carried for reporting. They never enter ``X``."""
    columns = list(columns)
    if not columns:
        return [], None
    if not allow_segments:
        raise LeakageError("Segment columns need allow_segments (--allow-segments)")
    not_segments = [c for c in columns if not c.startswith("segment.")]
    if not_segments:
        raise LeakageError(f"Not segment columns: {not_segments}")
    audit = require_columns_pass(
        columns, manifest_version=FEATURE_MANIFEST_VERSION, allow_segments=True
    )
    return columns, audit


def _audit_json(audit: AuditResult) -> dict[str, Any]:
    return {"manifest_version": audit.manifest_version, "ok": audit.ok, "codes": audit.codes}


def _dir_name(repo: str) -> str:
    return repo.replace("/", "__", 1)


def _repo_dirs(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"No feature root {root}")
    out = {}
    for child in sorted(root.iterdir()):
        path = child / "features.jsonl.gz"
        if child.is_dir() and "__" in child.name and path.exists():
            out[child.name.replace("__", "/", 1)] = path
    return out


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _pr_number(repo: str, url: str) -> int:
    prefix = f"https://github.com/{repo}/pull/"
    if not url.startswith(prefix):
        raise LeakageError(f"Label row {url} is not a {repo} PR")
    return int(url[len(prefix) :])


def _read_corrective(
    repo: str, path: Path, horizon: int, meta: dict[str, set[Any]]
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    chosen: dict[int, dict[str, Any]] = {}
    tallies: dict[int, Counter] = {h: Counter() for h in HORIZONS}
    for row in _read_jsonl(path):
        if row.get("record_type") != "corrective":
            raise LeakageError(f"{path}: unexpected record_type {row.get('record_type')}")
        envelope = row["envelope"]
        meta["label_schema_version"].add(row["schema_version"])
        meta["definition_version"].add(envelope["definition_version"])
        meta["labeller_version"].add(envelope["labeller_version"])
        meta["label_as_of"].add(pd.Timestamp(envelope["as_of"]))
        h = row["horizon_days"]
        if h in tallies:
            value = row["corrective"]
            tallies[h]["rows"] += 1
            tallies[h]["null" if value is None else ("true" if value else "false")] += 1
        if h == horizon:
            number = _pr_number(repo, row["prUrl"])
            if number in chosen:
                raise LeakageError(f"{repo}#{number} has two labels at {horizon} days")
            chosen[number] = row
    rates = {}
    for h, t in tallies.items():
        known = t["true"] + t["false"]
        rates[str(h)] = {
            "rows": t["rows"],
            "positives": t["true"],
            "null": t["null"],
            "rate": round(t["true"] / known, 4) if known else None,
        }
    return chosen, rates


def _read_merge_shas(
    repo: str, path: Path, horizon: int, meta: dict[str, set[Any]]
) -> dict[int, str]:
    out: dict[int, str] = {}
    for row in _read_jsonl(path):
        if row["horizon_days"] != horizon:
            continue
        envelope = row["envelope"]
        meta["survival_labeller_version"].add(envelope["labeller_version"])
        number = _pr_number(repo, row["prUrl"])
        sha = envelope.get("merge_sha")
        if sha:
            if out.get(number, sha) != sha:
                raise LeakageError(f"{repo}#{number} has two merge SHAs in {path}")
            out[number] = sha
    return out


def _check_feature_row(repo: str, path: Path, row: Mapping[str, Any]) -> None:
    if row.get("manifest_version") != FEATURE_MANIFEST_VERSION:
        raise LeakageError(
            f"{repo}: feature rows are {row.get('manifest_version')}, "
            f"expected {FEATURE_MANIFEST_VERSION}"
        )
    if row.get("repo") != repo:
        raise LeakageError(f"{path} holds rows for {row.get('repo')}")


def _join_row(
    row: Mapping[str, Any],
    label: Mapping[str, Any] | None,
    merge_sha: str | None,
    *,
    horizon_days: int,
    label_as_of: pd.Timestamp,
    weights: Mapping[str, float],
    columns: Sequence[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Join one feature row to its label. Returns the record, or None and the reason."""
    if label is None:
        return None, "label_missing"
    if label["corrective"] is None:
        return None, "label_null:" + ",".join(sorted(label["reason_codes"]))
    if merge_sha is None:
        return None, "merge_sha_unknown"
    if merge_sha != row.get("merge_sha"):
        return None, "merge_sha_mismatch"
    if not row.get("as_of"):
        return None, "as_of_missing"
    as_of = pd.Timestamp(row["as_of"])
    observed_until = as_of + timedelta(days=horizon_days)
    if observed_until > label_as_of:
        return None, "label_immature"
    provenance = label["label_provenance"]
    if provenance not in weights:
        return None, f"label_provenance_unweighted:{provenance}"
    values = row["features"]
    missing = [c for c in columns if c not in values]
    if missing:
        raise LeakageError(f"{row['repo']}#{row['pr_number']} lacks columns {missing}")
    record = {
        "repo": row["repo"],
        "pr_number": row["pr_number"],
        "merge_sha": merge_sha,
        "as_of": as_of,
        "label_observed_until": observed_until,
        "label": int(bool(label["corrective"])),
        "label_provenance": provenance,
        "sample_weight": float(weights[provenance]),
    }
    record.update({c: values[c] for c in columns})
    return record, None


def _single(meta: Mapping[str, set[Any]], key: str) -> Any:
    values = meta.get(key, set())
    if len(values) != 1:
        raise LeakageError(f"Labels mix {key} values: {sorted(map(str, values))}")
    return next(iter(values))


def _check_label_meta(meta: Mapping[str, set[Any]]) -> dict[str, Any]:
    versions = {
        key: _single(meta, key)
        for key in (
            "label_schema_version",
            "definition_version",
            "labeller_version",
            "survival_labeller_version",
            "label_as_of",
        )
    }
    if versions["label_schema_version"] != LABEL_SCHEMA_VERSION:
        raise LeakageError(f"Label schema {versions['label_schema_version']} is not supported")
    if versions["definition_version"] not in TARGET_DEFINITIONS:
        raise LeakageError(
            f"Target definition {versions['definition_version']} is not listed in "
            "TARGET_DEFINITIONS"
        )
    versions["label_as_of"] = versions["label_as_of"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return versions


def _rate(labels: pd.Series) -> dict[str, Any]:
    n = int(len(labels))
    positives = int(labels.sum()) if n else 0
    return {"rows": n, "positives": positives, "rate": round(positives / n, 4) if n else None}


def _pool(by_repo: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, Any]:
    pooled = {}
    for h in HORIZONS:
        rows = sum(r[str(h)]["rows"] for r in by_repo.values())
        positives = sum(r[str(h)]["positives"] for r in by_repo.values())
        null = sum(r[str(h)]["null"] for r in by_repo.values())
        known = rows - null
        pooled[str(h)] = {
            "rows": rows,
            "positives": positives,
            "null": null,
            "rate": round(positives / known, 4) if known else None,
        }
    return pooled


def _code_version() -> dict[str, Any]:
    here = Path(__file__).resolve().parent
    try:
        commit = subprocess.run(  # noqa: S603, S607
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=here,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(  # noqa: S603, S607
                ["git", "status", "--porcelain", "--", "."],  # noqa: S607
                cwd=here,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {"repo": "hokusai-data-pipeline", "commit": None, "dirty": None}
    return {"repo": "hokusai-data-pipeline", "commit": commit, "dirty": dirty}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, data: Any) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


__all__ = [
    "DATASET_SCHEMA_VERSION",
    "FEATURE_MANIFEST_VERSION",
    "AssembledDataset",
    "LeakageError",
    "LeaveRepoOut",
    "Split",
    "TimeSplit",
    "assemble",
    "audit_feature_columns",
    "audit_segment_columns",
    "check_split",
    "load_dataset",
]
