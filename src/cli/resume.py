"""Resume and idempotency helpers for `hokusai eval` runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RUN_COMPLETED_STATUSES = {"FINISHED"}
RUN_INCOMPLETE_STATUSES = {"RUNNING", "SCHEDULED", "FAILED", "KILLED"}


@dataclass(frozen=True)
class ResumeDecision:
    """Decision for whether to create, resume, or skip an evaluation run."""

    mode: str
    run_id: str | None
    message: str


@dataclass(frozen=True)
class RunSummary:
    """Normalized run summary used by resume logic."""

    run_id: str
    status: str
    eval_status: str | None


def _summarize_run(run: Any) -> RunSummary:
    """Create run summary from an MLflow run object."""
    tags = run.data.tags if hasattr(run, "data") else {}
    info = run.info if hasattr(run, "info") else None
    return RunSummary(
        run_id=getattr(info, "run_id", ""),
        status=getattr(info, "status", "").upper(),
        eval_status=tags.get("hoku_eval.status") if tags else None,
    )


def _is_completed(summary: RunSummary) -> bool:
    """Return whether run should be treated as complete for idempotency."""
    if summary.eval_status == "completed":
        return True
    return summary.status in RUN_COMPLETED_STATUSES


def _is_resumable(summary: RunSummary) -> bool:
    """Return whether run should be resumed."""
    if summary.eval_status in {"running", "aborted", "failed"}:
        return True
    return summary.status in RUN_INCOMPLETE_STATUSES


def _search_matching_runs(
    *,
    client: Any,
    model_id: str,
    eval_spec: str,
    seed: int | None,
) -> list[Any]:
    """Search for runs tagged with matching evaluation identity."""
    seed_value = "none" if seed is None else str(seed)
    filter_parts = [
        f"tags.hoku_eval.model_id = '{model_id}'",
        f"tags.hoku_eval.eval_spec = '{eval_spec}'",
        f"tags.hoku_eval.seed = '{seed_value}'",
    ]
    filter_string = " and ".join(filter_parts)

    experiment_ids = ["0"]
    if hasattr(client, "search_experiments"):
        try:
            experiments = client.search_experiments()
            if experiments:
                experiment_ids = [exp.experiment_id for exp in experiments]
        except Exception:
            experiment_ids = ["0"]

    return client.search_runs(
        experiment_ids=experiment_ids,
        filter_string=filter_string,
        max_results=25,
        order_by=["attributes.start_time DESC"],
    )


def resolve_resume_decision(
    *,
    client: Any,
    model_id: str,
    eval_spec: str,
    seed: int | None,
    resume: str | None,
) -> ResumeDecision:
    """Resolve idempotent behavior for explicit or auto resume options."""
    if resume and resume != "auto":
        run = client.get_run(resume)
        summary = _summarize_run(run)
        if _is_completed(summary):
            return ResumeDecision(
                mode="skip",
                run_id=summary.run_id,
                message="Requested run already completed; skipping execution.",
            )
        if _is_resumable(summary):
            return ResumeDecision(
                mode="resume",
                run_id=summary.run_id,
                message="Resuming requested MLflow run.",
            )

    if resume:
        runs = _search_matching_runs(
            client=client,
            model_id=model_id,
            eval_spec=eval_spec,
            seed=seed,
        )
        for run in runs:
            summary = _summarize_run(run)
            if _is_completed(summary):
                return ResumeDecision(
                    mode="skip",
                    run_id=summary.run_id,
                    message="Found matching completed run; skipping execution.",
                )
            if _is_resumable(summary):
                return ResumeDecision(
                    mode="resume",
                    run_id=summary.run_id,
                    message="Found matching incomplete run; resuming execution.",
                )

    return ResumeDecision(
        mode="new",
        run_id=None,
        message="No resumable run found; creating a new run.",
    )
