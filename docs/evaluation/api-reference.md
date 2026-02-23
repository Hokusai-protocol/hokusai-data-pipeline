# HEK API Reference

This reference documents the HEK API surface implemented in this repository.

Related pages:
- [Quick Start](./quickstart.md)
- [Custom Providers](./custom-providers.md)
- [Migration Guide](./migration-guide.md)

## Package exports (`src.evaluation`)

### Protocols and adapter registry

#### `EvalAdapter`

```python
class EvalAdapter(Protocol):
    def run(self, eval_spec: str, model_ref: str) -> str: ...
```

Minimal provider adapter contract.

#### `register_adapter(name: str, adapter: EvalAdapter) -> None`

Register an adapter by name.

#### `get_adapter(name: str) -> EvalAdapter`

Resolve a registered adapter.

#### `list_adapters() -> list[str]`

List registered adapter names.

#### `clear_adapters() -> None`

Clear adapter registry (mainly for tests).

### HEM data model

#### `HEM`

```python
@dataclass(slots=True)
class HEM:
    metric_name: str
    metric_value: float
    sample_size: int
    dataset_hash: str
    timestamp: datetime
    source_mlflow_run_id: str
    model_id: str
    experiment_id: str
    confidence_interval_lower: float | None = None
    confidence_interval_upper: float | None = None
```

### Manifest and schema

#### `HEM_V1_SCHEMA: dict[str, object]`

JSON schema for HEM manifest validation.

#### `HokusaiEvaluationManifest`

```python
@dataclass
class HokusaiEvaluationManifest:
    model_id: str
    eval_id: str
    dataset: dict[str, Any]
    primary_metric: dict[str, Any]
    metrics: list[dict[str, Any]]
    mlflow_run_id: str
    schema_version: str = "hokusai.eval.manifest/v1"
    ...
```

Methods:
- `to_dict() -> dict[str, Any]`
- `from_dict(data: dict[str, Any]) -> HokusaiEvaluationManifest`
- `compute_hash() -> str`
- `is_comparable_to(other) -> bool`
- `to_json(indent: int = 2) -> str`

#### `create_hem_from_mlflow_run(run_id, eval_id=None, primary_metric_name=None) -> HokusaiEvaluationManifest`

Build a manifest from an existing MLflow run.

#### `log_hem_to_mlflow(manifest, run_id=None) -> None`

Persist manifest as `hem/manifest.json` artifact.

#### `validate_manifest(data: dict) -> list[str]`

Return validation errors (empty list means valid).

### DeltaOne

#### `DeltaOneDecision`

```python
@dataclass(slots=True)
class DeltaOneDecision:
    accepted: bool
    reason: str
    run_id: str
    baseline_run_id: str
    model_id: str
    dataset_hash: str
    metric_name: str
    delta_percentage_points: float
    ci95_low_percentage_points: float
    ci95_high_percentage_points: float
    n_current: int
    n_baseline: int
    evaluated_at: datetime
```

#### `DeltaOneEvaluator(...)`

```python
DeltaOneEvaluator(
    mlflow_client: MlflowClientProtocol | None = None,
    cooldown_hours: int = 24,
    min_examples: int = 800,
    delta_threshold_pp: float = 1.0,
)
```

Methods:
- `evaluate(mlflow_run_id: str, baseline_mlflow_run_id: str) -> DeltaOneDecision`

#### `detect_delta_one(model_name: str, webhook_url: str | None = None) -> bool`

Backward-compatible detector based on model versions and benchmark tags.

#### `send_deltaone_webhook(webhook_url: str, payload: dict[str, Any], max_retries: int = 3) -> bool`

Queue webhook notifications for configured DeltaOne endpoints.

## Judge APIs (`src.evaluation.judges`)

### `JudgeConfig`

```python
JudgeConfig(
    model: str = "anthropic:/claude-opus-4-1-20250805",
    temperature: float = 0.0,
    name_prefix: str = "hokusai",
)
```

### Core judge helpers

- `create_judge(base_name: str, instructions: str, config: JudgeConfig | None = None) -> Any`
- `register_judge(judge: Any, name: str | None = None, experiment_id: str | None = None) -> Any`
- `list_registered_judges(experiment_id: str | None = None) -> list[Any]`

### Judge factories

- `create_classification_judge(task_description: str, config: JudgeConfig | None = None) -> Any`
- `create_generation_judge(metrics: list[str], config: JudgeConfig | None = None) -> Any`
- `create_ranking_judge(config: JudgeConfig | None = None) -> Any`
- `create_session_scorer(config: JudgeConfig | None = None) -> Any`

### DeepEval bridge

- `is_deepeval_judge_api_available() -> bool`
- `get_deepeval_judge(metric_name: str) -> Any`
- `get_faithfulness_judge() -> Any`
- `get_answer_relevancy_judge() -> Any`
- `get_contextual_precision_judge() -> Any`

## Evaluation wrapper (`src.modules.evaluation`)

### `ModelEvaluator`

```python
ModelEvaluator(metrics: list[str] | None = None)
```

Default metrics: `accuracy`, `precision`, `recall`, `f1`, `auroc`.

Methods:
- `evaluate_sklearn_model(model, X_test, y_test, threshold=0.5) -> dict[str, float | None]`
- `evaluate_mock_model(model, X_test, y_test) -> dict[str, float]`
- `evaluate_model(model, X_test, y_test) -> dict[str, Any]`
- `compare_models(baseline_metrics, new_metrics) -> dict[str, dict[str, float]]`
- `calculate_delta_score(comparison, weights=None) -> float`
- `create_evaluation_report(baseline_results, new_results, comparison, delta_score) -> dict[str, Any]`

`evaluate_sklearn_model` uses `mlflow.evaluate(..., extra_metrics=[...])`.

## OpenAI adapter (`src.evals.openai_adapter`)

### `OpenAIEvalsAdapter`

```python
OpenAIEvalsAdapter(experiment_name: str | None = None)
```

Method:
- `run(eval_spec: str, model_ref: str, tags: dict[str, str] | None = None) -> str`

Behavior:
- Runs `oaieval`
- Parses numeric metrics from JSON report/stdout
- Logs metrics, tags, and raw output to MLflow
- Returns MLflow run ID

