# Implementation Plan: HOK-1503 — Add Deterministic Custom Scorer Registry

## Overview

Create a new `src/evaluation/scorers/` package that provides a stable, in-process registry for deterministic business outcome scorers. Each scorer carries a content-derived SHA-256 source hash used by HEM provenance. A resolver is wired into `spec_translation.py` as an import/lookup point.

No DB changes, no API routes, no new pip dependencies.

---

## Phase 1: Define Metadata Types (`src/evaluation/scorers/metadata.py`)

Create `ScorerMetadata` as a frozen dataclass with:
- `scorer_ref: str` — stable lookup key (case-sensitive)
- `version: str`
- `input_schema: dict[str, Any]` — JSON Schema of expected inputs
- `output_metric_keys: tuple[str, ...]` — MLflow-safe keys (validated via `metric_naming`)
- `metric_family: MetricFamily` — `str` enum: `OUTCOME`, `QUALITY`, `COST`, `LATENCY`
- `aggregation: Aggregation` — `str` enum: `MEAN`, `SUM`, `PASS_RATE`, `WEIGHTED_MEAN`, `MIN`, `MAX`
- `source_hash: str` — 64-char lowercase hex SHA-256, computed externally and passed in
- `description: str | None`

Pattern: follow the `@dataclass(frozen=True)` style used in `spec_translation.py` and `manifest.py`. `MetricFamily` and `Aggregation` are `str` enums for JSON-serialization friendliness.

---

## Phase 2: Registry + Hash Logic (`src/evaluation/scorers/registry.py`)

### Error types
- `UnknownScorerError(KeyError)` — message: `f"Unknown scorer ref: {ref!r}"`
- `ScorerConflictError(ValueError)` — message: `f"Scorer ref {ref!r} already registered with different metadata"`

### `RegisteredScorer` — named tuple or small dataclass holding `(metadata, callable_)`.

### `compute_source_hash(...)` helper
Inputs: `scorer_ref`, `version`, `input_schema`, `output_metric_keys`, `metric_family`, `aggregation` + the callable's `inspect.getsource()` (fallback to `callable_.__qualname__`).

Canonicalization: serialize to a JSON string with `sort_keys=True, separators=(',', ':')` then SHA-256 hexdigest. Document this contract in the docstring.

**Note**: `description` is intentionally excluded from the hash (cosmetic field; same scorer, different description = idempotent).

### Module-level `_REGISTRY: dict[str, RegisteredScorer]`

### Public API
- `register_scorer(scorer_ref, *, callable_, version, input_schema, output_metric_keys, metric_family, aggregation, description=None)` → validates metric keys via `validate_mlflow_metric_key`, computes hash, upserts if identical, raises `ScorerConflictError` if different.
- `resolve_scorer(ref: str) -> RegisteredScorer` — O(1) dict lookup, raises `UnknownScorerError` on miss.
- `list_scorers() -> list[ScorerMetadata]` — sorted by `scorer_ref`.
- `clear_scorers()` — for test isolation (mirrors `clear_benchmark_adapters` pattern).

---

## Phase 3: Built-in Scorers (`src/evaluation/scorers/builtin.py`)

Register at module-import time. Ship: `mean`, `sum`, `pass_rate`, `min`, `max`. These are pure functions operating on `list[float]` inputs.

Metric keys for built-ins: `"mean"`, `"sum"`, `"pass_rate"`, `"min"`, `"max"` — all MLflow-safe.

Each scorer's `input_schema` will be a minimal JSON Schema: `{"type": "array", "items": {"type": "number"}}`.

`metric_family` = `MetricFamily.OUTCOME` for all built-ins (they measure outcomes generically).

---

## Phase 4: Public API (`src/evaluation/scorers/__init__.py`)

- Import `builtin` module to trigger registration side effects.
- Re-export: `resolve_scorer`, `list_scorers`, `register_scorer`, `clear_scorers`, `ScorerMetadata`, `MetricFamily`, `Aggregation`, `UnknownScorerError`, `ScorerConflictError`.
- Use same lazy-import pattern as `src/evaluation/__init__.py` for consistency (or direct imports since the package is new and small).

---

## Phase 5: Wire into `spec_translation.py`

Add a minimal wiring point:
- Import `resolve_scorer` from `src.evaluation.scorers` (lazy, inside a helper).
- Add helper `_resolve_scorer_for_translation(ref: str | None)` that calls `resolve_scorer(ref)` when `ref` is non-None, returns `None` otherwise.
- Do not refactor existing translation logic. The helper is available for adapters and the next issue to wire up.

---

## Phase 6: Tests (`tests/unit/test_scorer_registry.py`)

Cover:
1. `resolve_scorer("mean")` → correct metadata and valid 64-char hex hash
2. `resolve_scorer("does_not_exist")` → `UnknownScorerError`, message contains ref, `isinstance(KeyError)`
3. `resolve_scorer("")` → `UnknownScorerError`
4. `resolve_scorer(None)` → `TypeError` (type contract)
5. Hash stability: same inputs → same digest (two in-process calls)
6. Hash sensitivity: changing `version` changes digest
7. Idempotent re-registration: same metadata → no error
8. `ScorerConflictError` on conflicting re-registration
9. `list_scorers()` returns sorted list including all built-ins
10. `output_metric_keys` round-trip: all keys pass `validate_mlflow_metric_key`
11. `_resolve_scorer_for_translation(None)` returns `None`; with valid ref returns metadata

Use `clear_scorers()` in fixtures where custom test scorers are registered to avoid state leakage.

---

## File Checklist

| File | Action |
|------|--------|
| `src/evaluation/scorers/__init__.py` | Create |
| `src/evaluation/scorers/metadata.py` | Create |
| `src/evaluation/scorers/registry.py` | Create |
| `src/evaluation/scorers/builtin.py` | Create |
| `src/evaluation/spec_translation.py` | Minimal edit: add `_resolve_scorer_for_translation` helper |
| `tests/unit/test_scorer_registry.py` | Create |

---

## Release Readiness

- `database_change_risk`: none
- `env_changes`: none
- `config_changes`: none
- `manual_steps`: none
