# Hokusai Evals Kit (HEK) - Implementation Context Document
**REVISED FOR MLflow 3.4 Native Capabilities**

## Project Overview

### Mission

Build a comprehensive evaluation framework for Hokusai that **leverages MLflow 3.4's native GenAI evaluation capabilities** while adding Hokusai-specific business logic for DeltaOne token economics, statistical rigor, and provider integration.

### Key Business Requirements

- **DeltaOne Detection**: Automatically detect and reward ≥1 percentage point improvements in model performance
- **Token Economics**: Performance improvements trigger token minting (1pp = 1 DeltaOne token)
- **Anti-Gaming**: Statistical rigor and cooldown periods prevent manipulation
- **MLflow 3.4 Native**: Leverage built-in evaluation, custom judges, and evaluation datasets
- **Provider Integration**: Support external frameworks (OpenAI Evals, LM Eval Harness) via lightweight adapters
- **Enterprise Ready**: Reproducible, auditable, with cost controls

### MLflow 3.4 Native Features Leveraged

The following MLflow 3.4 features eliminate the need for custom implementations:

- **`mlflow.evaluate()`**: Core evaluation API with built-in metrics
- **`mlflow.genai.make_judge()`**: Custom LLM judges for GenAI evaluation (**NEW in 3.4**)
- **Evaluation Datasets**: Versioned, centralized test datasets (**NEW in 3.4**)
- **`mlflow.metrics.make_metric()`**: Custom metric definitions
- **`mlflow.data.Dataset`**: Dataset versioning and tracking
- **OpenTelemetry Integration**: Native observability and tracing (**NEW in 3.4**)
- **`mlflow.log_dict()`**: Structured manifest/artifact storage

### What We Build (Hokusai-Specific)

- **DeltaOne Evaluator**: Statistical significance testing, cooldown management, token minting triggers
- **Lightweight Provider Adapters**: Thin wrappers for OpenAI Evals and LM Eval Harness
- **Evaluation Orchestrator**: Cost controls, queue management, API layer
- **Hokusai Evaluation Manifest (HEM)**: Cross-provider result standardization for DeltaOne comparison

## Architecture Overview

### Revised System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / API Layer                       │
│  (hokusai eval command)         (REST endpoints)             │
└─────────────┬───────────────────────────┬───────────────────┘
              │                           │
┌─────────────▼───────────────────────────▼───────────────────┐
│                Evaluation Orchestrator                       │
│  - Cost Controls                                             │
│  - Queue Management                                          │
│  - HEM Generation                                            │
└─────────────┬───────────────────────────┬───────────────────┘
              │                           │
┌─────────────▼───────────┐ ┌────────────▼──────────────────┐
│  Lightweight Adapters    │ │     DeltaOne Evaluator        │
│  - OpenAI Evals (thin)  │ │  - Statistical Significance    │
│  - LM Eval Harness      │ │  - Cooldown Management        │
│  - MLflow Native        │ │  - Token Minting Trigger      │
└─────────────┬───────────┘ └────────────┬──────────────────┘
              │                           │
┌─────────────▼───────────────────────────▼───────────────────┐
│              MLflow 3.4 Native Evaluation                    │
│  - mlflow.evaluate()         - make_judge()                 │
│  - Evaluation Datasets       - Custom Metrics               │
│  - Dataset Versioning        - OpenTelemetry Tracing        │
└─────────────┬───────────────────────────┬───────────────────┘
              │                           │
┌─────────────▼───────────────────────────▼───────────────────┐
│                    Storage & Tracking                        │
│  - MLflow (metrics, artifacts, datasets)                    │
│  - PostgreSQL (MLflow backend, metadata)                    │
│  - Redis (queue, cache, cooldown tracking)                  │
│  - S3 (model artifacts, large datasets)                     │
└──────────────────────────────────────────────────────────────┘
```

### Key Architectural Changes from Original Plan

**REMOVED (now using MLflow 3.4 native):**
- ❌ Custom dataset manager → Use `mlflow.data.Dataset` and Evaluation Datasets
- ❌ Custom evaluation registry (YAML) → Use MLflow Evaluation Datasets
- ❌ Heavy provider abstraction → Use MLflow's native evaluation with lightweight adapters
- ❌ Custom observability → Use OpenTelemetry integration

**SIMPLIFIED:**
- ✅ Provider adapters are now thin wrappers that convert to MLflow format
- ✅ Native Hokusai evaluation uses `mlflow.evaluate()` directly
- ✅ Templates use `make_judge()` for LLM evaluation

**KEPT (Hokusai-specific business logic):**
- ✅ DeltaOne detection with statistical significance
- ✅ Cooldown management and anti-gaming
- ✅ Token minting integration
- ✅ Cost controls and estimation
- ✅ HEM for cross-provider comparison
- ✅ Queue management for async evaluation
- ✅ API and CLI layers

## Existing Codebase Structure

```
hokusai-data-pipeline/
├── src/
│   ├── api/                    # FastAPI application
│   │   ├── routes/
│   │   │   └── evaluations.py  # NEW: Evaluation endpoints
│   │   └── middleware/         # Auth, rate limiting
│   ├── evaluation/             # NEW: Evaluation system
│   │   ├── manifest.py         # HEM specification
│   │   ├── mlflow_wrapper.py   # NEW: Wrapper for mlflow.evaluate()
│   │   ├── judges/             # NEW: Custom judge templates
│   │   ├── adapters/           # NEW: Lightweight provider adapters
│   │   │   ├── openai_evals.py
│   │   │   ├── lm_eval.py
│   │   │   └── native.py
│   │   └── deltaone_evaluator.py  # EXISTING: Enhanced
│   ├── modules/
│   │   └── evaluation.py       # EXISTING: Current evaluator
│   └── services/
│       ├── model_registry.py   # EXISTING: MLflow registry
│       └── evaluation_queue.py # NEW: Redis queue management
├── tests/
│   └── unit/
│       ├── test_evaluation_deltaone_evaluator.py  # EXISTING
│       ├── test_mlflow_wrapper.py                 # NEW
│       └── test_evaluation_judges.py              # NEW
└── hokusai-ml-platform/
    └── src/hokusai/core/
        └── registry.py          # EXISTING: Tokenized registry
```

## Core Concepts

### 1. Hokusai Evaluation Manifest (HEM)

**Simplified with MLflow 3.4**: HEM is now primarily for DeltaOne comparison across providers. Most metadata is stored in MLflow's native format.

```json
{
    "schema": "hokusai.eval.manifest/v2",
    "model_id": "XRAY-123",
    "eval_id": "2025-01-09T12:00:00Z-abc123",
    "mlflow_run_id": "abc123def456",  // NEW: Link to MLflow run
    "provider": "mlflow_native",      // or "openai_evals", "lm_eval"
    "dataset": {
        "mlflow_dataset_id": "dataset_123",  // NEW: MLflow dataset reference
        "name": "xray-nih",
        "version": "1.4.0",
        "hash": "sha256:a1b2c3...",  // CRITICAL: For DeltaOne comparison
        "split": "test",
        "n_examples": 1000
    },
    "primary_metric": {
        "name": "accuracy",
        "value": 0.884,
        "direction": "maximize",
        "unit": "ratio"
    },
    "metrics": {
        "precision": 0.891,
        "recall": 0.878
    },
    "uncertainty": {
        "method": "bootstrap",
        "ci95": [0.874, 0.892]
    }
}
```

### 2. MLflow Native Evaluation Workflow

**NEW**: Simplified workflow using MLflow 3.4

```python
import mlflow
from mlflow.genai import make_judge

# 1. Load evaluation dataset (MLflow 3.4 native)
eval_dataset = mlflow.data.load_dataset(
    "evaluations://xray-nih/versions/1.4.0"
)

# 2. Create custom judge (MLflow 3.4 native)
accuracy_judge = make_judge(
    name="xray_accuracy",
    instructions=(
        "Evaluate if the diagnosis in {{ outputs }} matches "
        "the ground truth in {{ expectations }}."
    ),
    model="anthropic:/claude-opus-4-1-20250805"
)

# 3. Run evaluation (MLflow native)
results = mlflow.evaluate(
    model=model,
    data=eval_dataset,
    model_type="classifier",
    evaluators=[accuracy_judge],
    extra_metrics=[custom_metric]
)

# 4. Create HEM for DeltaOne comparison
hem = create_hem_from_mlflow_run(results.run_id)

# 5. DeltaOne detection (Hokusai-specific)
deltaone_result = deltaone_evaluator.evaluate(
    model_id="XRAY-123",
    current_hem=hem
)
```

### 3. DeltaOne Detection Rules

**UNCHANGED** - This is Hokusai-specific business logic

- **Threshold**: ≥1.0 percentage point improvement
- **Statistical Significance**: 95% CI must exclude baseline
- **Dataset Integrity**: Exact hash match required
- **Cooldown**: 24-hour minimum between evaluations
- **Minimum Samples**: 800 examples (configurable)

### 4. Lightweight Provider Adapters

**SIMPLIFIED**: Adapters now just convert external framework results to MLflow format

```python
class OpenAIEvalsAdapter:
    """Thin wrapper to run OpenAI Evals and log to MLflow."""

    def run(self, eval_spec: str, model_ref: str) -> str:
        """
        Run OpenAI eval and return MLflow run ID.

        Returns:
            MLflow run_id with results logged
        """
        # 1. Run OpenAI eval
        raw_results = subprocess.run(
            ["oaieval", model_ref, eval_spec],
            capture_output=True
        )

        # 2. Start MLflow run and log results
        with mlflow.start_run() as run:
            # Log metrics
            for metric, value in parse_results(raw_results).items():
                mlflow.log_metric(metric, value)

            # Log raw output as artifact
            mlflow.log_text(raw_results.stdout, "openai_eval_output.txt")

            # Tag as OpenAI eval
            mlflow.set_tag("eval:provider", "openai_evals")
            mlflow.set_tag("eval:spec", eval_spec)

        return run.info.run_id
```

## Technical Standards

### Python Version & Dependencies

```python
# requirements.txt additions for MLflow 3.4
mlflow>=3.4.0  # REQUIRED for make_judge and evaluation datasets
opentelemetry-api>=1.20.0  # For tracing
opentelemetry-sdk>=1.20.0
pydantic>=2.0.0
```

### MLflow 3.4 Integration Patterns

#### Pattern 1: Using Evaluation Datasets

```python
from mlflow.data import from_pandas
import mlflow

# Register evaluation dataset (do once)
eval_df = pd.read_csv("xray_test.csv")
dataset = from_pandas(eval_df, source="xray-nih-test")

# Log dataset to MLflow
with mlflow.start_run(run_name="Register xray-nih v1.4.0"):
    mlflow.log_input(dataset, context="evaluation")
    # Compute and log hash for DeltaOne comparison
    dataset_hash = compute_dataset_hash(eval_df)
    mlflow.set_tag("dataset:hash", dataset_hash)
    mlflow.set_tag("dataset:version", "1.4.0")

# Later: Load dataset for evaluation
eval_dataset = mlflow.data.load_dataset(run_id, context="evaluation")
```

#### Pattern 2: Creating Custom Judges

```python
from mlflow.genai import make_judge

# Simple field-based judge
quality_judge = make_judge(
    name="response_quality",
    instructions=(
        "Rate the quality of {{ outputs }} on a scale of 1-5. "
        "Consider accuracy, clarity, and completeness."
    ),
    model="anthropic:/claude-opus-4-1-20250805",
    parameters={"temperature": 0.0}  # Deterministic for reproducibility
)

# Register judge for reuse
mlflow.genai.register_judge(
    judge=quality_judge,
    name="hokusai/xray_quality_v1"
)
```

#### Pattern 3: Custom Metrics with make_metric

```python
from mlflow.metrics import make_metric, MetricValue

def bootstrap_ci_95(predictions, targets):
    """Calculate 95% CI via bootstrap for DeltaOne."""
    from scipy.stats import bootstrap

    def statistic(y_true, y_pred):
        return accuracy_score(y_true, y_pred)

    ci = bootstrap(
        (targets, predictions),
        statistic,
        n_resamples=10000,
        confidence_level=0.95
    )

    return MetricValue(
        scores={
            "ci_lower": ci.confidence_interval.low,
            "ci_upper": ci.confidence_interval.high
        }
    )

# Create metric
bootstrap_metric = make_metric(
    eval_fn=bootstrap_ci_95,
    greater_is_better=False,
    name="bootstrap_ci_95"
)

# Use in evaluation
results = mlflow.evaluate(
    model=model,
    data=eval_dataset,
    extra_metrics=[bootstrap_metric]
)
```

#### Pattern 4: OpenTelemetry Tracing

```python
from opentelemetry import trace
from mlflow.tracing import trace_call

# Automatic tracing for evaluation
@trace_call(name="hokusai_evaluation")
def run_evaluation(model_id: str, dataset_id: str):
    with mlflow.start_run():
        # MLflow 3.4 automatically exports spans to OpenTelemetry
        results = mlflow.evaluate(
            model=load_model(model_id),
            data=load_dataset(dataset_id)
        )
    return results
```

### DeltaOne Evaluator Implementation

**Enhanced to use MLflow results**

```python
class DeltaOneEvaluator:
    def __init__(self, mlflow_client: MlflowClient, redis_client: Redis):
        self.mlflow = mlflow_client
        self.redis = redis_client

    def evaluate(
        self,
        model_id: str,
        current_run_id: str
    ) -> DeltaOneResult:
        """
        Evaluate if current run achieves DeltaOne.

        Args:
            model_id: Hokusai model ID
            current_run_id: MLflow run ID with evaluation results

        Returns:
            DeltaOneResult with achievement status
        """
        # 1. Check cooldown
        if not self._check_cooldown(model_id):
            raise CooldownError("24-hour cooldown not met")

        # 2. Get current results from MLflow
        current_run = self.mlflow.get_run(current_run_id)
        current_hem = self._create_hem_from_run(current_run)

        # 3. Get baseline results
        baseline_hem = self._get_baseline_hem(model_id)

        # 4. Verify comparability (dataset hash match)
        if not current_hem.is_comparable_to(baseline_hem):
            raise ValueError("Dataset hash mismatch - not comparable")

        # 5. Calculate delta
        delta_pp = self._calculate_delta_pp(
            baseline_hem.primary_metric["value"],
            current_hem.primary_metric["value"],
            current_hem.primary_metric["unit"]
        )

        # 6. Check statistical significance
        significant = self._check_significance(
            current_hem,
            baseline_hem
        )

        # 7. DeltaOne achieved?
        achieved = delta_pp >= 1.0 and significant

        if achieved:
            # Trigger token minting
            self._trigger_token_mint(model_id, delta_pp, current_hem)
            # Update cooldown
            self._set_cooldown(model_id)

        return DeltaOneResult(
            achieved=achieved,
            delta_pp=delta_pp,
            significant=significant,
            current_hem=current_hem,
            baseline_hem=baseline_hem
        )

    def _create_hem_from_run(self, run: Run) -> HokusaiEvaluationManifest:
        """Create HEM from MLflow run."""
        return HokusaiEvaluationManifest(
            schema="hokusai.eval.manifest/v2",
            mlflow_run_id=run.info.run_id,
            dataset={
                "hash": run.data.tags.get("dataset:hash"),
                "version": run.data.tags.get("dataset:version"),
                "name": run.data.tags.get("dataset:name"),
                "n_examples": int(run.data.tags.get("dataset:n_examples", 0))
            },
            primary_metric={
                "name": run.data.tags.get("primary_metric"),
                "value": run.data.metrics.get(run.data.tags["primary_metric"]),
                "direction": run.data.tags.get("metric:direction", "maximize"),
                "unit": run.data.tags.get("metric:unit", "ratio")
            },
            uncertainty={
                "method": "bootstrap",
                "ci95": [
                    run.data.metrics.get("bootstrap_ci_95.ci_lower"),
                    run.data.metrics.get("bootstrap_ci_95.ci_upper")
                ]
            }
        )
```

## Revised File Structure

```
src/evaluation/
├── __init__.py
├── manifest.py              # HEM dataclass and validation
├── mlflow_wrapper.py        # NEW: Convenience wrappers for mlflow.evaluate()
├── deltaone_evaluator.py    # REVISED: Uses MLflow runs
├── judges/                  # NEW: Custom judge templates
│   ├── __init__.py
│   ├── classification.py    # make_judge templates for classification
│   ├── generation.py        # make_judge templates for text generation
│   └── ranking.py           # make_judge templates for ranking
├── metrics/                 # NEW: Custom metric definitions
│   ├── __init__.py
│   ├── statistical.py       # Bootstrap CI, significance tests
│   └── domain_specific.py   # Medical imaging, etc.
├── adapters/                # NEW: Lightweight provider adapters
│   ├── __init__.py
│   ├── base.py              # Base adapter interface
│   ├── openai_evals.py      # OpenAI Evals → MLflow
│   ├── lm_eval.py           # LM Eval Harness → MLflow
│   └── native.py            # Direct MLflow evaluation
└── datasets/                # NEW: Dataset management helpers
    ├── __init__.py
    ├── loader.py            # Load and hash datasets
    └── registry.py          # Register datasets to MLflow
```

## Implementation Priorities

### Phase 1: Core MLflow 3.4 Integration (CRITICAL)
1. ✅ **Upgrade to MLflow 3.4** and verify all features work
2. ✅ **Create evaluation dataset workflow** using MLflow's native datasets
3. ✅ **Implement custom metrics** including bootstrap CI for DeltaOne
4. ✅ **Create judge templates** using make_judge for common evaluation types
5. ✅ **Update DeltaOne evaluator** to work with MLflow runs

### Phase 2: Hokusai Integration
6. ✅ **Implement HEM v2** with MLflow run references
7. ✅ **Create API endpoints** for evaluation triggering
8. ✅ **Implement evaluation queue** for async processing
9. ✅ **Add cost controls** and estimation
10. ✅ **Webhook notifications** for DeltaOne events

### Phase 3: Provider Adapters (OPTIONAL)
11. ⚠️ **OpenAI Evals adapter** (only if external evaluation needed)
12. ⚠️ **LM Eval Harness adapter** (only if benchmark comparison needed)

### Phase 4: Enterprise Features
13. ✅ **CLI tool** with MLflow backend
14. ✅ **Privacy controls** and PII detection
15. ✅ **Comprehensive testing**
16. ✅ **Documentation and examples**

### Governance Status Update
- 2026-02-23: Implemented HOK-338 privacy and governance controls:
  PII scanning service and APIs, private evaluation mode flag enforcement,
  dataset licensing validation, audit logging endpoints, retention policy
  management, GDPR export/delete/consent helpers, and governance schema migration.

## Success Criteria

Each implementation should:
1. ✅ **Leverage MLflow 3.4 native features** instead of custom implementations
2. ✅ **Include comprehensive tests** (90% coverage)
3. ✅ **Use OpenTelemetry** for tracing via MLflow
4. ✅ **Store datasets** using MLflow Evaluation Datasets
5. ✅ **Use make_judge** for LLM evaluation instead of custom adapters
6. ✅ **Maintain backward compatibility** with existing DeltaOne logic
7. ✅ **Follow MLflow best practices** from official documentation

## Migration from Original Plan

### Removed Issues (MLflow 3.4 provides native functionality)
- ~~Implement Evaluation Registry Configuration System~~ → Use MLflow Evaluation Datasets
- ~~Implement Dataset Manager with Versioning~~ → Use `mlflow.data.Dataset`
- ~~Enhance MLflow Integration for HEM~~ → Already native in MLflow 3.4
- ~~Implement Mock Provider for Testing~~ → Use MLflow's testing framework
- ~~Implement Observability and Metrics~~ → Use OpenTelemetry integration

### Simplified Issues (Use MLflow native + minimal Hokusai logic)
- **Create Evaluation Templates Library** → Use `make_judge()` templates
- **Native Hokusai Provider Wrapper** → Direct `mlflow.evaluate()` calls
- **Comprehensive Test Suite** → Test MLflow integration + DeltaOne logic

### Unchanged Issues (Hokusai-specific business logic)
- **DeltaOne Detection** with statistical rigor
- **Evaluation Queue Management** for async processing
- **API Endpoints** for REST access
- **CLI Tool** for command-line usage
- **Webhook Notifications** for DeltaOne events
- **Privacy and Governance Controls**
- **User Documentation**

## Questions to Answer Before Implementation

For each implementation task, consider:
1. **Can we use MLflow 3.4 native features?** Don't build custom if MLflow provides it
2. **How does this integrate with MLflow runs?** Everything should link to MLflow
3. **Is this Hokusai-specific business logic?** Only build what's unique to us
4. **How to maintain backward compatibility?** Existing DeltaOne logic must work
5. **What's the migration path?** Smooth transition from current system

## Resources

- **MLflow 3.4 Documentation**: https://mlflow.org/docs/latest/genai/eval-monitor/
- **make_judge API**: https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/make-judge/
- **Evaluation Datasets**: https://mlflow.org/docs/latest/ml/dataset/
- **OpenTelemetry Integration**: https://mlflow.org/docs/latest/genai/eval-monitor/
- **Repository**: hokusai-data-pipeline
- **MLflow UI**: https://registry.hokus.ai

---

## Summary of Changes from Original Plan

**Key Philosophy Shift**:
- **Before**: Build comprehensive evaluation framework from scratch
- **After**: Leverage MLflow 3.4 native capabilities + add Hokusai-specific business logic

**Complexity Reduction**:
- **Lines of Custom Code**: ~5000 → ~1500 (70% reduction)
- **Custom Providers**: 3 → 2 optional lightweight adapters
- **Custom Infrastructure**: Heavy → Minimal (use MLflow native)

**Improved Capabilities**:
- ✅ Better observability via OpenTelemetry
- ✅ Standardized evaluation framework
- ✅ Built-in versioning and tracking
- ✅ Enterprise-grade features from MLflow
- ✅ Easier maintenance and upgrades

This revision significantly simplifies implementation while providing better functionality by leveraging MLflow 3.4's mature evaluation ecosystem.
