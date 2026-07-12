"""Cross-repo contract coverage for SDK task descriptors.

The fixture in ``tests/fixtures/sdk_task_descriptor_contract_rows.v1.json`` is
vendored from the SDK's descriptor generator output. It keeps the data-pipeline
consumer honest about the values the SDK actually emits.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.models.technical_task_router import _normalize_serving_features_with_counts

FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / ("sdk_task_descriptor_contract_rows.v1.json")
)
SOURCE_SDK_COMMIT = "d5eaf4ce9d23a7d231fc631acbb27ebc97f93f88"


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _rows() -> list[dict[str, Any]]:
    return _fixture()["rows"]


def test_sdk_descriptor_fixture_records_numeric_hok2495_contract() -> None:
    fixture = _fixture()
    provenance = fixture["provenance"]
    rows = fixture["rows"]

    assert provenance["source_commit"] == SOURCE_SDK_COMMIT
    assert provenance["descriptor_generator"].endswith("deriveTaskDescriptor")
    assert len(provenance["reference_harness_fixture_sha256"]) == 64
    assert [row["case"] for row in rows] == ["shallow", "standard", "deep"]

    descriptor_shapes = []
    for row in rows:
        assert "complexity" not in row
        descriptor = row["task_descriptor"]
        assert isinstance(descriptor["complexity"], (int, float))
        assert not isinstance(descriptor["complexity"], bool)
        descriptor_shapes.append(
            {key: value for key, value in descriptor.items() if key != "complexity"}
        )

    assert [row["task_descriptor"]["complexity"] for row in rows] == [3, 5, 8]
    assert descriptor_shapes[0] == descriptor_shapes[1] == descriptor_shapes[2]


def test_sdk_reference_fixture_provenance_matches_local_checkout() -> None:
    fixture = _fixture()
    provenance = fixture["provenance"]
    sdk_fixture = (
        Path(__file__).resolve().parents[3].parent
        / "hokusai-sdk"
        / provenance["reference_harness_fixture"]
    )
    if not sdk_fixture.exists():
        pytest.skip("Sibling hokusai-sdk checkout is not available")

    digest = hashlib.sha256(sdk_fixture.read_bytes()).hexdigest()

    assert digest == provenance["reference_harness_fixture_sha256"]


def test_sdk_descriptor_rows_normalize_to_distinct_feature_vectors() -> None:
    normalized_by_case = {
        row["case"]: _normalize_serving_features_with_counts(row, emit_metrics=False)
        for row in _rows()
    }

    complexities = {
        case: normalized.features["complexity"] for case, normalized in normalized_by_case.items()
    }
    assert complexities == {"shallow": 3.0, "standard": 5.0, "deep": 8.0}
    assert len(set(complexities.values())) == 3

    for row in _rows():
        normalized = normalized_by_case[row["case"]]
        assert normalized.default_counts == {}
        assert normalized.features["language"] == "ts"
        assert normalized.features["task_type"] == "feature"
        assert normalized.features["repo_size_bucket"] == row["task_descriptor"]["repo_size_bucket"]
