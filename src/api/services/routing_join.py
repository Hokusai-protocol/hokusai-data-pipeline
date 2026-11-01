"""The one outcome-to-inference join for Model 30 (HOK-3365).

Every Model 30 outcome answers one of two questions, and they must never be
mixed:

* *Executed-model evidence*: how did the models that actually ran do? Every
  outcome is this kind of evidence, linked or not.
* *Recommendation evidence*: was Model 30's own recommendation right? Only an
  outcome that joins to the inference which made the recommendation, and whose
  harness changed nothing, can answer it.

Both intake paths (contribution rows and ``/api/v1/outcomes`` submissions)
resolve through :func:`resolve_routing_joins`. The recommendation is read only
from the inference log (``inference_logs.output_payload``); rows never carry a
copy of it (HOK-3364). The link key is ``inference_log_id`` and nothing else: a
row's ``task_id`` or ``row_id`` never produces a link.

A row is recommendation evidence only when it has no override on *any* role.
The outcome is task-level, so a reviewer override contaminates the coder's
evidence too. The per-role override list is kept for reporting.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

ROUTING_JOIN_VERSION = "routing_join/v1"

ROUTE_ROLES: tuple[str, ...] = ("planner", "coder", "reviewer")
ROUTE_OVERRIDE_SOURCES: tuple[str, ...] = ("escalation", "launchability", "challenge", "operator")
_OVERRIDE_KEYS = frozenset({"role", "source", "from", "to", "reason"})
_ROUTE_SLUG = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")

# Keys that would store a copy of the recommendation (mirrors the SDK's
# ``RECOMMENDATION_COPY_KEYS``). Compared with underscores removed, case-folded.
RECOMMENDATION_COPY_KEYS: frozenset[str] = frozenset(
    key.replace("_", "")
    for key in (
        "recommended_model",
        "recommended_models",
        "recommended_model_id",
        "recommendation",
        "recommendation_accepted",
    )
)


class LinkStatus(str, Enum):
    """Whether an outcome joined to the inference that recommended its route."""

    LINKED = "linked"
    # No ``inference_log_id``: Hokusai did not route this task (or the writer
    # dropped the key). Usable only as executed-model evidence.
    UNLINKED = "unlinked"
    # The row names an inference log that does not exist. Inference logs are
    # written best-effort in the background, so this is expected occasionally.
    LOG_MISSING = "log_missing"
    # The inference log belongs to a different API token than the submitter.
    FOREIGN_TOKEN = "foreign_token"
    # The inference log store could not be reached at intake. Re-resolvable.
    UNRESOLVED = "unresolved"


class EvidenceClass(str, Enum):
    """What an outcome is evidence about."""

    RECOMMENDATION = "recommendation"
    OVERRIDE = "override"
    EXECUTED_ONLY = "executed_only"
    # Linked, but the outcome does not say what ran or what was overridden, or
    # its claims contradict the inference log. Never recommendation evidence.
    UNATTRIBUTED = "unattributed"


# ---------------------------------------------------------------------------
# Routing-outcome block validation (port of the SDK's ``routingOutcomeErrors``)
# ---------------------------------------------------------------------------


def find_recommendation_copy(value: Any, path: str = "") -> str | None:
    """Return the dotted path of the first key that stores a recommendation copy."""
    if isinstance(value, list):
        for index, item in enumerate(value):
            found = find_recommendation_copy(item, f"{path}.{index}" if path else str(index))
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None
    for key, child in value.items():
        child_path = f"{path}.{key}" if path else str(key)
        if str(key).casefold().replace("_", "") in RECOMMENDATION_COPY_KEYS:
            return child_path
        found = find_recommendation_copy(child, child_path)
        if found:
            return found
    return None


def routing_outcome_errors(row: Mapping[str, Any]) -> list[str]:  # noqa: C901
    """Return why a row's routing-outcome block is invalid; ``[]`` when valid.

    Rules (HOK-3364): ``overrides`` is present iff ``inference_log_id`` is; each
    override is well-formed; per role, overrides chain and end at the executed
    model in ``selected_models``.
    """
    errors: list[str] = []
    routed = "inference_log_id" in row and row["inference_log_id"] is not None
    log_id = row.get("inference_log_id")
    if routed and (not isinstance(log_id, str) or not log_id.strip()):
        errors.append("inference_log_id must be a non-empty string")
    overrides = row.get("overrides")
    if routed and overrides is None:
        errors.append("a routed row must list overrides ([] when the recommendation was followed)")
    if not routed and overrides is not None:
        errors.append("overrides require inference_log_id")
    if overrides is None:
        return errors
    if not isinstance(overrides, list):
        return [*errors, "overrides must be an array"]

    selected = row.get("selected_models")
    selected = selected if isinstance(selected, dict) else {}
    last_by_role: dict[str, Mapping[str, Any]] = {}
    for index, entry in enumerate(overrides):
        label = f"overrides[{index}]"
        if not isinstance(entry, dict) or set(entry) - _OVERRIDE_KEYS or len(entry) != 5:
            errors.append(f"{label} must be an object with role, source, from, to and reason")
            continue
        if entry["role"] not in ROUTE_ROLES:
            errors.append(f"{label}.role must be one of: {', '.join(ROUTE_ROLES)}")
        if entry["source"] not in ROUTE_OVERRIDE_SOURCES:
            errors.append(f"{label}.source must be one of: {', '.join(ROUTE_OVERRIDE_SOURCES)}")
        for key in ("from", "to"):
            model = entry[key]
            if not isinstance(model, str) or not model.strip():
                errors.append(f"{label}.{key} must be a non-empty model id")
        if entry["from"] == entry["to"]:
            errors.append(f"{label} must change the model (from equals to)")
        if not isinstance(entry["reason"], str) or not _ROUTE_SLUG.match(entry["reason"]):
            errors.append(f"{label}.reason must be a slug")
        role = str(entry["role"])
        previous = last_by_role.get(role)
        if previous is not None and previous["to"] != entry["from"]:
            errors.append(f"{label}.from must equal the previous {role} override's to")
        last_by_role[role] = entry
    for role, last in last_by_role.items():
        if selected.get(role) != last["to"]:
            errors.append(f"the last {role} override must end at selected_models.{role}")
    return errors


# ---------------------------------------------------------------------------
# What an outcome claims, and what the inference log recorded
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingOutcome:
    """What an outcome says about its route. ``None`` means the outcome did not say."""

    inference_log_id: str | None
    executed: Mapping[str, str] | None
    overrides: tuple[Mapping[str, Any], ...] | None


def routing_outcome_from_row(row: Mapping[str, Any]) -> RoutingOutcome:
    """Read the routing-outcome block from a raw or normalized contribution row.

    Normalized canonical rows keep the block under ``metadata.routing_outcome``
    because the canonical schema's top level is closed.
    """
    block: Mapping[str, Any] = row
    metadata = row.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("routing_outcome"), dict):
        block = metadata["routing_outcome"]
    return routing_outcome_from_fields(
        inference_log_id=block.get("inference_log_id"),
        selected_models=block.get("selected_models"),
        overrides=block.get("overrides"),
    )


def routing_outcome_from_fields(
    *,
    inference_log_id: Any,
    selected_models: Any,
    overrides: Any,
) -> RoutingOutcome:
    """Build a :class:`RoutingOutcome` from loosely typed fields."""
    log_id = str(inference_log_id) if inference_log_id not in (None, "") else None
    executed: dict[str, str] | None = None
    # A list of models carries no roles, so it cannot be compared per role.
    if isinstance(selected_models, dict):
        executed = {
            role: model
            for role in ROUTE_ROLES
            if isinstance((model := selected_models.get(role)), str) and model
        }
    override_tuple = (
        tuple(entry for entry in overrides if isinstance(entry, dict))
        if isinstance(overrides, list)
        else None
    )
    return RoutingOutcome(inference_log_id=log_id, executed=executed, overrides=override_tuple)


@dataclass(frozen=True)
class InferenceRecord:
    """The recommendation an inference log recorded, plus its owner."""

    api_token_id: str
    recommended: Mapping[str, str]
    confidence: float | None
    estimated_success_under_budget: float | None


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def inference_record_from_log(
    *, api_token_id: str, output_payload: Mapping[str, Any] | None
) -> InferenceRecord:
    """Extract the recommended route from a stored Model 30 prediction payload."""
    payload: Mapping[str, Any] = output_payload or {}
    strategy = payload.get("recommended_strategy")
    if not isinstance(strategy, dict):
        nested = payload.get("predictions")
        strategy = nested.get("recommended_strategy") if isinstance(nested, dict) else None
    strategy = strategy if isinstance(strategy, dict) else {}
    recommended = {
        role: model
        for role in ROUTE_ROLES
        if isinstance((model := strategy.get(f"{role}_model")), str) and model
    }
    return InferenceRecord(
        api_token_id=str(api_token_id),
        recommended=recommended,
        confidence=_finite_float(strategy.get("confidence")),
        estimated_success_under_budget=_finite_float(
            strategy.get("estimated_success_under_budget")
        ),
    )


class InferenceLogLookup(Protocol):
    """Batch reader for inference logs, keyed by inference log id string."""

    def fetch(self: InferenceLogLookup, ids: Collection[str]) -> dict[str, InferenceRecord]:
        """Return the records that exist. Raise when the store is unreachable."""


class DatabaseInferenceLogLookup:
    """Reads inference logs from Postgres in one query per batch."""

    def __init__(self: DatabaseInferenceLogLookup, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def fetch(self: DatabaseInferenceLogLookup, ids: Collection[str]) -> dict[str, InferenceRecord]:
        from src.api.models import InferenceLog

        uuids: dict[UUID, str] = {}
        for raw in ids:
            try:
                uuids[UUID(str(raw))] = str(raw)
            except ValueError:
                continue  # Not a UUID, so no log can exist for it.
        if not uuids:
            return {}
        session = self._session_factory()
        try:
            logs = session.query(InferenceLog).filter(InferenceLog.id.in_(list(uuids))).all()
            return {
                uuids[UUID(str(log.id))]: inference_record_from_log(
                    api_token_id=log.api_token_id, output_payload=log.output_payload
                )
                for log in logs
            }
        finally:
            session.close()


# ---------------------------------------------------------------------------
# The joined record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingJoin:
    """``{recommended (from the log), executed (selected_models), overrides (from the row)}``."""

    link: LinkStatus
    inference_log_id: str | None
    recommended: Mapping[str, str]
    confidence: float | None
    estimated_success_under_budget: float | None
    executed: Mapping[str, str] | None
    overrides: tuple[Mapping[str, Any], ...] | None
    # Whether the outcome's claims agree with the inference log: each role's
    # first override starts at the recommended model, and each role without an
    # override ran the recommended model. ``None`` when not linked.
    consistent: bool | None

    @property
    def evidence(self: RoutingJoin) -> EvidenceClass:
        """Classify the outcome. Strict: any override on any role disqualifies it."""
        if self.link is not LinkStatus.LINKED:
            return EvidenceClass.EXECUTED_ONLY
        if self.executed is None or self.overrides is None or not self.consistent:
            return EvidenceClass.UNATTRIBUTED
        if self.overrides:
            return EvidenceClass.OVERRIDE
        return EvidenceClass.RECOMMENDATION

    @property
    def override_sources(self: RoutingJoin) -> tuple[str, ...]:
        """Distinct override sources, in first-seen order."""
        seen: list[str] = []
        for entry in self.overrides or ():
            source = str(entry.get("source"))
            if source not in seen:
                seen.append(source)
        return tuple(seen)

    def to_dict(self: RoutingJoin) -> dict[str, Any]:
        """Serialize for contribution metadata and inference-log trace metadata."""
        return {
            "join_version": ROUTING_JOIN_VERSION,
            "link": self.link.value,
            "evidence": self.evidence.value,
            "inference_log_id": self.inference_log_id,
            "recommended": dict(self.recommended),
            "confidence": self.confidence,
            "estimated_success_under_budget": self.estimated_success_under_budget,
            "executed": dict(self.executed) if self.executed is not None else None,
            "overrides": [dict(entry) for entry in self.overrides]
            if self.overrides is not None
            else None,
            "override_sources": list(self.override_sources),
            "consistent": self.consistent,
        }


def _claims_consistent(
    recommended: Mapping[str, str],
    outcome: RoutingOutcome,
    canonicalize: Callable[[str], str],
) -> bool:
    if not recommended:
        # The log holds no route (e.g. it is another model's inference).
        return False
    overridden: set[str] = set()
    for entry in outcome.overrides or ():
        role = str(entry.get("role"))
        if role in overridden:
            continue  # Only the first override of a role starts at the recommendation.
        overridden.add(role)
        expected = recommended.get(role)
        start = entry.get("from")
        if expected is not None and (
            not isinstance(start, str) or canonicalize(start) != canonicalize(expected)
        ):
            return False
    for role, executed_model in (outcome.executed or {}).items():
        if role in overridden:
            continue
        expected = recommended.get(role)
        if expected is not None and canonicalize(executed_model) != canonicalize(expected):
            return False
    return True


def _default_canonicalize(model_id: str) -> str:
    from src.api.endpoints.model_30_adapter import canonical_model_id

    return canonical_model_id(model_id)


def resolve_routing_joins(
    outcomes: Sequence[RoutingOutcome],
    *,
    api_token_id: str | None,
    lookup: InferenceLogLookup | None,
    canonicalize: Callable[[str], str] | None = None,
) -> list[RoutingJoin]:
    """Join every outcome to its inference log. Never raises.

    ``api_token_id`` is the submitter. A log owned by another token is
    ``foreign_token``, so one caller cannot attach outcomes to another's
    recommendations.
    """
    normalize = canonicalize or _default_canonicalize
    wanted = {outcome.inference_log_id for outcome in outcomes if outcome.inference_log_id}
    records: dict[str, InferenceRecord] | None = {}
    if wanted:
        if lookup is None:
            records = None
        else:
            try:
                records = lookup.fetch(wanted)
            except Exception:  # noqa: BLE001 - intake must never fail on the join
                logger.exception("routing_join_lookup_failed", extra={"count": len(wanted)})
                records = None

    joins: list[RoutingJoin] = []
    for outcome in outcomes:
        record: InferenceRecord | None = None
        if outcome.inference_log_id is None:
            link = LinkStatus.UNLINKED
        elif records is None:
            link = LinkStatus.UNRESOLVED
        elif (record := records.get(outcome.inference_log_id)) is None:
            link = LinkStatus.LOG_MISSING
        elif api_token_id is None or record.api_token_id != str(api_token_id):
            link = LinkStatus.FOREIGN_TOKEN
            record = None  # Never expose another caller's recommendation.
        else:
            link = LinkStatus.LINKED
        linked = record if link is LinkStatus.LINKED else None
        joins.append(
            RoutingJoin(
                link=link,
                inference_log_id=outcome.inference_log_id,
                recommended=dict(linked.recommended) if linked else {},
                confidence=linked.confidence if linked else None,
                estimated_success_under_budget=(
                    linked.estimated_success_under_budget if linked else None
                ),
                executed=outcome.executed,
                overrides=outcome.overrides,
                consistent=(
                    _claims_consistent(linked.recommended, outcome, normalize) if linked else None
                ),
            )
        )
    return joins


def summarize_routing_joins(joins: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count serialized joins by link status, evidence class and override source."""
    links = {status.value: 0 for status in LinkStatus}
    evidence = {cls.value: 0 for cls in EvidenceClass}
    overrides_by_source = {source: 0 for source in ROUTE_OVERRIDE_SOURCES}
    for join in joins:
        links[str(join.get("link"))] = links.get(str(join.get("link")), 0) + 1
        evidence[str(join.get("evidence"))] = evidence.get(str(join.get("evidence")), 0) + 1
        for entry in join.get("overrides") or []:
            source = str(entry.get("source"))
            overrides_by_source[source] = overrides_by_source.get(source, 0) + 1
    total = len(joins)
    return {
        "total": total,
        "links": links,
        "evidence": evidence,
        "overrides_by_source": overrides_by_source,
        "linked_share": (links[LinkStatus.LINKED.value] / total) if total else 0.0,
    }
