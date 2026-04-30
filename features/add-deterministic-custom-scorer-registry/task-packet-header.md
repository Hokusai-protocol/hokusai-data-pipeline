# HOK-1503 - Quick Reference

**Issue ID**: HOK-1503

## Objective

Create a deterministic custom scorer registry under `src/evaluation/scorers/` that resolves business-outcome scorers by stable reference, exposes their source hash for HEM provenance, and is consumable by adapters and `spec_translation.py`. This is a non-LLM, deterministic counterpart to LLM-as-judge logic in `src/evaluation/judges/` (which remains untouched).

## Key Files

- `src/evaluation/scorers/__init__.py` (new — public registry API)
- `src/evaluation/scorers/base.py` (new — `ScorerMetadata`, `Scorer` protocol)
- `src/evaluation/scorers/registry.py` (new — registration decorator + resolver)
- `src/evaluation/scorers/builtin.py` (new — built-in deterministic scorers)
- `tests/unit/test_scorer_registry.py` (new — covers happy path + missing/unknown refs)

## Critical Constraints

1. Scorers MUST be deterministic outcome aggregations only — no LLM calls, no I/O, no randomness. LLM-as-judge stays in `src/evaluation/judges/` (do not modify).
2. Source hash MUST be stable across processes (content-addressed via `inspect.getsource` + SHA-256) so HEM provenance comparisons hold across runs.
3. Public resolver API must raise a typed `UnknownScorerError` for missing refs — adapters and `spec_translation.py` rely on a single, predictable error type.

## Success Criteria (High-Level)

- [ ] `resolve_scorer(ref)` returns a `Scorer` with metadata (input schema, output metric keys, metric_family, aggregation semantics, source hash) for every registered ref
- [ ] Source hash is deterministic and exposed via `ScorerMetadata.source_hash`
- [ ] Unknown / missing refs raise `UnknownScorerError` with the offending ref in the message
- [ ] Tests and lint pass (`pytest tests/unit/test_scorer_registry.py`, `ruff check src/evaluation/scorers tests/unit/test_scorer_registry.py`)
- [ ] PR created and linked to HOK-1503

## Detailed Sections

Full details available on-demand in task-packet-details.md:

- [Section 1: Complete Objective & Scope](#1-objective)
- [Section 2: Technical Context](#2-technical-context)
- [Section 3: Implementation Approach](#3-implementation-approach)
- [Section 4: Success Criteria](#4-success-criteria)
- [Section 5: Implementation Constraints](#5-implementation-constraints)
- [Section 6: Validation Steps](#6-validation-steps)
- [Section 8: Definition of Done](#8-definition-of-done)
- [Section 9: Rollback Plan](#9-rollback-plan)
- [Section 10: Release Readiness](#10-release-readiness)
- [Section 11: Proposed Labels](#11-proposed-labels)

**Implementation Note**: Start with this overview. Read detailed sections on-demand as you implement.