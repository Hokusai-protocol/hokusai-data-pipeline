"""Guardrail evaluation for DeltaOne mint gating."""

from __future__ import annotations

from collections.abc import Sequence

from src.evaluation.schema import GuardrailBreach, GuardrailResult
from src.evaluation.spec_translation import RuntimeGuardrailSpec


def evaluate_guardrails(
    observations: dict[str, float],
    guardrails: Sequence[RuntimeGuardrailSpec],
) -> GuardrailResult:
    """Evaluate all guardrails against observed metric values.

    Only ``blocking=True`` guardrails produce breaches.  Non-blocking guardrails
    are informational and do not affect the returned ``passed`` status.
    """
    breaches: list[GuardrailBreach] = []

    for spec in guardrails:
        if not spec.blocking:
            continue

        observed = observations.get(spec.name)
        if observed is None:
            continue

        breached = False
        if spec.direction == "higher_is_better" and observed < spec.threshold:
            breached = True
            reason = f"{spec.name} observed {observed:.4g} is below threshold {spec.threshold:.4g}"
        elif spec.direction == "lower_is_better" and observed > spec.threshold:
            breached = True
            reason = f"{spec.name} observed {observed:.4g} exceeds threshold {spec.threshold:.4g}"

        if breached:
            breaches.append(
                GuardrailBreach(
                    metric_name=spec.name,
                    observed=observed,
                    threshold=spec.threshold,
                    direction=spec.direction,
                    policy="reject_mint",
                    reason=reason,
                )
            )

    return GuardrailResult(passed=len(breaches) == 0, breaches=tuple(breaches))
