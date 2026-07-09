"""Feature normalization for the Model 30 technical task router.

Complexity arrives from harnesses as a number or as one of several word
spellings. Any word the map does not recognize silently becomes 5.0, which
turns the feature into a constant — so the accepted vocabulary is pinned here.
"""

from __future__ import annotations

import pytest

from src.models.technical_task_router import _complexity_number, _normalize_language


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        # Reasoning-depth spellings emitted by the Hokusai SDK.
        ("shallow", 3.0),
        ("standard", 5.0),
        ("deep", 8.0),
        # The server's own aliases.
        ("low", 3.0),
        ("small", 3.0),
        ("medium", 5.0),
        ("moderate", 5.0),
        ("high", 8.0),
        ("large", 8.0),
        ("very_high", 10.0),
    ],
)
def test_complexity_words_map_to_distinct_scores(word: str, expected: float) -> None:
    assert _complexity_number(word) == expected


def test_reasoning_depth_words_are_not_all_the_default() -> None:
    # The regression this guards: before `shallow`/`standard`/`deep` were in the
    # map they all resolved to 5.0, erasing the signal the SDK computed.
    scores = {_complexity_number(w) for w in ("shallow", "standard", "deep")}
    assert len(scores) == 3


def test_complexity_passes_through_numbers() -> None:
    assert _complexity_number(7) == 7.0
    assert _complexity_number(7.5) == 7.5
    # Numeric strings are parsed too, matching the SDK's normalizeComplexity.
    assert _complexity_number("8") == 8.0
    assert _complexity_number("7.5") == 7.5


def test_complexity_defaults_for_unknown_values() -> None:
    assert _complexity_number("banana") == 5.0
    assert _complexity_number(None) == 5.0
    assert _complexity_number("") == 5.0


def test_normalize_language_is_case_insensitive() -> None:
    # The SDK once sent the display label "TypeScript"; both spellings land on
    # the same feature value, which is why the language mismatch was harmless.
    assert _normalize_language("TypeScript") == _normalize_language("typescript") == "ts"
    assert _normalize_language("Python") == "py"
    assert _normalize_language("go") == "go"
    assert _normalize_language(None) == "unknown"
