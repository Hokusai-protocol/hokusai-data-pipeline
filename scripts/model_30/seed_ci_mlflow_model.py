"""Seed a lightweight MLflow pyfunc model for health-test CI.

Authentication follows the normal MLflow SDK environment, including
`MLFLOW_TRACKING_TOKEN` when the registry requires bearer auth.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

import cloudpickle
import mlflow
import pandas as pd
import requests

MODEL_NAME = os.getenv("MODEL_30_REGISTERED_MODEL_NAME", "Technical Task Router")


class TechnicalTaskRouterSmokeModel(mlflow.pyfunc.PythonModel):
    """Minimal pyfunc model that matches the model 30 response contract."""

    def predict(
        self: TechnicalTaskRouterSmokeModel,
        context,  # noqa: ANN001
        model_input: Any,
    ) -> pd.DataFrame:
        del context
        rows = len(model_input.index) if hasattr(model_input, "index") else 1
        return pd.DataFrame(
            [
                {
                    "selected_model": "gpt-5.4",
                    "selected_models": ["gpt-5.4", "claude-sonnet-4-6"],
                    "confidence": 0.91,
                    "rationale": "Seeded smoke model for MLflow mTLS integration coverage",
                    "estimated_cost_usd": 0.42,
                }
                for _ in range(rows)
            ]
        )


def main() -> None:
    """Register and smoke-load the CI model against the configured MLflow server."""
    tracking_uri = os.environ["MLFLOW_TRACKING_URI"]
    tracking_token = os.getenv("MLFLOW_TRACKING_TOKEN")
    if tracking_token:
        os.environ["MLFLOW_TRACKING_TOKEN"] = tracking_token
    mlflow.set_tracking_uri(tracking_uri)

    print("seed_status=creating_registered_model", flush=True)  # noqa: T201
    _create_registered_model(tracking_uri, MODEL_NAME)

    print("seed_status=creating_run", flush=True)  # noqa: T201
    run_id, artifact_uri = _create_run(tracking_uri)

    model_path = _path_from_file_uri(f"{artifact_uri.rstrip('/')}/model")
    shutil.rmtree(model_path, ignore_errors=True)

    print("seed_status=saving_model", flush=True)  # noqa: T201
    _write_pyfunc_model(model_path)

    print("seed_status=creating_model_version", flush=True)  # noqa: T201
    version = _create_model_version(tracking_uri, MODEL_NAME, model_path.as_uri(), run_id)

    # Use version number directly; 'latest' is not a built-in in MLflow 3.x.
    model_uri = f"models:/{MODEL_NAME}/{version}"
    print(f"seed_status=loading_model uri={model_path.as_uri()}", flush=True)  # noqa: T201
    loaded = mlflow.pyfunc.load_model(model_path.as_uri())
    sample = pd.DataFrame(
        [
            {
                "task_type": "feature",
                "language": "python",
                "framework": "fastapi",
                "repo_type": "monorepo",
            }
        ]
    )
    loaded.predict(sample)
    _finish_run(tracking_uri, run_id)
    print("seed_status=smoke_prediction_ok", flush=True)  # noqa: T201
    print(f"seeded_model_name={MODEL_NAME}")  # noqa: T201
    print(f"seeded_model_version={version}")  # noqa: T201
    print(f"seeded_model_uri={model_uri}")  # noqa: T201


def _create_registered_model(tracking_uri: str, name: str) -> None:
    response = _post_mlflow(tracking_uri, "registered-models/create", {"name": name})
    if response.status_code == 200:
        return

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code == 400 and payload.get("error_code") == "RESOURCE_ALREADY_EXISTS":
        return
    response.raise_for_status()


def _create_run(tracking_uri: str) -> tuple[str, str]:
    response = _post_mlflow(
        tracking_uri,
        "runs/create",
        {
            "experiment_id": "0",
            "start_time": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        },
    )
    response.raise_for_status()
    run_info = response.json()["run"]["info"]
    return str(run_info["run_id"]), str(run_info["artifact_uri"])


def _finish_run(tracking_uri: str, run_id: str) -> None:
    response = _post_mlflow(
        tracking_uri,
        "runs/update",
        {
            "run_id": run_id,
            "status": "FINISHED",
            "end_time": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        },
    )
    response.raise_for_status()


def _create_model_version(tracking_uri: str, name: str, source: str, run_id: str) -> str:
    response = _post_mlflow(
        tracking_uri,
        "model-versions/create",
        {"name": name, "source": source, "run_id": run_id},
    )
    if response.status_code != 200:
        print(  # noqa: T201
            f"seed_status=model_version_error status={response.status_code} body={response.text}",
            flush=True,
        )
    response.raise_for_status()
    return str(response.json()["model_version"]["version"])


def _post_mlflow(tracking_uri: str, endpoint: str, payload: dict[str, str]) -> requests.Response:
    headers = {}
    if token := os.getenv("MLFLOW_TRACKING_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    return requests.post(
        f"{tracking_uri.rstrip('/')}/api/2.0/mlflow/{endpoint}",
        json=payload,
        headers=headers,
        cert=(os.environ["MLFLOW_CLIENT_CERT_PATH"], os.environ["MLFLOW_CLIENT_KEY_PATH"]),
        verify=os.environ["MLFLOW_CA_BUNDLE_PATH"],
        timeout=10,
    )


def _path_from_file_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Expected file artifact URI, got: {uri}")
    return Path(unquote(parsed.path))


def _write_pyfunc_model(model_path: Path) -> None:
    model_path.mkdir(parents=True, exist_ok=True)
    with (model_path / "python_model.pkl").open("wb") as model_file:
        cloudpickle.dump(TechnicalTaskRouterSmokeModel(), model_file)

    python_version = ".".join(str(part) for part in sys.version_info[:3])
    (model_path / "requirements.txt").write_text("mlflow==3.9.0\npandas\n", encoding="utf-8")
    (model_path / "python_env.yaml").write_text(
        "\n".join(
            [
                f"python: {python_version}",
                "build_dependencies:",
                "- pip==24.0",
                "- setuptools==79.0.1",
                "- wheel==0.45.1",
                "dependencies:",
                "- -r requirements.txt",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (model_path / "conda.yaml").write_text(
        "\n".join(
            [
                "channels:",
                "- conda-forge",
                "dependencies:",
                f"- python={python_version}",
                "- pip<=24.0",
                "- pip:",
                "  - mlflow==3.9.0",
                "  - pandas",
                "name: mlflow-env",
                "",
            ]
        ),
        encoding="utf-8",
    )
    utc_time_created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    (model_path / "MLmodel").write_text(
        "\n".join(
            [
                "flavors:",
                "  python_function:",
                f"    cloudpickle_version: {cloudpickle.__version__}",
                "    code: null",
                "    env:",
                "      conda: conda.yaml",
                "      virtualenv: python_env.yaml",
                "    loader_module: mlflow.pyfunc.model",
                "    python_model: python_model.pkl",
                f"    python_version: {python_version}",
                "    streamable: false",
                "mlflow_version: 3.9.0",
                "model_id: null",
                f"model_size_bytes: {(model_path / 'python_model.pkl').stat().st_size}",
                f"model_uuid: {uuid4().hex}",
                "prompts: null",
                f"utc_time_created: '{utc_time_created}'",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
