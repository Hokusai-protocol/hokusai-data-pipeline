"""Canonical Hokusai MLflow run tag keys."""

from __future__ import annotations

PRIMARY_METRIC_TAG = "hokusai.primary_metric"
MLFLOW_NAME_TAG = "hokusai.mlflow_name"
DATASET_HASH_TAG = "hokusai.dataset.hash"  # dotted form — DeltaOne/HEM convention
DATASET_ID_TAG = "hokusai.dataset.id"
DATASET_NUM_SAMPLES_TAG = "hokusai.dataset.num_samples"
SCORER_REF_TAG = "hokusai.scorer_ref"
MEASUREMENT_POLICY_TAG = "hokusai.measurement_policy"
STATUS_TAG = "hokusai.eval.status"
FAILURE_REASON_TAG = "hokusai.eval.failure_reason"
PROJECTED_COST_TAG = "hokusai.eval.projected_cost_usd"
ACTUAL_COST_TAG = "hokusai.eval.actual_cost_usd"
EVAL_SPEC_ID_TAG = "hokusai.benchmark_spec_id"
