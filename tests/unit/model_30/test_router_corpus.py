"""HOK-3414: one corpus builder over canonical rows; history frozen into the store."""

from __future__ import annotations

import copy
import csv
import json
import math
import re
from pathlib import Path
from typing import Any

import pytest

from scripts.model_30 import build_router_corpus as builder
from scripts.model_30.collect_wavemill_router_corpus import eval_record_to_router_row
from scripts.model_30.convert_legacy_to_canonical import convert, write_freeze
from src.model_30 import canonical_row as cr
from src.model_30 import router_corpus as rc

REPO_ROOT = Path(__file__).resolve().parents[3]
V4 = json.loads(
    (REPO_ROOT / "tests/fixtures/contribution_v4/sdk_contribution_v4_fixtures.v1.json").read_text(
        encoding="utf-8"
    )
)["fixtures"]


def _eval_record(**overrides: Any) -> dict[str, Any]:
    record = {
        "id": "eval-1",
        "timestamp": "2026-06-15T00:00:00.000Z",
        "trainingEligible": True,
        "score": 0.95,
        "scoreBand": "Minor Feedback",
        "workflowCost": 2.5,
        "timeSeconds": 1200,
        "interventionCount": 0,
        "taskDescriptor": {
            "signals": {
                "heuristic": {"task_type": "feature", "languages": ["python"], "files_touched": 4},
                "learned": {"complexity": 4, "domain": "backend"},
            },
            "constraints": {
                "max_cost_usd": 25,
                "models_available": ["gpt-5.4", "claude-sonnet-4-6"],
            },
            "stages": {
                "planner": {"model": "claude-sonnet-4-6"},
                "coder": {"model": "gpt-5.4"},
                "reviewer": {"model": "claude-sonnet-4-6"},
            },
            "rubric": {"criterion_count": 5, "criteria_scores": {"correctness": 0.95}},
        },
        "routePrediction": {"expectedSuccess": 0.7, "riskScore": 9},
        "outcomes": {"success": True},
    }
    record.update(overrides)
    return record


def _legacy_row(**overrides: str) -> dict[str, str]:
    """A pre-May export row: no token columns, harness-recorded total."""
    row = {name: "" for name in rc.FIELDNAMES}
    row.update(
        schema_version=rc.ROUTER_DATASET_SCHEMA_VERSION,
        run_id_hash="78eceb3230aef4ba5e46bea3",
        task_id_hash="75c630c9bd2fcf73b2d559be",
        timestamp="2026-02-16T17:12:46.002Z",
        source_repo_hash="97b2a313ca3b5d8f04a693f4",
        is_challenge="false",
        task_type="migration",
        language="unknown",
        domain="fullstack",
        complexity="5",
        repo_size_bucket="small",
        files_touched_bucket="2_5",
        description_length_bucket="long",
        is_greenfield="false",
        is_migration="true",
        requires_tests="true",
        cross_service="false",
        ui_heavy="true",
        risk_level="high",
        available_planner_models='["claude-opus-4-6"]',
        available_coder_models='["claude-opus-4-6","claude-sonnet-4-6"]',
        available_reviewer_models='["claude-opus-4-6"]',
        planner_model="claude-opus-4-6",
        planner_agent="claude",
        coder_model="claude-sonnet-4-6",
        coder_agent="claude",
        reviewer_model="claude-opus-4-6",
        reviewer_agent="claude",
        plan_depth="medium",
        completed_successfully="true",
        score="0.92",
        score_band="Minor Feedback",
        actual_cost_usd="12.512422",
        intervention_count="1",
        budget_violation="false",
    )
    row.update(overrides)
    return row


def _same(left: str, right: str) -> bool:
    if left == right:
        return True
    try:
        return math.isclose(float(left), float(right), rel_tol=1e-12)
    except ValueError:
        return json.loads(left) == json.loads(right)


def _round_trip(row: dict[str, str]) -> dict[str, str]:
    record = rc.router_row_to_canonical(
        row, freeze_id="f1", row_index=0, origin="test", price_source="test"
    )
    json.dumps(record)  # canonical rows are plain JSON
    return rc.canonical_to_router_row(record)


@pytest.mark.parametrize(
    "row",
    [
        _legacy_row(),
        _legacy_row(
            is_challenge="true", challenge_pair_hash="abc123", cost_status="", actual_cost_usd=""
        ),
    ],
)
def test_legacy_router_row_round_trips_through_the_canonical_row(row: dict[str, str]) -> None:
    out = _round_trip(row)
    assert list(out) == rc.FIELDNAMES
    assert {c: (row[c], out[c]) for c in rc.FIELDNAMES if not _same(row[c], out[c])} == {}


def test_derived_eval_row_round_trips_with_token_economics() -> None:
    row, reason = eval_record_to_router_row(_eval_record(), source_repo="repo-a")
    assert reason is None and row is not None
    row.update(
        run_id_hash="run1",
        cost_status="recovered:codex_sessions",
        coder_input_tokens="61",
        coder_cache_tokens="8282517",
        coder_output_tokens="41010",
        coder_cost_usd="6.205162",
        aux_cost_usd="0",
    )
    out = _round_trip(row)
    assert {c: (row[c], out[c]) for c in rc.FIELDNAMES if not _same(row[c], out[c])} == {}


@pytest.mark.parametrize(
    ("router_status", "cost", "expected"),
    [
        ("recorded", 1.0, cr.COST_PRICED),
        ("repriced", 1.0, cr.COST_PRICED),
        ("recovered:codex_sessions+execution_economics", 1.0, cr.COST_PRICED),
        ("", 12.5, cr.COST_RECORDED_TOTAL),
        ("", None, cr.COST_NO_TOKEN_EVIDENCE),
        ("untrusted:openai_cached_input_double_counted", None, cr.COST_NO_TOKEN_EVIDENCE),
        ("no_token_usage", None, cr.COST_NO_TOKEN_EVIDENCE),
        ("unpriced_model", None, cr.COST_UNPRICED_MODEL),
    ],
)
def test_legacy_cost_status_maps_onto_the_canonical_vocabulary(
    router_status: str, cost: float | None, expected: str
) -> None:
    assert rc.legacy_cost_status(router_status, cost) == expected


def _contribution(name: str, **overrides: Any) -> dict[str, Any]:
    row = copy.deepcopy(V4[name])
    kwargs: dict[str, Any] = {
        "submission_id": "sub-1",
        "row_index": 0,
        "fidelity_tier": "training_eligible",
        "routing_join": None,
        "contributor_id": "user-1",
    }
    kwargs.update(overrides)
    return cr.build_canonical_row(row, **kwargs)


def test_v4_contribution_becomes_a_router_row_with_its_repriced_cost() -> None:
    record = _contribution("singleHarness")
    out = rc.canonical_to_router_row(record)
    assert out["actual_cost_usd"] == rc.format_number(record["cost_usd"])
    assert out["cost_status"] == cr.COST_PRICED
    assert out["coder_model"] == "claude-sonnet-5"
    assert out["coder_agent"] == "claude"
    coder_tokens = record["roles"]["coder"]["tokens"]
    assert (
        float(out["coder_cache_tokens"]) == coder_tokens["cache_read"] + coder_tokens["cache_write"]
    )
    assert out["under_budget"] == "true" and out["budget_violation"] == "false"
    assert out["score"] == "1"  # no quality score: derived from success
    assert out["max_cost_usd"] == "5"
    assert out["actual_time_seconds"] == "1840"
    assert out["executed_route_source"] == "stage_executions"
    assert out["is_challenge"] == "false"
    assert all(re.fullmatch(r"[0-9a-f]{16}", out[c]) for c in ("run_id_hash", "task_id_hash"))
    assert out["source_repo_hash"] == rc.stable_hash("user-1")


def test_comparison_group_marks_the_challenge_pair() -> None:
    primary = rc.canonical_to_router_row(_contribution("challengePrimary"))
    challenger = rc.canonical_to_router_row(_contribution("challengeChallenger", row_index=1))
    assert primary["is_challenge"] == challenger["is_challenge"] == "true"
    assert primary["challenge_pair_hash"] == challenger["challenge_pair_hash"] != ""
    assert primary["run_id_hash"] != challenger["run_id_hash"]


def test_untrusted_cost_trains_success_but_no_cost_labels() -> None:
    out = rc.canonical_to_router_row(_contribution("challengeChallenger"))  # gpt-5-codex unpriced
    assert out["cost_status"] == cr.COST_UNPRICED_MODEL
    assert out["completed_successfully"] in {"true", "false"}
    for column in ("actual_cost_usd", "under_budget", "budget_violation", "coder_cost_usd"):
        assert out[column] == ""


def test_narrower_trust_drops_recorded_totals() -> None:
    record = rc.router_row_to_canonical(
        _legacy_row(), freeze_id="f1", row_index=0, origin="t", price_source="t"
    )
    assert rc.canonical_to_router_row(record)["actual_cost_usd"] == "12.512422"
    tokens_only = rc.canonical_to_router_row(record, trusted_cost_statuses={cr.COST_PRICED})
    assert tokens_only["actual_cost_usd"] == ""
    assert tokens_only["completed_successfully"] == "true"


# --- converter + builder -------------------------------------------------------


def _write_snapshot(root: Path) -> None:
    evals = root / "repo-a" / ".wavemill" / "evals" / "evals.jsonl"
    evals.parent.mkdir(parents=True)
    evals.write_text(
        "".join(
            json.dumps(_eval_record(id=f"eval-{i}", timestamp=f"2026-06-1{i}T00:00:00.000Z")) + "\n"
            for i in range(3)
        ),
        encoding="utf-8",
    )


def _write_legacy_csv(path: Path) -> None:
    legacy_columns = rc.FIELDNAMES[: rc.FIELDNAMES.index("rubric_provenance") + 1]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=legacy_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(_legacy_row())
        # An OpenAI route: the export double-counted cached input, so cost is quarantined.
        writer.writerow(
            _legacy_row(
                run_id_hash="openai-run",
                timestamp="2026-03-01T00:00:00.000Z",
                coder_model="gpt-5.3-codex",
                coder_agent="codex",
                score="0.5",
            )
        )


def _freeze(tmp_path: Path) -> Path:
    _write_snapshot(tmp_path / "snapshot")
    _write_legacy_csv(tmp_path / "legacy.csv")
    rows, manifest = convert(
        search_roots=[tmp_path / "snapshot"],
        legacy_csv=tmp_path / "legacy.csv",
        recovered_usage=None,
        freeze_id="wavemill-test",
    )
    out = tmp_path / "store" / "legacy" / "wavemill-test"
    write_freeze(out, rows, manifest)
    return out


def test_converter_freezes_history_with_provenance(tmp_path: Path) -> None:
    out = _freeze(tmp_path)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
    assert manifest["rows"] == len(rows) == 5
    assert manifest["by_origin"] == {"legacy:legacy.csv": 2, "derived:evals.jsonl": 3}
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["inputs"]["eval_snapshot_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["rows_sha256"])
    assert [r["canonical_row_id"] for r in rows] == [f"legacy/wavemill-test:{i}" for i in range(5)]
    assert [r["observed_at"] for r in rows] == sorted(r["observed_at"] for r in rows)
    openai = next(r for r in rows if r["router_ids"]["run_id_hash"] == "openai-run")
    assert openai["cost_usd"] is None
    assert openai["cost_status"] == cr.COST_NO_TOKEN_EVIDENCE
    assert openai["success"] is False  # placeholder label re-derived from score 0.5
    assert {r["source"]["kind"] for r in rows} == {rc.LEGACY_SOURCE_KIND}


def test_builder_trains_from_the_store_alone(tmp_path: Path) -> None:
    freeze = _freeze(tmp_path)
    store = freeze.parents[1]
    contribution = _contribution("singleHarness")
    (store / "sub-1.jsonl").write_text(json.dumps(contribution) + "\n", encoding="utf-8")

    records = builder.select_rows(builder.read_canonical_rows([str(store)]))
    assert [builder.source_kind(r) for r in records].count("contribution") == 1
    report = builder.build_corpus(
        records,
        output=tmp_path / "corpus.csv",
        raw_output=tmp_path / "corpus.raw.csv",
        prices_output=tmp_path / "prices.json",
    )
    rows = list(csv.DictReader((tmp_path / "corpus.csv").open(encoding="utf-8")))
    assert report["output_rows"] == len(rows) == 6
    assert report["by_source"] == {"legacy_freeze": 5, "contribution": 1}
    assert report["clean_report"]["validation"]  # the trainer's model-id validation ran
    prices = json.loads((tmp_path / "prices.json").read_text(encoding="utf-8"))
    assert "claude-sonnet-5" in prices["prices"]
    assert prices["price_table_version"].startswith("model_30_token_prices/")


def test_builder_filters_by_date_source_and_contributor(tmp_path: Path) -> None:
    freeze = _freeze(tmp_path)
    records = builder.read_canonical_rows([str(freeze)])
    records.append(_contribution("singleHarness"))
    june = builder.select_rows(records, start="2026-06-01", end="2026-07-01")
    assert len(june) == 3
    assert builder.select_rows(records, sources={"contribution"}) == [records[-1]]
    assert builder.select_rows(records, contributors={"user-1"}) == [records[-1]]


def test_builder_refuses_rows_that_are_not_canonical(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"schema_version": "technical_task_router_row/v4"}) + "\n")
    with pytest.raises(ValueError, match="not a model_30_canonical_row/v1 row"):
        builder.read_canonical_rows([str(bad)])


def test_only_the_legacy_converter_reads_eval_records() -> None:
    """Training entry points never parse Wavemill eval records again."""
    readers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "scripts").rglob("*.py")
        if "collect_wavemill_router_corpus" in path.read_text(encoding="utf-8")
        and path.name != "collect_wavemill_router_corpus.py"
    )
    assert readers == ["scripts/model_30/convert_legacy_to_canonical.py"]
    collector = (REPO_ROOT / "scripts/model_30/collect_wavemill_router_corpus.py").read_text()
    for retired in ("def main(", "discover_router_csv_exports", "clean_router_datasets"):
        assert retired not in collector
    assert not (REPO_ROOT / "scripts/model_30/merge_legacy_router_export.py").exists()
