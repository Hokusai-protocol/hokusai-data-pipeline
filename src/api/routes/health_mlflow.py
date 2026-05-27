"""MLflow health check endpoints accessible at /api/health/mlflow.

MLflow authentication is inherited from the SDK environment such as
`MLFLOW_TRACKING_TOKEN` plus internal mTLS configuration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.mlflow_health import check_mlflow_registry_sdk

router = APIRouter()


def _sdk_result_to_payload(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    if payload["status"] == "ok":
        payload["sample_model"] = payload.get("sample_model")
    return payload


@router.get("/mlflow")
async def mlflow_health_check() -> JSONResponse:
    """Check MLflow registry reachability through the MLflow SDK transport."""
    result = (await check_mlflow_registry_sdk()).to_dict()
    payload = _sdk_result_to_payload(result)
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/mlflow/detailed")
async def mlflow_detailed_health_check() -> JSONResponse:
    """Return the same SDK-path health payload for detailed diagnostics."""
    return await mlflow_health_check()


@router.get("/mlflow/connectivity")
async def mlflow_connectivity_check() -> JSONResponse:
    """Return the same SDK-path health payload for connectivity checks."""
    return await mlflow_health_check()
