"""Unit coverage for Model 30 promotion and smoke validation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.model_30 import promote_technical_task_router as promotion


def _strategy_payload(model_id: str = "gpt-5.4") -> dict:
    return {
        "recommended_strategy": {
            "objective": "highest_reliability",
            "planner_model": model_id,
            "coder_model": model_id,
            "reviewer_model": model_id,
            "stages": ["plan", "code", "review"],
            "estimated_success_under_budget": 0.82,
            "estimated_cost_usd": 4.8,
            "estimated_duration_seconds": 1800,
            "confidence": 0.71,
        },
        "alternatives": [],
        "tradeoffs": {
            "lowest_cost": None,
            "fastest_completion": None,
            "highest_reliability": None,
        },
        "nearest_neighbors": {"count": 40},
    }


def test_assert_strategy_payload_rejects_fake_model_ids() -> None:
    with pytest.raises(ValueError, match="invalid model IDs"):
        promotion._assert_strategy_payload(_strategy_payload("deep-coder-v2"), source="test")


def test_assert_strategy_payload_rejects_nonpositive_duration_values() -> None:
    payload = _strategy_payload()
    payload["recommended_strategy"]["estimated_duration_seconds"] = 0.0

    with pytest.raises(ValueError, match="nonpositive duration"):
        promotion._assert_strategy_payload(payload, source="test")


def test_smoke_production_api_sends_auth_header_and_checks_all_objectives(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {
                "metadata": {"request_id": "req-123"},
                "predictions": _strategy_payload(),
            },
        )

    monkeypatch.setattr(promotion.requests, "post", fake_post)

    results = promotion._smoke_production_api(
        "https://api.hokus.ai/api/v1/models/30/predict",
        api_key="test-key",
        timeout_seconds=12.0,
    )

    assert [result["objective"] for result in results] == list(promotion.OBJECTIVES)
    assert [call["json"]["inputs"]["routing"]["objective"] for call in calls] == list(
        promotion.OBJECTIVES
    )
    assert all(call["headers"]["Authorization"] == "Bearer test-key" for call in calls)
    assert all(call["timeout"] == 12.0 for call in calls)


def test_register_promote_and_smoke_promotes_existing_version(monkeypatch) -> None:
    client = Mock()
    client.get_model_version_by_alias.return_value = SimpleNamespace(
        name=promotion.MODEL_NAME,
        version="4",
        run_id="run-old",
    )
    monkeypatch.setattr(promotion, "MlflowClient", lambda: client)
    monkeypatch.setattr(
        promotion,
        "_smoke_mlflow_model",
        lambda _model_uri: [{"objective": "lowest_cost"}],
    )

    report = promotion.register_promote_and_smoke(
        SimpleNamespace(
            tracking_uri=None,
            model_uri=f"models:/{promotion.MODEL_NAME}/5",
            router_dataset=None,
            holdout_dataset=None,
            evaluation_objectives="all",
            experiment_name=None,
            run_name="test",
            k_neighbors=40,
            training_manifest=None,
            model_id_uint=30,
            baseline_artifact_uri=None,
            eth_rpc_url="https://rpc.example",
            delta_verifier_address="0x" + "11" * 20,
            model_registry_address="0x" + "22" * 20,
            onchain_timeout_seconds=5.0,
            alias="production",
            no_promote=False,
            production_smoke=False,
            production_api_url="https://api.hokus.ai/api/v1/models/30/predict",
            api_key=None,
            production_timeout_seconds=30.0,
        )
    )

    client.set_registered_model_alias.assert_called_once_with(
        promotion.MODEL_NAME,
        "production",
        "5",
    )
    assert report["promotion"]["previous_alias_target"]["version"] == "4"
    assert "rollback_command" in report["promotion"]


def test_register_promote_and_smoke_passes_benchmark_args_to_registration(monkeypatch) -> None:
    client = Mock()
    client.get_model_version_by_alias.side_effect = Exception("missing alias")
    captured_args: list[SimpleNamespace] = []

    def fake_register_model(args: SimpleNamespace) -> dict:
        captured_args.append(args)
        return {
            "registered_model_name": promotion.MODEL_NAME,
            "registered_model_version": "8",
            "registered_model_uri": f"models:/{promotion.MODEL_NAME}/8",
        }

    monkeypatch.setattr(promotion, "MlflowClient", lambda: client)
    monkeypatch.setattr(promotion, "register_model", fake_register_model)
    monkeypatch.setattr(
        promotion,
        "_smoke_mlflow_model",
        lambda _model_uri: [{"objective": "lowest_cost"}],
    )

    promotion.register_promote_and_smoke(
        SimpleNamespace(
            tracking_uri=None,
            model_uri=None,
            router_dataset="/tmp/router.csv",
            holdout_dataset="/tmp/holdout.csv",
            evaluation_objectives="all",
            benchmark_version="v2",
            primary_metric="technical_task_router.benchmark_score_v2",
            benchmark_spec_id="technical_task_router.benchmark_score/v2",
            experiment_name=None,
            run_name="test",
            k_neighbors=40,
            training_manifest=None,
            model_id_uint=30,
            baseline_artifact_uri=None,
            eth_rpc_url="https://rpc.example",
            delta_verifier_address="0x" + "11" * 20,
            model_registry_address="0x" + "22" * 20,
            onchain_timeout_seconds=5.0,
            alias="production",
            no_promote=True,
            production_smoke=False,
            production_api_url="https://api.hokus.ai/api/v1/models/30/predict",
            api_key=None,
            production_timeout_seconds=30.0,
        )
    )

    assert len(captured_args) == 1
    assert captured_args[0].benchmark_version == "v2"
    assert captured_args[0].primary_metric == "technical_task_router.benchmark_score_v2"
    assert captured_args[0].benchmark_spec_id == "technical_task_router.benchmark_score/v2"
