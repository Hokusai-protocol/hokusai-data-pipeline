# HEK Concepts

This page defines the core concepts used by the Hokusai Evaluation Kit (HEK).

Related pages:
- [Quick Start](./quickstart.md)
- [API Reference](./api-reference.md)
- [Migration Guide](./migration-guide.md)

## What HEK is

HEK is a thin evaluation layer around MLflow 3.9.0 capabilities with Hokusai-specific structures for:
- Standardized evaluation manifests (HEM)
- Provider adapters
- DeltaOne acceptance decisions
- Judge templates for LLM-based scoring

## Architecture at a glance

| Layer | Responsibility | Main implementation |
|---|---|---|
| Evaluation execution | Run model evaluation with MLflow | `src/modules/evaluation.py` |
| Manifest standardization | Convert run data to HEM | `src/evaluation/manifest.py` |
| DeltaOne decisioning | Threshold + CI + cooldown checks | `src/evaluation/deltaone_evaluator.py` |
| Provider abstraction | Register and resolve adapters | `src/evaluation/interfaces.py`, `src/evaluation/provider_registry.py` |
| LLM judges | `make_judge()` templates and helpers | `src/evaluation/judges/*` |

## HEM (Hokusai Evaluation Manifest)

HEM is a normalized, provider-agnostic record for evaluation outcomes.

Core fields:
- `schema_version` (currently `hokusai.eval.manifest/v1`)
- `model_id`
- `eval_id`
- `dataset` (`id`, `hash`, `num_samples`)
- `primary_metric`
- `metrics`
- `mlflow_run_id`

Why it exists:
- Keeps cross-provider eval data comparable
- Preserves dataset hash and primary metric for DeltaOne checks
- Supports deterministic manifest hashing (`compute_hash()`)

## Providers and adapters

HEK adapters implement the `EvalAdapter` protocol:

```python
class EvalAdapter(Protocol):
    def run(self, eval_spec: str, model_ref: str) -> str:
        ...
```

Adapters are registered with:
- `register_adapter(name, adapter)`
- `get_adapter(name)`
- `list_adapters()`
- `clear_adapters()`

This allows provider-specific execution while preserving a shared result path in MLflow + HEM.

## DeltaOne

DeltaOne compares a candidate run against a baseline run and accepts only when all of the following pass:
- Minimum sample size (`min_examples`)
- Matching dataset hash
- Cooldown checks
- Improvement threshold (default `>= 1.0` percentage point)
- Statistical significance (95% CI lower bound > 0)

Output object: `DeltaOneDecision`

Important tags persisted to the candidate run include:
- `hokusai.deltaone.accepted`
- `hokusai.deltaone.reason`
- `hokusai.deltaone.delta_pp`
- `hokusai.deltaone.ci95_low_pp`
- `hokusai.deltaone.ci95_high_pp`

## MLflow 3.9.0 evaluation concepts used in HEK

### `mlflow.evaluate()` with `extra_metrics`

HEK uses the `extra_metrics` argument (not the legacy custom-metric argument name) when constructing evaluation calls.

### `make_judge()`

HEK judge helpers build reusable LLM judges with `mlflow.genai.make_judge(...)`.

### `get_judge()`

HEK includes guarded DeepEval lookup helpers (`get_deepeval_judge(...)`) that check runtime support first via `is_deepeval_judge_api_available()`.

### Session-level scorers

HEK session scoring is implemented using `make_judge()` prompts with `{{ trace }}` in instructions (`create_session_scorer(...)`).

### Online monitoring with LLM judges

A practical HEK monitoring loop is:
1. Log production traces/samples to MLflow runs.
2. Evaluate with judges (including session scorer).
3. Convert key runs to HEM manifests.
4. Track trend metrics and gate rollouts in CI/CD.

See:
- [CI/CD Integration](./cicd-integration.md)
- [Cost Optimization](./cost-optimization.md)
