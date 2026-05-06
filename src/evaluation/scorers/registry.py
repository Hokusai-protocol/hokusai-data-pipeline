"""Registry for deterministic custom scorers."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable

from src.evaluation.scorers.metadata import Aggregation, MetricFamily, ScorerMetadata
from src.utils.metric_naming import derive_mlflow_name, validate_mlflow_metric_key


class UnknownScorerError(KeyError):
    """Raised when a scorer ref is not found in the registry."""

    def __init__(self: UnknownScorerError, ref: str) -> None:
        super().__init__(f"Unknown scorer ref: {ref!r}")


class ScorerConflictError(ValueError):
    """Raised when a scorer ref is registered again with different metadata."""

    def __init__(self: ScorerConflictError, ref: str) -> None:
        super().__init__(f"Scorer ref {ref!r} already registered with different metadata")


@dataclass(frozen=True)
class RegisteredScorer:
    """A scorer paired with its callable."""

    metadata: ScorerMetadata
    callable_: Callable[..., Any]


_REGISTRY: dict[str, RegisteredScorer] = {}


def compute_source_hash(
    scorer_ref: str,
    version: str,
    input_schema: dict[str, Any],
    output_metric_keys: tuple[str, ...] | list[str],
    metric_family: MetricFamily,
    aggregation: Aggregation,
    callable_: Callable[..., Any],
) -> str:
    """Compute a stable SHA-256 content hash for a scorer.

    The hash covers all identity fields (scorer_ref, version, input_schema,
    output_metric_keys, metric_family, aggregation) plus the callable's source
    code (via inspect.getsource; falls back to __qualname__ if unavailable).
    The ``description`` field is intentionally excluded — cosmetic changes do
    not affect scorer identity.

    Canonicalization: serialize to JSON with sort_keys=True,
    separators=(',',':'), then SHA-256 hexdigest.
    """
    try:
        source = inspect.getsource(callable_)
    except (OSError, TypeError):
        source = callable_.__qualname__

    payload = {
        "scorer_ref": scorer_ref,
        "version": version,
        "input_schema": input_schema,
        "output_metric_keys": list(output_metric_keys),
        "metric_family": metric_family.value,
        "aggregation": aggregation.value,
        "source": source,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def register_scorer(
    scorer_ref: str,
    *,
    callable_: Callable[..., Any],
    version: str,
    input_schema: dict[str, Any],
    output_metric_keys: tuple[str, ...] | list[str],
    metric_family: MetricFamily,
    aggregation: Aggregation,
    description: str | None = None,
) -> None:
    """Register a scorer. Idempotent if metadata is identical; raises on conflict."""
    for key in output_metric_keys:
        # Canonical keys may contain ':' (e.g. 'sales:spam_complaint_rate'); validate
        # the derived MLflow-safe name rather than the canonical key directly.
        validate_mlflow_metric_key(derive_mlflow_name(key))

    source_hash = compute_source_hash(
        scorer_ref,
        version,
        input_schema,
        tuple(output_metric_keys),
        metric_family,
        aggregation,
        callable_,
    )

    metadata = ScorerMetadata(
        scorer_ref=scorer_ref,
        version=version,
        input_schema=input_schema,
        output_metric_keys=tuple(output_metric_keys),
        metric_family=metric_family,
        aggregation=aggregation,
        source_hash=source_hash,
        description=description,
    )

    existing = _REGISTRY.get(scorer_ref)
    if existing is not None:
        if existing.metadata.source_hash != source_hash:
            raise ScorerConflictError(scorer_ref)
        return

    _REGISTRY[scorer_ref] = RegisteredScorer(metadata=metadata, callable_=callable_)


def resolve_scorer(ref: str) -> RegisteredScorer:
    """Look up a scorer by ref. Raises UnknownScorerError on miss, TypeError if ref is not a str."""
    if not isinstance(ref, str):
        raise TypeError(f"scorer ref must be a str, got {type(ref).__name__!r}")
    if ref not in _REGISTRY:
        raise UnknownScorerError(ref)
    return _REGISTRY[ref]


def list_scorers() -> list[ScorerMetadata]:
    """Return all registered scorer metadata, sorted by scorer_ref."""
    return [_REGISTRY[ref].metadata for ref in sorted(_REGISTRY)]


def clear_scorers() -> None:
    """Remove all registered scorers. Intended for test isolation."""
    _REGISTRY.clear()
