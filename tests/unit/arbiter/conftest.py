"""A small synthetic corpus in the published layout, for HOK-2818 assembly tests."""

from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from src.arbiter.rework_dataset import (
    DEFAULT_TARGET_DEFINITION,
    FEATURE_MANIFEST_VERSION,
    corrective_file,
)

FAKE_VALIDATOR = (
    Path(__file__).resolve().parents[2] / "fixtures" / "arbiter" / "fake_feature_audit.py"
)
LABEL_AS_OF = "2026-10-20T00:00:00Z"
DEV_REPOS = ("acme/alpha", "acme/beta", "acme/delta")
SEALED_REPO = "acme/sealed"
START = datetime(2025, 6, 1, 12, tzinfo=timezone.utc)


def _gz(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _iso(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_corpus(
    root: Path,
    *,
    manifest_version: str = FEATURE_MANIFEST_VERSION,
    definition_version: str = DEFAULT_TARGET_DEFINITION,
    provenance: str = "harvested",
    label_file: str | None = None,
) -> dict[str, Path]:
    """Write features and labels for three development repos and one sealed repo.

    Each repo has 40 PRs merged every 10 days from 2025-06-01, then one PR merged
    2026-10-01 whose 30-day label window had not closed. ``acme/alpha`` also has a
    null label, a merge SHA mismatch, a missing label and a label with no feature row.
    """
    for gid, repo in enumerate((*DEV_REPOS, SEALED_REPO)):
        d = root / repo.replace("/", "__")
        features, corrective, survival = [], [], []
        merges = [START + timedelta(days=10 * i) for i in range(40)]
        merges.append(datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
        for i, at in enumerate(merges):
            number = 1000 + i
            sha = f"{gid:02d}{i:038d}"
            positive = (i + gid) % 4 == 0
            features.append(
                {
                    "manifest_version": manifest_version,
                    "repo": repo,
                    "pr_number": number,
                    "merge_sha": sha,
                    "as_of": _iso(at),
                    "features": {
                        "feature.shape.loc_touched": 10 * i + (500 if positive else 0),
                        "feature.history.file_commits_90d": i,
                        "feature.agent.tool_family": "none",
                        "feature.content.title_sha256": "0" * 64,
                        "segment.ci.checks_failed_by_merge": i % 3,
                        "segment.author.dependency_bot": i % 10 == 9,
                    },
                }
            )
            url = f"https://github.com/{repo}/pull/{number}"
            for h in (14, 30, 60):
                corrective.append(
                    {
                        "schema_version": "1.1.0",
                        "record_type": "corrective",
                        "prUrl": url,
                        "horizon_days": h,
                        "label_provenance": provenance,
                        "corrective": positive,
                        "reason_codes": [],
                        "envelope": {
                            "definition_version": definition_version,
                            "labeller_version": "1.0.0",
                            "as_of": LABEL_AS_OF,
                        },
                    }
                )
                survival.append(
                    {
                        "prUrl": url,
                        "horizon_days": h,
                        "envelope": {"labeller_version": "1.4.0", "merge_sha": sha},
                    }
                )
        if repo == "acme/alpha":
            for row in corrective:
                if row["prUrl"].endswith("/1001"):
                    row["corrective"] = None
                    row["reason_codes"] = ["base_label_missing"]
            for row in survival:
                if row["prUrl"].endswith("/1002"):
                    row["envelope"]["merge_sha"] = "f" * 40
            corrective = [r for r in corrective if not r["prUrl"].endswith("/1003")]
            features = [f for f in features if f["pr_number"] != 1004]
        _gz(d / "features.jsonl.gz", features)
        _gz(d / (label_file or corrective_file(definition_version)), corrective)
        _gz(d / "s2.jsonl.gz", survival)
    slice_file = root / "slice.json"
    slice_file.write_text(
        json.dumps({"procedure": "hok-3028-evaluation-slice", "repos": [SEALED_REPO]})
    )
    return {"root": root, "slice": slice_file}


@pytest.fixture
def fake_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{sys.executable} {FAKE_VALIDATOR} {FEATURE_MANIFEST_VERSION}"
    monkeypatch.setenv("HOKUSAI_SCAN_CMD", command)


@pytest.fixture
def corpus(tmp_path: Path, fake_validator: None) -> dict[str, Path]:
    return build_corpus(tmp_path / "corpus")
