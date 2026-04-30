## 1. Objective

### What
Add a deterministic custom-scorer registry at `src/evaluation/scorers/` that defines scorer metadata (`scorer_ref`, source hash, input schema, output metric keys, `metric_family`, aggregation semantics) and a resolver consumable by evaluation adapters and `src/evaluation/spec_translation.py`.

### Why
HOK-1500/1501/1502 introduced `BenchmarkSpec.eval_spec`, `spec_translation.py`, and unified custom-metric naming across MLflow/HEM/DeltaOne. Those pieces describe *what* metrics to emit but not *how* to compute deterministic outcome aggregations from raw eval rows. The registry closes that gap: it gives spec translation and adapters a single, content-addressed lookup point so HEM payloads can carry a verifiable `source_hash` for each business-outcome metric, separate from LLM-as-judge diagnostics in `src/evaluation/judges/`.

### Scope In
- New package `src/evaluation/scorers/` with `__init__.py`, `base.py`, `registry.py`, `builtin.py`.
- `ScorerMetadata` dataclass: `scorer_ref`, `source_hash`, `input_schema`, `output_metric_keys`, `metric_family`, `aggregation` (semantics descriptor), `version`.
- `Scorer` protocol/ABC: `metadata: ScorerMetadata`, `compute(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, float]`.
- `register_scorer` decorator and module-level `_REGISTRY` dict.
- `resolve_scorer(ref: str) -> Scorer` and `list_scorers() -> list[ScorerMetadata]` public API.
- `UnknownScorerError` typed exception.
- Source-hash helper that hashes the scorer class source (via `inspect.getsource`) plus its declared metadata, SHA-256 hex.
- 2–3 built-in deterministic scorers in `builtin.py` to prove the abstraction (e.g., `mean_outcome`, `pass_rate`, `sum_outcome`); registered at import time.
- Unit tests at `tests/unit/test_scorer_registry.py` covering: registration, resolution, source-hash stability, unknown/missing refs, duplicate registration rejection, basic compute() correctness on a small fixture.

### Scope Out
- Wiring the registry into `spec_translation.py` or adapter call sites (separate ticket).
- Persisting source hashes to the DB or HEM payload (separate ticket — this only exposes the hash).
- LLM-as-judge scorers — `src/evaluation/judges/` is explicitly untouched.
- API/CLI surface for registering external scorers at runtime.
- Plugin discovery via entry points or filesystem scanning.
- Migrations or schema changes.
- Docker, infrastructure, or deployment changes.
- Documentation site updates beyond an in-repo module docstring.

---

## 2. Technical Context

### Repository
`hokusai-data-pipeline` only. No cross-repo changes.

### Key Files

**New:**
- `src/evaluation/scorers/__init__.py` — re-exports `register_scorer`, `resolve_scorer`, `list_scorers`, `ScorerMetadata`, `Scorer`, `UnknownScorerError`.
- `src/evaluation/scorers/base.py` — `ScorerMetadata` dataclass, `Scorer` protocol, `UnknownScorerError`, source-hash helper.
- `src/evaluation/scorers/registry.py` — `_REGISTRY`, `register_scorer`, `resolve_scorer`, `list_scorers`.
- `src/evaluation/scorers/builtin.py` — built-in scorer implementations, registered via decorator at import time.
- `tests/unit/test_scorer_registry.py` — unit tests.

**Read-only references (do not modify in this task):**
- `src/evaluation/spec_translation.py` (HOK-1501) — future caller; understand its expected shape.
- `src/evaluation/manifest.py`, `src/evaluation/schema.py` (HOK-1502) — `metric_family` vocabulary and naming conventions.
- `src/utils/metric_naming.py` (HOK-1502) — for `output_metric_keys` formatting consistency.
- `src/evaluation/judges/` — boundary partner; confirm no overlap.

### Relevant Subsystem Specs

⚠️ **Knowledge Gap**: No subsystem specs were provided in `.wavemill/context/` for the evaluation subsystem. After implementation, consider running `wavemill context init --force` to create a subsystem spec for `src/evaluation/` capturing the scorer/judge boundary, the `metric_family` vocabulary, and the source-hash provenance contract — this enables persistent downstream acceleration for HOK-1504+.

### Dependencies
- Builds on **HOK-1500** (`eval_spec` JSONB column), **HOK-1501** (`spec_translation.py`), **HOK-1502** (custom metric name normalization). All merged on `main`.
- No new third-party packages — uses stdlib `dataclasses`, `hashlib`, `inspect`, `typing`.
- Runtime Python ≥ 3.10 (matches existing `src/evaluation/` modules).

### Architecture Notes
- Mirror the lightweight registry style already implicit in `src/evaluation/` (module-level dicts, decorator registration). Avoid pulling in heavyweight DI frameworks.
- Use `metric_family` values consistent with those introduced in HOK-1502 (`src/evaluation/schema.py`); read that file to enumerate the allowed set rather than re-defining it locally.
- `output_metric_keys` strings should be in the canonical custom-metric-name shape produced by `src/utils/metric_naming.py` so downstream HEM/DeltaOne emission is a passthrough.
- Aggregation semantics: a small string enum (`"mean"`, `"sum"`, `"rate"`, `"count"`, `"custom"`) is sufficient. Free-text or callable indirection is out of scope.
- Source hash is computed once at registration time and cached on `ScorerMetadata.source_hash`. It hashes `inspect.getsource(scorer_cls)` concatenated with a stable JSON encoding of the static metadata fields. Bytes → SHA-256 → hex digest.

---

## 3. Implementation Approach

1. **Read existing context** — open `src/evaluation/spec_translation.py`, `src/evaluation/manifest.py`, `src/evaluation/schema.py`, and `src/utils/metric_naming.py` to confirm: the `metric_family` vocabulary, the canonical metric-name shape, and what shape future callers (spec_translation) will pass to `resolve_scorer`. Confirm `src/evaluation/judges/` exists and that no naming collides.

2. **Create `src/evaluation/scorers/base.py`** —
   - `class UnknownScorerError(KeyError)` with a custom `__init__(ref: str)` storing the ref.
   - `@dataclass(frozen=True) class ScorerMetadata` with fields: `scorer_ref: str`, `source_hash: str`, `input_schema: Mapping[str, str]`, `output_metric_keys: tuple[str, ...]`, `metric_family: str`, `aggregation: Literal["mean", "sum", "rate", "count", "custom"]`, `version: str = "1"`.
   - `class Scorer(Protocol)` with `metadata: ScorerMetadata` attribute and `def compute(self, rows: Sequence[Mapping[str, Any]]) -> Mapping[str, float]`.
   - `def compute_source_hash(cls: type, static_meta: Mapping[str, Any]) -> str` — `hashlib.sha256(inspect.getsource(cls).encode("utf-8") + json.dumps(static_meta, sort_keys=True, default=str).encode("utf-8")).hexdigest()`.

3. **Create `src/evaluation/scorers/registry.py`** —
   - Module-level `_REGISTRY: dict[str, Scorer] = {}`.
   - `def register_scorer(*, scorer_ref: str, input_schema, output_metric_keys, metric_family, aggregation, version="1")` — class decorator. Builds `ScorerMetadata` (computes `source_hash` via `compute_source_hash`), instantiates the class, stores in `_REGISTRY[scorer_ref]`. Raises `ValueError` on duplicate `scorer_ref`.
   - `def resolve_scorer(ref: str) -> Scorer` — returns `_REGISTRY[ref]` or raises `UnknownScorerError(ref)`.
   - `def list_scorers() -> list[ScorerMetadata]` — returns `[s.metadata for s in _REGISTRY.values()]`, sorted by `scorer_ref` for deterministic output.

4. **Create `src/evaluation/scorers/builtin.py`** —
   - Three deterministic scorers, each a class decorated with `@register_scorer(...)`:
     - `MeanOutcomeScorer` (`scorer_ref="builtin.mean_outcome"`, aggregation `"mean"`).
     - `PassRateScorer` (`scorer_ref="builtin.pass_rate"`, aggregation `"rate"`, expects boolean `passed` field).
     - `SumOutcomeScorer` (`scorer_ref="builtin.sum_outcome"`, aggregation `"sum"`).
   - Each implements `compute(rows)`. Use `output_metric_keys` consistent with `src/utils/metric_naming.py` conventions.
   - No external imports beyond stdlib and `src.evaluation.scorers.registry`/`base`.

5. **Create `src/evaluation/scorers/__init__.py`** —
   - Import `builtin` for its registration side effects.
   - Re-export the public API.

6. **Create `tests/unit/test_scorer_registry.py`** — see Section 6 for the exact scenarios.

7. **Run lint + tests** — `ruff check src/evaluation/scorers tests/unit/test_scorer_registry.py` and `pytest tests/unit/test_scorer_registry.py -v`.

8. **Open PR** with title `feat: add deterministic custom scorer registry (HOK-1503)`, body referencing the issue, and confirming `src/evaluation/judges/` is unchanged.

---

## 4. Success Criteria

### Functional Requirements

- [ ] **[REQ-F1]** `resolve_scorer("builtin.mean_outcome")` returns a `Scorer` whose `metadata.scorer_ref == "builtin.mean_outcome"`, `metadata.aggregation == "mean"`, and `metadata.source_hash` is a 64-char lowercase hex SHA-256 string.
- [ ] **[REQ-F2]** `resolve_scorer("does.not.exist")` raises `UnknownScorerError` whose `args[0]` contains the string `"does.not.exist"`.
- [ ] **[REQ-F3]** Two separate calls to `resolve_scorer("builtin.mean_outcome")` in the same process return objects with identical `metadata.source_hash`. Re-importing the module in a fresh process produces the same hash (verified by hashing the same inputs in the test).
- [ ] **[REQ-F4]** Registering two scorers with the same `scorer_ref` raises `ValueError` containing the conflicting ref.
- [ ] **[REQ-F5]** `list_scorers()` returns `ScorerMetadata` for all built-in scorers, sorted by `scorer_ref`. Length ≥ 3.
- [ ] **[REQ-F6]** `MeanOutcomeScorer.compute([{"value": 1.0}, {"value": 3.0}])` returns a mapping whose value for the canonical metric key is `2.0` (within 1e-9). Empty input returns `0.0` or raises a documented `ValueError` — pick one and test it.
- [ ] **[REQ-F7]** `metadata.metric_family` of every built-in scorer is a value already present in `src/evaluation/schema.py`'s `metric_family` vocabulary (verified by importing the constant rather than hard-coding strings in tests).

### Non-Functional Requirements
- [ ] No new third-party dependencies added to `pyproject.toml`.
- [ ] No imports from `src/evaluation/judges/` in `src/evaluation/scorers/`, and vice versa (verified by grep in the test file or a static check).
- [ ] Importing `src.evaluation.scorers` has no I/O side effects (no file/network/DB access at import time).

### Code Quality
- [ ] Follows existing patterns in `src/evaluation/` (module-level registries, dataclasses, type hints).
- [ ] Type hints present on all public functions; no bare `Any` returns from public API.
- [ ] No lint errors (`ruff check`).

---

## 5. Implementation Constraints

- **Code style**: Match the rest of `src/evaluation/`. Use `from __future__ import annotations` if the surrounding modules do. Line length per repo `pyproject.toml`. Use `ruff` for linting.
- **Determinism**: No `random`, no `time`, no `uuid`, no I/O inside `compute()` or at import. Source hash must be stable across processes — only hash source code and static metadata, never object ids or memory addresses.
- **Boundary**: Do NOT import from `src/evaluation/judges/`. Do NOT modify any file under `src/evaluation/judges/`. Do NOT add LLM client calls anywhere in this package.
- **Testing**: Tests live under `tests/unit/`. Use `pytest`, no network or DB fixtures. Do not use mocks for the registry itself — exercise the real module.
- **Security**: No `eval`/`exec`. `inspect.getsource` is the only reflection used and only on classes registered in this package's source tree.
- **Performance**: Registry resolution is O(1) dict lookup. Source hashing happens once per class at registration (import time); do not re-hash on every `resolve_scorer` call.
- **Backwards compatibility**: This is a new package — nothing to be backwards-compatible with. Public API surface is the contract going forward; mark internal helpers with leading underscore.
- **Dependency direction**: `src/evaluation/scorers/` may import from `src/utils/metric_naming.py` and `src/evaluation/schema.py` (read-only). Nothing else under `src/evaluation/` should import from `scorers/` *in this PR* — wiring is a separate ticket.

---

## 6. Validation Steps

### Functional Requirement Validation

**[REQ-F1] Resolve a registered scorer and inspect metadata**

1. Setup: `from src.evaluation.scorers import resolve_scorer`.
2. Action: `s = resolve_scorer("builtin.mean_outcome")`.
3. Expected result: `s.metadata.scorer_ref == "builtin.mean_outcome"`, `s.metadata.aggregation == "mean"`, `len(s.metadata.source_hash) == 64`, `int(s.metadata.source_hash, 16)` does not raise.
4. Edge cases:
   - Whitespace in ref (`"builtin.mean_outcome "`) → raises `UnknownScorerError` (no implicit trimming).
   - Empty string ref (`""`) → raises `UnknownScorerError`.

**[REQ-F2] Unknown ref raises typed exception**

1. Setup: import `resolve_scorer`, `UnknownScorerError`.
2. Action: `resolve_scorer("does.not.exist")` inside `pytest.raises(UnknownScorerError) as exc`.
3. Expected result: `"does.not.exist"` appears in `str(exc.value)`. `UnknownScorerError` is a subclass of `KeyError` (so existing `except KeyError` callers still work).
4. Edge cases:
   - `None` passed as ref → `TypeError` from dict lookup is acceptable; document in test.
   - Case-sensitive: `"BUILTIN.mean_outcome"` → `UnknownScorerError` (refs are case-sensitive by design).

**[REQ-F3] Source hash is deterministic**

1. Setup: capture `h1 = resolve_scorer("builtin.mean_outcome").metadata.source_hash`.
2. Action: in the same test, recompute `h2 = resolve_scorer("builtin.mean_outcome").metadata.source_hash`; also independently call the helper `compute_source_hash(MeanOutcomeScorer, static_meta_dict)` and assert it matches.
3. Expected result: `h1 == h2 == h_independent`.
4. Edge cases:
   - Two scorers with identical metadata but different class bodies → distinct hashes.
   - Same class body with a different `version` field in metadata → distinct hashes.

**[REQ-F4] Duplicate registration fails loudly**

1. Setup: import `register_scorer`.
2. Action: define a dummy class and decorate it twice with `@register_scorer(scorer_ref="builtin.mean_outcome", ...)`.
3. Expected result: `ValueError` raised on the second decoration; original entry in `_REGISTRY` is unchanged.
4. Edge cases:
   - Re-registering after removing from registry (not supported in this ticket — registry has no `unregister`) → confirm there's no public unregister API.

**[REQ-F5] `list_scorers` returns built-ins, sorted**

1. Setup: `from src.evaluation.scorers import list_scorers`.
2. Action: `metas = list_scorers()`.
3. Expected result: `len(metas) >= 3`; refs are sorted ascending; every entry is a `ScorerMetadata` instance.
4. Edge cases:
   - Calling `list_scorers()` twice returns equal lists (no mutation).

**[REQ-F6] `compute()` correctness**

1. Setup: `s = resolve_scorer("builtin.mean_outcome")`.
2. Action: `out = s.compute([{"value": 1.0}, {"value": 3.0}])`.
3. Expected result: `out[s.metadata.output_metric_keys[0]] == pytest.approx(2.0)`.
4. Edge cases:
   - Empty input `[]` → either returns `{key: 0.0}` or raises `ValueError("empty rows")`. Pick one in implementation, assert exactly that in the test.
   - Missing `value` key in a row → `KeyError` (no silent skip).
   - Same test for `PassRateScorer.compute([{"passed": True}, {"passed": False}, {"passed": True}])` → rate of `2/3`.

**[REQ-F7] `metric_family` is from the canonical vocabulary**

1. Setup: import the `metric_family` enum/constant from `src/evaluation/schema.py`.
2. Action: for each `m in list_scorers()`, assert `m.metric_family` is in the canonical set.
3. Expected result: all built-ins use a recognized family.
4. Edge cases:
   - If `schema.py` exposes the vocabulary as an `Enum`, compare via `.value`; if as a `frozenset`/`tuple`, use `in`.

### Input/Output Verification

**Valid Inputs:**
- `resolve_scorer("builtin.mean_outcome")` → `MeanOutcomeScorer` instance.
- `resolve_scorer("builtin.pass_rate")` → `PassRateScorer` instance.
- `MeanOutcomeScorer().compute([{"value": 5.0}])` → `{<key>: 5.0}`.

**Invalid Inputs:**
- `resolve_scorer("nope")` → `UnknownScorerError("nope")`.
- `register_scorer(scorer_ref="builtin.mean_outcome", ...)` on a fresh class after import → `ValueError` mentioning `builtin.mean_outcome`.
- `MeanOutcomeScorer().compute([{"wrong_key": 1.0}])` → `KeyError("value")`.

### Standard Validation Commands

```bash
# 1. Lint passes
ruff check src/evaluation/scorers tests/unit/test_scorer_registry.py
# Expected: no errors

# 2. Type check (if mypy is configured for this path; otherwise skip)
# mypy src/evaluation/scorers
# Expected: no type errors

# 3. Targeted tests pass
pytest tests/unit/test_scorer_registry.py -v
# Expected: all tests pass

# 4. Full unit-test suite still passes (no regressions to neighbors)
pytest tests/unit -q
# Expected: all tests pass; no new failures vs. main

# 5. Boundary check (no leakage between scorers/ and judges/)
grep -R "evaluation.judges" src/evaluation/scorers/ && echo "VIOLATION" || echo "ok"
grep -R "evaluation.scorers" src/evaluation/judges/ && echo "VIOLATION" || echo "ok"
# Expected: both print "ok"
```

### Manual Verification Checklist

- [ ] `python -c "from src.evaluation.scorers import list_scorers; [print(m.scorer_ref, m.source_hash) for m in list_scorers()]"` prints ≥ 3 entries with 64-char hex hashes.
- [ ] Running the same one-liner in two separate Python invocations produces identical `source_hash` values for the same `scorer_ref`.
- [ ] `git diff --stat src/evaluation/judges/` shows zero changes.
- [ ] `pyproject.toml` has no new dependencies.

---

## 8. Definition of Done

- [ ] All [REQ-F1]–[REQ-F7] criteria met and covered by tests in `tests/unit/test_scorer_registry.py`.
- [ ] Validation commands in Section 6 all pass locally.
- [ ] `src/evaluation/judges/` is byte-identical to `main`.
- [ ] No new third-party dependencies in `pyproject.toml`.
- [ ] Commit message includes `HOK-1503`.
- [ ] PR opened against `main` with description summarizing the scorer/judge boundary, the source-hash provenance contract, and an explicit "no caller changes" note (wiring is a follow-up ticket).

---

## 9. Rollback Plan

- Revert PR via `git revert <merge-sha>` — safe, since no callers depend on the new package yet.
- No database migration to undo.
- No environment variables, infra, or deployed services touched.
- No feature flag needed: package is dead code until a follow-up wires it into `spec_translation.py` and adapters.

---

## 10. Release Readiness

- **database_change_risk**: none
- **env_changes**: none
- **config_changes**: none
- **manual_steps**: none

---

## 11. Proposed Labels

**Risk Level** (Required):

**Selected**: `Risk: Low`

**Justification**: Low — additive new package with no callers wired in this PR; pure stdlib, no schema or infra changes, fully reversible by `git revert`.

---

**Files to Modify** (Auto-detected):

- `src/evaluation/scorers/__init__.py`
- `src/evaluation/scorers/base.py`
- `src/evaluation/scorers/registry.py`
- `src/evaluation/scorers/builtin.py`
- `tests/unit/test_scorer_registry.py`

**Label**: `Files: scorers/__init__.py, scorers/base.py, scorers/registry.py, scorers/builtin.py, test_scorer_registry.py`

**Purpose**: Prevents parallel tasks from modifying the same files.

---

**Architectural Layer** (Recommended):

**Selected**: `Layer: Service`

**Purpose**: Pure backend service-layer code under `src/evaluation/`; no API routes, DB schema, or UI. Can run in parallel with UI/API/Database tasks.

---

**Area** (Recommended):

**Selected**: `Area: Evaluation`

**Purpose**: Avoid running 2+ tasks affecting the evaluation subsystem at once (e.g., HOK-1500/1501/1502 successors).

---

**Test Coverage** (Auto-detected):

**Selected**: `Tests: Unit`

**Purpose**: Unit-only; can run in parallel with other unit-test tasks. No integration or E2E exposure required.

---

**Component** (Optional):

**Selected**: `Component: ScorerRegistry`

**Purpose**: Avoid concurrent edits to the scorer registry from other tasks.

---

### Label Summary

```
Suggested labels for this task:
- Risk: Low
- Files: scorers/__init__.py, scorers/base.py, scorers/registry.py, scorers/builtin.py, test_scorer_registry.py
- Layer: Service
- Area: Evaluation
- Tests: Unit
- Component: ScorerRegistry
```

**How these labels help the autonomous workflow:**
- **Risk: Low** — Higher parallelism allowance; reversible.
- **Files: ...** — Prevents file conflicts with other scorer-touching tasks.
- **Layer: Service** — Can run in parallel with UI/API/Database tasks.
- **Area: Evaluation** — Serialize against other Evaluation-area tasks (HOK-150x line) to avoid stepping on shared modules.
- **Tests: Unit** — Fast, parallel-safe.
- **Component: ScorerRegistry** — Prevents concurrent edits to the new registry.