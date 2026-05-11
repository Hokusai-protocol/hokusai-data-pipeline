"""Dispatch BenchmarkSpec-backed custom evals through existing MLflow paths."""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.evaluation.schema import MetricFamily
from src.evaluation.spec_translation import RuntimeAdapterSpec, translate_benchmark_spec
from src.evaluation.tags import (
    ACTUAL_COST_TAG,
    DATASET_HASH_TAG,
    DATASET_ID_TAG,
    DATASET_NUM_SAMPLES_TAG,
    EVAL_SPEC_ID_TAG,
    FAILURE_REASON_TAG,
    MEASUREMENT_POLICY_TAG,
    MLFLOW_NAME_TAG,
    PER_ROW_ARTIFACT_URI_TAG,
    PRIMARY_METRIC_TAG,
    PROJECTED_COST_TAG,
    SCORER_REF_TAG,
    STATUS_TAG,
)
from src.utils.dataset_hash import parse_sha256_dataset_version
from src.utils.metric_naming import derive_mlflow_name

logger = logging.getLogger(__name__)

_PER_ROW_ARTIFACT_DIR = "eval_results"
_PER_ROW_ARTIFACT_FILE = "per_row.parquet"
_PER_ROW_ARTIFACT_PATH = "eval_results/per_row.parquet"

_REMOTE_PREFIXES = ("s3://", "gs://", "az://", "kaggle://", "http://", "https://")


class CustomEvalError(Exception):
    """Base exception for custom eval validation failures (pre-flight or spec issues)."""


class CustomEvalRuntimeError(CustomEvalError):
    """Raised when the MLflow evaluate call itself fails at runtime."""


class CostGateExceeded(CustomEvalError):  # noqa: N818
    """Raised when projected cost exceeds the configured cap."""


class ScorerLoadError(CustomEvalError):
    """Raised when a scorer ref cannot be resolved from the registry."""


class DatasetHashUnresolvableError(CustomEvalError):
    """Raised when no sha256 hash can be determined for the dataset."""


class DatasetLoadError(CustomEvalError):
    """Raised when a deterministic sales dataset cannot be loaded or validated."""


class DatasetAccessNotImplementedError(CustomEvalError, NotImplementedError):
    """Raised when deterministic scorer dispatch cannot yet read a remote dataset."""


class MetricNameCollisionError(CustomEvalError):
    """Raised when multiple scored specs collapse to the same MLflow metric key."""


@dataclass(frozen=True)
class CostProjection:
    """Result of pre-flight cost projection."""

    projected_usd: float
    cap_usd: float | None
    num_rows: int
    num_genai_scorers: int
    per_call_estimate_usd: float


def is_genai_spec(spec: RuntimeAdapterSpec) -> bool:
    """Return True if any scorer ref implies LLM-judge cost."""
    from src.evaluation.scorers.registry import UnknownScorerError, resolve_scorer

    refs = _all_scorer_refs(spec)
    for ref in refs:
        if ref.startswith("genai:") or ref.startswith("judge:"):
            return True
        try:
            registered = resolve_scorer(ref)
            if registered.metadata.metric_family == MetricFamily.QUALITY:
                return True
        except (UnknownScorerError, Exception):  # noqa: S110
            pass
    return False


def compute_dataset_hash(
    spec_dataset_version: str | None,
    dataset_path: str | None,
) -> str:
    """Return a ``sha256:<hex>`` dataset hash.

    Priority: (1) spec_dataset_version if already in sha256 form;
    (2) SHA-256 of canonical-JSON of dataset rows from local path.
    """
    canonical_dataset_version = parse_sha256_dataset_version(spec_dataset_version)
    if canonical_dataset_version:
        return canonical_dataset_version

    if dataset_path:
        p = Path(dataset_path)
        if p.exists() and p.is_file():
            try:
                canonical = _canonicalize_local_dataset_for_hash(p)
                return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            except Exception:  # noqa: S110
                pass

    raise DatasetHashUnresolvableError(
        "Cannot determine dataset hash: dataset_version is not in sha256 form "
        "and no local dataset path is readable."
    )


def project_cost(
    spec: RuntimeAdapterSpec,
    num_rows: int,
    cap_usd: float | None,
) -> CostProjection:
    """Compute O(1) pre-flight cost projection for GenAI scorer runs."""
    from src.evaluation.scorers.registry import UnknownScorerError, resolve_scorer

    policy = spec.measurement_policy or {}
    default_cost = float(os.getenv("HOKUSAI_DEFAULT_JUDGE_COST_USD", "0.01"))
    per_call = float(policy.get("per_call_cost_usd", default_cost))

    refs = _all_scorer_refs(spec)
    num_genai = 0
    for ref in refs:
        if ref.startswith("genai:") or ref.startswith("judge:"):
            num_genai += 1
            continue
        try:
            registered = resolve_scorer(ref)
            if registered.metadata.metric_family == MetricFamily.QUALITY:
                num_genai += 1
        except (UnknownScorerError, Exception):  # noqa: S110
            pass

    projected = num_rows * num_genai * per_call
    return CostProjection(
        projected_usd=projected,
        cap_usd=cap_usd,
        num_rows=num_rows,
        num_genai_scorers=num_genai,
        per_call_estimate_usd=per_call,
    )


def emit_canonical_tags(
    mlflow_module: Any,
    *,
    primary_metric_name: str,
    mlflow_name: str,
    dataset_hash: str,
    scorer_refs: list[str],
    measurement_policy: dict[str, Any] | None,
    benchmark_spec_id: str,
    num_samples: int,
    dataset_id: str,
) -> None:
    """Set the five canonical HEM/DeltaOne tags plus supporting tags on the active run."""
    unique_refs = sorted({r for r in scorer_refs if r})
    scorer_ref_value = ",".join(unique_refs) if unique_refs else "none"
    policy_value = json.dumps(measurement_policy, sort_keys=True) if measurement_policy else "none"

    mlflow_module.set_tag(PRIMARY_METRIC_TAG, primary_metric_name)
    mlflow_module.set_tag(MLFLOW_NAME_TAG, mlflow_name)
    mlflow_module.set_tag(DATASET_HASH_TAG, dataset_hash)
    mlflow_module.set_tag(SCORER_REF_TAG, scorer_ref_value)
    mlflow_module.set_tag(MEASUREMENT_POLICY_TAG, policy_value)
    mlflow_module.set_tag(DATASET_ID_TAG, dataset_id)
    mlflow_module.set_tag(DATASET_NUM_SAMPLES_TAG, str(num_samples))
    mlflow_module.set_tag(EVAL_SPEC_ID_TAG, benchmark_spec_id)


def run_custom_eval(  # noqa: C901
    *,
    model_id: str,
    benchmark_spec: dict[str, Any],
    benchmark_spec_id: str,
    mlflow_module: Any,
    mlflow_client: Any,
    cli_max_cost: float | None,
    seed: int | None,
    temperature: float | None,
) -> dict[str, Any]:
    """Dispatch a BenchmarkSpec-backed custom eval through MLflow.

    Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is configured on
    the injected mlflow_module before this function is called.

    Pre-MLflow-run aborts (raise before starting a run):
      - spec inactive → CustomEvalError
      - scorer ref unknown → ScorerLoadError
      - dataset hash unresolvable → DatasetHashUnresolvableError

    Post-MLflow-run aborts (tags written before raising):
      - cost gate exceeded → CostGateExceeded
      - mlflow evaluate failure → CustomEvalError("mlflow_evaluate_error: ...")
    """
    # 1. Validate is_active (pre-run abort)
    if not benchmark_spec.get("is_active", True):
        raise CustomEvalError("spec_not_found_or_inactive")

    # 2. Translate spec (pre-run abort)
    runtime_spec = translate_benchmark_spec(benchmark_spec)

    # 3. Validate scorers (pre-run abort)
    all_refs = _all_scorer_refs(runtime_spec)
    _validate_scorers(all_refs)

    # 4. Compute dataset hash (pre-run abort)
    dataset_reference = benchmark_spec.get("dataset_reference", "")
    is_remote_reference = _is_remote(dataset_reference)
    local_path = dataset_reference if not is_remote_reference else None
    if is_remote_reference and not parse_sha256_dataset_version(
        benchmark_spec.get("dataset_version")
    ):
        dataset_version = benchmark_spec.get("dataset_version")
        raise DatasetHashUnresolvableError(
            f"Remote dataset_reference {dataset_reference!r} requires dataset_version in "
            f"canonical sha256:<hex> form; got {dataset_version!r}."
        )
    dataset_hash = compute_dataset_hash(
        spec_dataset_version=benchmark_spec.get("dataset_version"),
        dataset_path=local_path,
    )

    # 5. Dataset metadata
    dataset_id = dataset_reference or benchmark_spec.get("dataset_id", "")
    num_samples = _count_rows(local_path) or 0

    # 6. Determine cost cap (spec policy takes priority over CLI flag)
    policy = runtime_spec.measurement_policy or {}
    spec_cap = policy.get("max_cost_usd")
    cap_usd = float(spec_cap) if spec_cap is not None else cli_max_cost

    # 7. Start MLflow run
    with mlflow_module.start_run(
        run_name=f"hokusai_custom_eval:{model_id}:{benchmark_spec_id}"
    ) as run:
        run_id = run.info.run_id

        # 8. Set canonical tags + running status
        primary_metric_name = runtime_spec.primary_metric.name
        mlflow_name_val = derive_mlflow_name(primary_metric_name)
        emit_canonical_tags(
            mlflow_module,
            primary_metric_name=primary_metric_name,
            mlflow_name=mlflow_name_val,
            dataset_hash=dataset_hash,
            scorer_refs=all_refs,
            measurement_policy=runtime_spec.measurement_policy,
            benchmark_spec_id=benchmark_spec_id,
            num_samples=num_samples,
            dataset_id=dataset_id,
        )
        mlflow_module.set_tag(STATUS_TAG, "running")

        # 9. Cost gate (GenAI specs only)
        genai = is_genai_spec(runtime_spec)
        if genai and cap_usd is not None:
            projection = project_cost(runtime_spec, num_samples, cap_usd)
            if projection.projected_usd > cap_usd:
                mlflow_module.set_tag(STATUS_TAG, "failed")
                mlflow_module.set_tag(FAILURE_REASON_TAG, "cost_gate_exceeded")
                mlflow_module.set_tag(PROJECTED_COST_TAG, f"{projection.projected_usd:.6f}")
                raise CostGateExceeded(
                    f"Projected cost ${projection.projected_usd:.4f} exceeds cap "
                    f"${cap_usd:.4f} "
                    f"({projection.num_rows} rows × {projection.num_genai_scorers} GenAI scorers "
                    f"× ${projection.per_call_estimate_usd:.4f}/call)"
                )

        result = _dispatch_runtime_result(
            mlflow_module=mlflow_module,
            model_id=model_id,
            dataset_reference=dataset_reference,
            runtime_spec=runtime_spec,
            run_id=run_id,
            genai=genai,
        )

        # 11. Log metrics and mark success
        metrics = _extract_metrics(result)
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                mlflow_module.log_metric(metric_name, float(metric_value))

        actual_cost = _find_cost_metric(metrics)
        if actual_cost is not None:
            mlflow_module.set_tag(ACTUAL_COST_TAG, f"{actual_cost:.6f}")

        mlflow_module.set_tag(STATUS_TAG, "succeeded")

        return {
            "status": "success",
            "run_id": run_id,
            "metrics": metrics,
            "benchmark_spec_id": benchmark_spec_id,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _all_scorer_refs(spec: RuntimeAdapterSpec) -> list[str]:
    refs: list[str] = []
    if spec.primary_metric.scorer_ref:
        refs.append(spec.primary_metric.scorer_ref)
    for m in spec.secondary_metrics:
        if m.scorer_ref:
            refs.append(m.scorer_ref)
    for g in spec.guardrails:
        if g.scorer_ref:
            refs.append(g.scorer_ref)
    return refs


def _validate_scorers(refs: list[str]) -> None:
    """Raise ScorerLoadError for any unknown non-prefixed scorer ref."""
    from src.evaluation.scorers.registry import UnknownScorerError, resolve_scorer

    for ref in refs:
        if ref.startswith("genai:") or ref.startswith("judge:"):
            continue
        try:
            resolve_scorer(ref)
        except UnknownScorerError as exc:
            raise ScorerLoadError(f"scorer_load_failed: {exc}") from exc


def _is_remote(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _REMOTE_PREFIXES)


def _has_direct_sales_scorer_refs(spec: RuntimeAdapterSpec) -> bool:
    scored_specs = _metric_specs_with_scorers(spec)
    return bool(scored_specs) and all(
        scorer_ref.startswith("sales:") for _, scorer_ref in scored_specs
    )


def _metric_specs_with_scorers(
    spec: RuntimeAdapterSpec,
) -> list[tuple[str, str]]:
    scored_specs: list[tuple[str, str]] = []
    if spec.primary_metric.scorer_ref:
        scored_specs.append((spec.primary_metric.name, spec.primary_metric.scorer_ref))
    scored_specs.extend(
        (metric.name, metric.scorer_ref) for metric in spec.secondary_metrics if metric.scorer_ref
    )
    scored_specs.extend(
        (guardrail.name, guardrail.scorer_ref)
        for guardrail in spec.guardrails
        if guardrail.scorer_ref
    )
    return scored_specs


def _count_rows(local_path: str | None) -> int | None:
    if not local_path:
        return None
    p = Path(local_path)
    if not p.exists() or not p.is_file():
        return None
    suffix = p.suffix.lower()
    try:
        if suffix == ".json":
            payload = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return len(payload)
            if isinstance(payload, dict):
                return 1
        elif suffix == ".jsonl":
            return sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
        elif suffix == ".parquet":
            return len(_load_parquet_rows(p))
        elif suffix in (".csv", ".tsv"):
            lines = p.read_text(encoding="utf-8").splitlines()
            return max(0, len(lines) - 1)
    except Exception:  # noqa: S110
        pass
    return None


def _coerce_metric_column(df: Any, col: str, family: MetricFamily) -> Any:
    """Cast a single metric column to the expected dtype for the given family."""
    import pandas as pd

    try:
        if family == MetricFamily.OUTCOME:
            numeric = pd.to_numeric(df[col], errors="coerce")
            non_null_values = set(numeric.dropna().tolist())
            if non_null_values.issubset({0.0, 1.0}):
                df[col] = numeric.astype(bool)
            else:
                df[col] = numeric
        elif family in (MetricFamily.QUALITY, MetricFamily.LATENCY, MetricFamily.COST):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    except Exception as cast_exc:  # noqa: BLE001
        logger.warning("Could not cast per-row column %r: %s", col, cast_exc)
    return df


def _apply_scorer_dtypes(df: Any, runtime_spec: RuntimeAdapterSpec) -> Any:
    """Apply dtype coercions for each registered scorer ref's output columns."""
    from src.evaluation.scorers.registry import UnknownScorerError, resolve_scorer

    for metric_name, ref in _metric_specs_with_scorers(runtime_spec):
        if ref.startswith("genai:") or ref.startswith("judge:"):
            continue
        try:
            registered = resolve_scorer(ref)
            candidate_columns = {
                derive_mlflow_name(metric_name),
                *(derive_mlflow_name(key) for key in registered.metadata.output_metric_keys),
            }
            for col in candidate_columns:
                if col in df.columns:
                    df = _coerce_metric_column(df, col, registered.metadata.metric_family)
        except (UnknownScorerError, Exception) as exc:  # noqa: BLE001
            logger.debug("Skipping dtype coercion for scorer ref %r: %s", ref, exc)
    return df


def _prepare_per_row_dataframe(result_df: Any, runtime_spec: RuntimeAdapterSpec) -> Any:
    """Normalize result_df for Parquet storage.

    Returns a copy with guaranteed string row_id, optional string unit_id, and
    dtype-coerced metric columns where metadata is available.
    """
    df = result_df.copy()

    if "row_id" not in df.columns:
        df["row_id"] = [str(i) for i in range(len(df))]
    else:
        df["row_id"] = df["row_id"].astype(str)

    if df["row_id"].duplicated().any():
        logger.warning(
            "Per-row result_df has duplicate row_id values; synthesizing positional row IDs."
        )
        df["row_id"] = [str(i) for i in range(len(df))]

    if "unit_id" in df.columns:
        df["unit_id"] = df["unit_id"].astype(str)

    return _apply_scorer_dtypes(df, runtime_spec)


def _persist_per_row_artifact(
    *,
    mlflow_module: Any,
    result: Any,
    runtime_spec: RuntimeAdapterSpec,
    run_id: str,
) -> str | None:
    """Persist result_df as eval_results/per_row.parquet and tag the run.

    Returns the artifact URI on success, None on any failure (best-effort).
    The eval result is never affected by failures in this function.
    """
    try:
        import pandas as pd

        result_df = getattr(result, "result_df", None)
        if result_df is None:
            return None
        if not isinstance(result_df, pd.DataFrame):
            return None
        if result_df.empty:
            return None

        df = _prepare_per_row_dataframe(result_df, runtime_spec)

        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / _PER_ROW_ARTIFACT_FILE
            df.to_parquet(str(parquet_path), index=False)

            raw_bytes = parquet_path.read_bytes()
            sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
            logger.debug("Per-row artifact sha256=%s row_count=%d", sha256_hex, len(df))

            mlflow_module.log_artifact(str(parquet_path), artifact_path=_PER_ROW_ARTIFACT_DIR)

        uri = f"runs:/{run_id}/{_PER_ROW_ARTIFACT_PATH}"
        mlflow_module.set_tag(PER_ROW_ARTIFACT_URI_TAG, uri)
        return uri

    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist per-row eval artifact: %s", exc)
        return None


def _dispatch_genai(
    *,
    mlflow_module: Any,
    model_id: str,
    dataset_reference: str,
    runtime_spec: RuntimeAdapterSpec,
    run_id: str,
) -> Any:
    """Route to mlflow.genai.evaluate for LLM-judge specs."""
    from src.evaluation.scorers.registry import UnknownScorerError, resolve_scorer

    try:
        mlflow_genai = importlib.import_module("mlflow.genai")
    except ImportError as exc:
        raise CustomEvalRuntimeError("mlflow_genai_unavailable") from exc

    scorer_callables: list[Any] = []
    for ref in _all_scorer_refs(runtime_spec):
        if ref.startswith("genai:") or ref.startswith("judge:"):
            continue
        try:
            registered = resolve_scorer(ref)
            scorer_callables.append(registered.callable_)
        except UnknownScorerError:
            pass

    result = mlflow_genai.evaluate(
        data=dataset_reference,
        scorers=scorer_callables,
        model_id=model_id,
    )
    _persist_per_row_artifact(
        mlflow_module=mlflow_module,
        result=result,
        runtime_spec=runtime_spec,
        run_id=run_id,
    )
    return result


def _dispatch_deterministic(
    *,
    mlflow_module: Any,
    model_id: str,
    dataset_reference: str,
    runtime_spec: RuntimeAdapterSpec,
    run_id: str,
) -> Any:
    """Route to mlflow.evaluate for deterministic specs."""
    policy = runtime_spec.measurement_policy or {}
    model_type = (
        runtime_spec.unit_of_analysis or policy.get("mlflow_evaluate_model_type") or "classifier"
    )
    result = mlflow_module.evaluate(
        model=f"models:/{model_id}",
        data=dataset_reference,
        model_type=model_type,
    )
    _persist_per_row_artifact(
        mlflow_module=mlflow_module,
        result=result,
        runtime_spec=runtime_spec,
        run_id=run_id,
    )
    return result


def _dispatch_runtime_result(
    *,
    mlflow_module: Any,
    model_id: str,
    dataset_reference: str,
    runtime_spec: RuntimeAdapterSpec,
    run_id: str,
    genai: bool,
) -> Any:
    try:
        if genai:
            return _dispatch_genai(
                mlflow_module=mlflow_module,
                model_id=model_id,
                dataset_reference=dataset_reference,
                runtime_spec=runtime_spec,
                run_id=run_id,
            )
        if _has_direct_sales_scorer_refs(runtime_spec):
            return _dispatch_deterministic_scorers(
                mlflow_module=mlflow_module,
                dataset_reference=dataset_reference,
                runtime_spec=runtime_spec,
                run_id=run_id,
            )
        return _dispatch_deterministic(
            mlflow_module=mlflow_module,
            model_id=model_id,
            dataset_reference=dataset_reference,
            runtime_spec=runtime_spec,
            run_id=run_id,
        )
    except CostGateExceeded:
        raise
    except CustomEvalError:
        mlflow_module.set_tag(STATUS_TAG, "failed")
        mlflow_module.set_tag(FAILURE_REASON_TAG, "mlflow_evaluate_error")
        raise
    except Exception as exc:
        mlflow_module.set_tag(STATUS_TAG, "failed")
        mlflow_module.set_tag(FAILURE_REASON_TAG, "mlflow_evaluate_error")
        raise CustomEvalRuntimeError(f"mlflow_evaluate_error: {exc}") from exc


def _dispatch_deterministic_scorers(
    *,
    mlflow_module: Any,
    dataset_reference: str,
    runtime_spec: RuntimeAdapterSpec,
    run_id: str,
) -> SimpleNamespace:
    """Compute deterministic scorer-backed metrics directly from registered callables."""
    from src.evaluation.scorers.registry import resolve_scorer

    metric_specs = _metric_specs_with_scorers(runtime_spec)
    metric_name_map: dict[str, str] = {}
    resolved_scorers: list[tuple[str, str, Any]] = []
    for spec_name, scorer_ref in metric_specs:
        mlflow_metric_name = derive_mlflow_name(spec_name)
        if mlflow_metric_name in metric_name_map:
            raise MetricNameCollisionError(
                "metric_name_collision: "
                f"{spec_name!r} and {metric_name_map[mlflow_metric_name]!r} both normalize to "
                f"{mlflow_metric_name!r}"
            )
        metric_name_map[mlflow_metric_name] = spec_name
        resolved_scorers.append((spec_name, mlflow_metric_name, resolve_scorer(scorer_ref)))

    rows = _load_sales_outcome_rows(dataset_reference)
    logger.info(
        "Running direct deterministic scorer dispatch for %d rows and scorer refs %s",
        len(rows),
        [registered.metadata.scorer_ref for _, _, registered in resolved_scorers],
    )

    metrics: dict[str, float] = {}
    for _, mlflow_metric_name, registered in resolved_scorers:
        metric_value = registered.callable_(rows)
        if not isinstance(metric_value, (int, float)):
            raise DatasetLoadError(
                f"deterministic scorer {registered.metadata.scorer_ref!r} returned non-numeric "
                f"value {metric_value!r}"
            )
        metrics[mlflow_metric_name] = float(metric_value)

    result = SimpleNamespace(
        metrics=metrics,
        result_df=_build_per_row_result_df(rows, metrics),
    )
    _persist_per_row_artifact(
        mlflow_module=mlflow_module,
        result=result,
        runtime_spec=runtime_spec,
        run_id=run_id,
    )
    return result


def _build_per_row_result_df(rows: list[dict[str, Any]], metrics: dict[str, float]) -> Any:
    import pandas as pd

    result_rows = []
    for row in rows:
        metric_columns = dict(metrics)
        result_rows.append({**row, **metric_columns})
    return pd.DataFrame(result_rows)


def _load_sales_outcome_rows(dataset_reference: str) -> list[dict[str, Any]]:
    if _is_remote(dataset_reference):
        raise DatasetAccessNotImplementedError(
            "S3 dataset access not yet wired for deterministic scorer dispatch"
        )

    dataset_path = Path(dataset_reference)
    if not dataset_path.exists() or not dataset_path.is_file():
        raise DatasetLoadError(f"dataset_reference is not a readable file: {dataset_reference!r}")

    suffix = dataset_path.suffix.lower()
    if suffix == ".json":
        rows = _load_json_rows(dataset_path)
    elif suffix == ".jsonl":
        rows = _load_jsonl_rows(dataset_path)
    elif suffix == ".parquet":
        rows = _load_parquet_rows(dataset_path)
    else:
        raise DatasetLoadError(
            f"unsupported deterministic sales dataset format {suffix!r} for {dataset_reference!r}"
        )

    if not rows:
        raise DatasetLoadError("deterministic scorer datasets must contain at least one row")

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DatasetLoadError(f"row {index} is not an object")
        if row.get("schema_version") != "sales_outcome_row/v1":
            raise DatasetLoadError(
                f"row {index} has unsupported schema_version {row.get('schema_version')!r}"
            )
    return rows


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetLoadError(f"invalid JSON dataset at {path}: {exc}") from exc

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    raise DatasetLoadError(f"JSON dataset at {path} must contain an object or array of objects")


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise DatasetLoadError(f"JSONL line {line_number} in {path} is not an object")
            rows.append(payload)
    except json.JSONDecodeError as exc:
        raise DatasetLoadError(f"invalid JSONL dataset at {path}: {exc}") from exc
    return rows


def _load_parquet_rows(path: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise DatasetLoadError("pandas is required to load parquet datasets") from exc

    try:
        return pd.read_parquet(path).to_dict("records")
    except Exception as exc:  # noqa: BLE001
        raise DatasetLoadError(f"invalid parquet dataset at {path}: {exc}") from exc


def _canonicalize_local_dataset_for_hash(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _canonicalize_json_payload(payload)
    if suffix == ".jsonl":
        return _canonicalize_json_payload(_load_jsonl_rows(path))
    if suffix == ".parquet":
        return _canonicalize_json_payload(_load_parquet_rows(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _canonicalize_json_payload(payload)


def _canonicalize_json_payload(payload: Any) -> str:
    if isinstance(payload, list):
        sorted_rows = sorted(
            payload,
            key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")),
        )
        return json.dumps(sorted_rows, sort_keys=True, separators=(",", ":"))
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _extract_metrics(result: Any) -> dict[str, Any]:
    if hasattr(result, "metrics") and isinstance(result.metrics, dict):
        return result.metrics
    if isinstance(result, dict) and isinstance(result.get("metrics"), dict):
        return result["metrics"]
    return {}


def _find_cost_metric(metrics: dict[str, Any]) -> float | None:
    for key in ("total_token_cost", "cost_usd"):
        if key in metrics and isinstance(metrics[key], (int, float)):
            return float(metrics[key])
    for key, value in metrics.items():
        if "cost" in key.lower() and isinstance(value, (int, float)):
            return float(value)
    return None
