"""HOK-2818 / HOK-3023: the shared leakage conformance cases, run through assembly's gates.

These use the real validator (``HOKUSAI_SCAN_CMD`` or ``hokusai-scan`` on PATH).
Without one they skip locally; CI sets ``HOKUSAI_REQUIRE_VALIDATOR=1``, which
turns a missing validator into a failure.

``tests/fixtures/arbiter/leakage-conformance.json`` is a copy of
``fixtures/arbiter/rework-risk/leakage-conformance.json`` in hokusai-sdk. With
``HOKUSAI_SDK_DIR`` set, the copy must match it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.arbiter.feature_audit import (
    ColumnLeakageError,
    ValidatorUnavailableError,
    audit_columns,
)
from src.arbiter.rework_dataset import (
    FEATURE_MANIFEST_VERSION,
    audit_feature_columns,
    audit_segment_columns,
)

CASES_FILE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "arbiter" / "leakage-conformance.json"
)
UPSTREAM = "fixtures/arbiter/rework-risk/leakage-conformance.json"
CASES = json.loads(CASES_FILE.read_text())["cases"]


@pytest.fixture(scope="module")
def validator() -> None:
    try:
        result = audit_columns(["feature.shape.loc_touched"])
    except ValidatorUnavailableError as error:
        if os.environ.get("HOKUSAI_REQUIRE_VALIDATOR") == "1":
            pytest.fail(f"Leakage validator required but unavailable: {error}")
        pytest.skip(f"Leakage validator unavailable: {error}")
    assert result.manifest_version == FEATURE_MANIFEST_VERSION


def test_vendored_cases_match_hokusai_sdk():
    sdk = os.environ.get("HOKUSAI_SDK_DIR")
    if not sdk:
        if os.environ.get("HOKUSAI_REQUIRE_VALIDATOR") == "1":
            pytest.fail("HOKUSAI_SDK_DIR must be set where the validator is required")
        pytest.skip("HOKUSAI_SDK_DIR not set")
    upstream = Path(sdk) / UPSTREAM
    assert json.loads(upstream.read_text()) == json.loads(CASES_FILE.read_text())


def test_cases_cover_both_outcomes():
    assert any(not c["expect_codes"] for c in CASES)
    assert any(c["expect_codes"] for c in CASES)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_conformance_case(validator, case):
    columns, allow_segments, expected = (
        case["columns"],
        case["allow_segments"],
        case["expect_codes"],
    )

    def gate() -> None:
        if allow_segments:
            audit_segment_columns(columns, allow_segments=True)
        else:
            audit_feature_columns(columns)

    if not expected:
        gate()
        return
    with pytest.raises(ColumnLeakageError) as caught:
        gate()
    assert caught.value.codes == sorted(set(expected))
