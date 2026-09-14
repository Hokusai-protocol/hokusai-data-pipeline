from __future__ import annotations

from scripts.model_30.activate_v2_benchmark_spec import apply_activation, plan_activation
from src.api.services.governance.benchmark_specs import BenchmarkSpecService

V1_METRIC = "technical_task_router.success_under_budget/v1"
V2_METRIC = "technical_task_router.benchmark_score/v2"


def _register(service: BenchmarkSpecService, *, metric_name: str, dataset_version: str) -> dict:
    return service.register_spec(
        model_id="30",
        dataset_id="model-30-router",
        dataset_version=dataset_version,
        eval_split="holdout",
        metric_name=metric_name,
        metric_direction="higher_is_better",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        is_active=True,
    )


def test_plan_targets_v2_and_deactivates_other_active_specs() -> None:
    service = BenchmarkSpecService()  # in-memory
    _register(service, metric_name=V1_METRIC, dataset_version="v1")
    v2 = _register(service, metric_name=V2_METRIC, dataset_version="v2")

    plan = plan_activation(service, model_id="30", metric_name=V2_METRIC)

    assert plan.target is not None
    assert plan.target["spec_id"] == v2["spec_id"]
    assert plan.to_activate == []  # v2 was registered active
    assert [s["metric_name"] for s in plan.to_deactivate] == [V1_METRIC]


def test_apply_makes_v2_the_single_active_spec() -> None:
    service = BenchmarkSpecService()
    _register(service, metric_name=V1_METRIC, dataset_version="v1")
    v2 = _register(service, metric_name=V2_METRIC, dataset_version="v2")

    apply_activation(service, plan_activation(service, model_id="30", metric_name=V2_METRIC))

    active = service.get_active_spec_for_model("30")
    assert active is not None
    assert active["spec_id"] == v2["spec_id"]
    assert active["metric_name"] == V2_METRIC
    # the v1 spec is no longer active
    v1_specs = [s for s in service.list_specs(model_id="30") if s["metric_name"] == V1_METRIC]
    assert all(not s["is_active"] for s in v1_specs)


def test_plan_returns_no_target_when_v2_spec_absent() -> None:
    service = BenchmarkSpecService()
    _register(service, metric_name=V1_METRIC, dataset_version="v1")

    plan = plan_activation(service, model_id="30", metric_name=V2_METRIC)

    assert plan.target is None
    assert plan.to_deactivate == []
