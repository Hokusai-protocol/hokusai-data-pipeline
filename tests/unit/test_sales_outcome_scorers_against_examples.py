"""Integration tests running registered sales scorers against schema example rows.

Each valid sales_outcome_row/v1 example is loaded from disk and fed directly to
the resolved scorer without any field adaptation, verifying that canonical row
shapes are consumed correctly end-to-end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.evaluation.scorers.builtin  # noqa: F401  — register scorers as side effect
from src.evaluation.scorers.registry import resolve_scorer

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "schema" / "examples"
BUILTIN_PATH = Path(__file__).resolve().parents[2] / "src" / "evaluation" / "scorers" / "builtin.py"


def _load_example(filename: str) -> dict:
    return json.loads((EXAMPLES_DIR / filename).read_text())


# ---------------------------------------------------------------------------
# Example-driven scorer tests
# ---------------------------------------------------------------------------


class TestScorerAgainstExamples:
    def test_qualified_meeting_example_returns_one(self) -> None:
        """qualified_meeting=true → rate of 1.0 over a single row."""
        row = _load_example("sales_outcome_row.qualified_meeting.v1.json")
        scorer = resolve_scorer(row["scorer_ref"])
        result = scorer.callable_([row])
        assert result == pytest.approx(1.0)

    def test_revenue_example_returns_expected_usd_per_1000(self) -> None:
        """revenue_amount_cents=125000, delivered_count=1 → 125000/100/1*1000 = 1250000.0 USD/1k."""
        row = _load_example("sales_outcome_row.revenue.v1.json")
        assert row["revenue_amount_cents"] == 125000
        assert row["delivered_count"] == 1
        scorer = resolve_scorer(row["scorer_ref"])
        result = scorer.callable_([row])
        assert result == pytest.approx(1250000.0)

    def test_spam_complaint_example_returns_zero(self) -> None:
        """spam_complaint=false, delivered_count=1 → rate of 0.0."""
        row = _load_example("sales_outcome_row.spam_complaint.v1.json")
        scorer = resolve_scorer(row["scorer_ref"])
        result = scorer.callable_([row])
        assert result == pytest.approx(0.0)

    def test_unsubscribe_example_returns_one(self) -> None:
        """unsubscribe=true, delivered_count=1 → rate of 1.0."""
        row = _load_example("sales_outcome_row.unsubscribe.v1.json")
        scorer = resolve_scorer(row["scorer_ref"])
        result = scorer.callable_([row])
        assert result == pytest.approx(1.0)

    def test_scorer_ref_resolves_for_all_valid_examples(self) -> None:
        """Every valid example's scorer_ref resolves in the registry without error."""
        valid_files = [
            "sales_outcome_row.qualified_meeting.v1.json",
            "sales_outcome_row.revenue.v1.json",
            "sales_outcome_row.spam_complaint.v1.json",
            "sales_outcome_row.unsubscribe.v1.json",
        ]
        for filename in valid_files:
            row = _load_example(filename)
            scorer = resolve_scorer(row["scorer_ref"])
            assert (
                scorer is not None
            ), f"{filename}: scorer_ref {row['scorer_ref']!r} did not resolve"

    def test_revenue_denominator_is_delivered_count_not_per_1000_scale(self) -> None:
        """Revenue example denominator field equals delivered_count (raw contribution), not 1000."""
        row = _load_example("sales_outcome_row.revenue.v1.json")
        assert row["denominator"] == row["delivered_count"], (
            "Revenue example denominator should equal delivered_count (the raw eligible "
            "observation count), not the per-1000 scaling factor"
        )


# ---------------------------------------------------------------------------
# Regression: no deprecated field aliases in scorer source
# ---------------------------------------------------------------------------


class TestNoDeprecatedFieldAliases:
    def test_no_delivered_alias_in_builtin(self) -> None:
        """The old 'delivered' field alias must not appear as a dict key lookup in builtin.py."""
        src = BUILTIN_PATH.read_text()
        assert '"delivered"' not in src, (
            'Deprecated field alias "delivered" found in builtin.py; '
            "use delivered_count from sales_outcome_row/v1"
        )

    def test_no_revenue_alias_in_builtin(self) -> None:
        """The old 'revenue' field alias must not appear as a dict key lookup in builtin.py."""
        src = BUILTIN_PATH.read_text()
        assert '"revenue"' not in src, (
            'Deprecated field alias "revenue" found in builtin.py; '
            "use revenue_amount_cents from sales_outcome_row/v1"
        )
