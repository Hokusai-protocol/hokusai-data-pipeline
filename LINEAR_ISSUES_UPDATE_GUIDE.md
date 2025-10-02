# Linear Issues Update Guide - MLflow 3.4 Migration

This document outlines required changes to Linear issues in the "Implement custom evals" milestone following the revision of openai_evals_plan.md to leverage MLflow 3.4 native capabilities.

## Summary of Changes

**Philosophy Shift**: From "build everything custom" to "leverage MLflow 3.4 native features + add Hokusai-specific business logic"

**Impact**:
- **5 issues to DELETE** (MLflow provides natively)
- **4 issues to SIGNIFICANTLY SIMPLIFY** (reduce scope, use MLflow)
- **9 issues to KEEP** (Hokusai-specific business logic)

---

## Issues to DELETE

These issues are no longer needed because MLflow 3.4 provides the functionality natively.

### ❌ Issue #19: Create Evaluation Registry Configuration System
**Reason for Deletion**: MLflow 3.4 Evaluation Datasets provide native registry functionality

**Migration Path**:
- Use `mlflow.data.Dataset` for dataset registration
- Use MLflow's native evaluation dataset storage
- No custom YAML registry needed

**Action**: **DELETE THIS ISSUE**

---

### ❌ Issue #21: Implement Dataset Manager with Versioning and Integrity
**Reason for Deletion**: MLflow 3.4 provides `mlflow.data.Dataset` with built-in versioning

**What We Still Need**:
- Hash computation for DeltaOne comparison (simple utility function)
- This is covered in the revised "HEM Specification" issue

**Migration Path**:
```python
# Instead of custom dataset manager
from mlflow.data import from_pandas
dataset = from_pandas(eval_df, source="xray-nih-test")
mlflow.log_input(dataset, context="evaluation")
```

**Action**: **DELETE THIS ISSUE**

---

### ❌ Issue #12: Enhance MLflow Integration for HEM
**Reason for Deletion**: MLflow 3.4 natively supports:
- Structured logging via `mlflow.log_dict()`
- Consistent tagging
- Artifact management
- Evaluation datasets

**What We Still Need**:
- HEM creation from MLflow runs (covered in revised HEM issue)

**Migration Path**: Use MLflow's native APIs directly

**Action**: **DELETE THIS ISSUE**

---

### ❌ Issue #16: Implement Mock Provider for Testing
**Reason for Deletion**: MLflow 3.4 provides comprehensive testing framework

**Migration Path**:
- Use `mlflow.evaluate()` with mock data
- Use MLflow's built-in testing utilities
- Standard pytest mocking for DeltaOne-specific logic

**Action**: **DELETE THIS ISSUE**

---

### ❌ Issue #6: Implement Observability and Metrics
**Reason for Deletion**: MLflow 3.4 provides native OpenTelemetry integration

**Migration Path**:
- Use MLflow's built-in OpenTelemetry export
- Leverage automatic span tracking
- Use `mlflow.tracing.trace_call` decorator

**Code Example**:
```python
from mlflow.tracing import trace_call

@trace_call(name="hokusai_evaluation")
def run_evaluation(model_id: str, dataset_id: str):
    # Automatically traced and exported to OpenTelemetry
    results = mlflow.evaluate(model, data)
    return results
```

**Action**: **DELETE THIS ISSUE**

---

## Issues to SIGNIFICANTLY SIMPLIFY

These issues are still needed but should be simplified to use MLflow 3.4 features.

### ⚠️ Issue #18: Implement OpenAI Evals Provider Adapter
**Current Description**: Create comprehensive adapter for OpenAI Evals framework

**REVISED Description**:

**Title**: Create Lightweight OpenAI Evals Adapter (OPTIONAL)

**Description**: Create a thin wrapper to run OpenAI Evals and log results to MLflow. This is OPTIONAL and only needed if we want to compare against OpenAI's standard benchmarks.

**Acceptance Criteria**:
- Thin adapter that runs `oaieval` CLI
- Logs results to MLflow run
- Returns MLflow run_id
- ~100 lines of code (not 500+)

**Technical Details**:
```python
class OpenAIEvalsAdapter:
    def run(self, eval_spec: str, model_ref: str) -> str:
        # 1. Run oaieval CLI
        result = subprocess.run(["oaieval", model_ref, eval_spec])

        # 2. Log to MLflow
        with mlflow.start_run() as run:
            mlflow.log_metrics(parse_results(result))
            mlflow.log_text(result.stdout, "output.txt")
            mlflow.set_tag("eval:provider", "openai_evals")

        return run.info.run_id
```

**Priority**: LOW (only implement if needed)

**Action**: **UPDATE ISSUE WITH REVISED DESCRIPTION**

---

### ⚠️ Issue #17: Create Native Hokusai Provider Wrapper
**Current Description**: Wrap existing evaluation system as provider

**REVISED Description**:

**Title**: Integrate Existing Hokusai Evaluation with MLflow 3.4

**Description**: Update existing `src/modules/evaluation.py` to use `mlflow.evaluate()` directly instead of custom provider abstraction.

**Acceptance Criteria**:
- Call `mlflow.evaluate()` with existing model evaluator
- Create custom metrics using `mlflow.metrics.make_metric()`
- Log results to MLflow runs
- Maintain backward compatibility
- ~200 lines of changes (not new provider)

**Technical Details**:
```python
from mlflow.metrics import make_metric

# Convert existing metrics to MLflow format
accuracy_metric = make_metric(
    eval_fn=compute_accuracy,
    greater_is_better=True,
    name="accuracy"
)

# Use mlflow.evaluate directly
results = mlflow.evaluate(
    model=hokusai_model,
    data=eval_dataset,
    model_type="classifier",
    extra_metrics=[accuracy_metric, precision_metric, recall_metric]
)
```

**Dependencies**: None

**Action**: **UPDATE ISSUE WITH REVISED DESCRIPTION**

---

### ⚠️ Issue #9: Create Evaluation Templates Library
**Current Description**: Build library of evaluation templates for common model types

**REVISED Description**:

**Title**: Create MLflow Judge Templates for Common Evaluation Types

**Description**: Create reusable `make_judge()` templates for common Hokusai model evaluation scenarios using MLflow 3.4's native judge API.

**Acceptance Criteria**:
- Create `src/evaluation/judges/` directory
- Classification judge template using `make_judge()`
- Generation judge template (BLEU, ROUGE via make_judge)
- Ranking judge template (NDCG via make_judge)
- All judges registered to MLflow for reuse
- Documentation for each template

**Technical Details**:
```python
# src/evaluation/judges/classification.py
from mlflow.genai import make_judge

def create_classification_judge(task_description: str):
    return make_judge(
        name=f"classification_{task_description}",
        instructions=(
            f"Evaluate if {{{{ outputs }}}} correctly classifies "
            f"the input for task: {task_description}. "
            f"Compare against ground truth in {{{{ expectations }}}}."
        ),
        model="anthropic:/claude-opus-4-1-20250805",
        parameters={"temperature": 0.0}
    )

# Register for reuse
mlflow.genai.register_judge(
    judge=create_classification_judge("medical_diagnosis"),
    name="hokusai/medical_classification_v1"
)
```

**Estimated Effort**: 2-3 days (was 1 week)

**Action**: **UPDATE ISSUE WITH REVISED DESCRIPTION**

---

### ⚠️ Issue #10: Create Comprehensive Test Suite
**Current Description**: Build comprehensive test coverage for all HEK components

**REVISED Description**:

**Title**: Create Test Suite for DeltaOne Integration with MLflow 3.4

**Description**: Build comprehensive test coverage focusing on Hokusai-specific business logic and MLflow 3.4 integration points.

**Acceptance Criteria**:
- Unit tests for DeltaOne detection (90% coverage)
- Integration tests for MLflow evaluation workflow
- Test bootstrap CI calculations
- Test dataset hash verification
- Test cooldown management
- Test HEM creation from MLflow runs
- Mock MLflow API for isolated testing

**Test Focus Areas**:
1. **DeltaOne Logic** (Hokusai-specific):
   - Statistical significance testing
   - Cooldown enforcement
   - Token minting triggers
   - Dataset hash matching

2. **MLflow Integration**:
   - Evaluation dataset loading
   - Custom metrics registration
   - Judge template creation
   - Run ID retrieval and parsing

3. **End-to-End Workflows**:
   - Complete evaluation + DeltaOne check
   - Queue processing
   - Webhook notifications

**NOT Testing** (MLflow already tested):
- ❌ MLflow's evaluate() function
- ❌ make_judge() functionality
- ❌ Dataset versioning
- ❌ OpenTelemetry tracing

**Estimated Effort**: 3-4 days (was 1 week)

**Action**: **UPDATE ISSUE WITH REVISED DESCRIPTION**

---

## Issues to KEEP (Unchanged or Minor Updates)

These issues remain as-is because they implement Hokusai-specific business logic that MLflow doesn't provide.

### ✅ Issue #20: Enhance DeltaOne Detection with Statistical Rigor
**Status**: KEEP AS-IS

**Minor Update Needed**:
- Add note about using MLflow runs as input
- Update code example to show `current_run_id` parameter

**Revised Acceptance Criteria** (add this):
- Accept `mlflow_run_id` as input instead of custom EvalResult
- Extract metrics from MLflow run via `mlflow_client.get_run()`
- Create HEM from MLflow run data

**Action**: **ADD MINOR UPDATE TO ISSUE**

---

### ✅ Issue #22: Implement Hokusai Evaluation Manifest (HEM) Specification
**Status**: KEEP WITH UPDATES

**Update Needed**:
- Add `mlflow_run_id` field to HEM schema
- Add `mlflow_dataset_id` field for dataset reference
- Add method to create HEM from MLflow run

**Revised Acceptance Criteria**:
- Implement HEM v2 schema with MLflow references
- Add `create_hem_from_mlflow_run(run_id)` function
- Maintain `is_comparable_to()` method for DeltaOne
- Integrate with MLflow's `log_dict()` for storage

**Action**: **UPDATE ISSUE WITH MLflow INTEGRATION DETAILS**

---

### ✅ Issue #23: Create Provider-Agnostic Evaluation Interface
**Status**: KEEP WITH SIMPLIFICATION

**Update Needed**:
- Simplify to just define adapter interface
- Adapters return MLflow run_id, not custom EvalResult
- Remove heavy abstraction

**Revised Technical Details**:
```python
class EvalAdapter(Protocol):
    """Lightweight adapter for external evaluation frameworks."""

    def run(self, eval_spec: str, model_ref: str) -> str:
        """Run evaluation and return MLflow run_id."""
        pass
```

**Action**: **SIMPLIFY INTERFACE DEFINITION**

---

### ✅ Issue #13: Implement Evaluation Queue Management
**Status**: KEEP AS-IS

This is Hokusai-specific async processing logic. No changes needed.

**Action**: **NO CHANGE**

---

### ✅ Issue #14: Create Evaluation API Endpoints
**Status**: KEEP AS-IS

REST API layer is Hokusai-specific. No changes needed.

**Action**: **NO CHANGE**

---

### ✅ Issue #15: Implement Enhanced CLI Tool with Reproducibility
**Status**: KEEP WITH MINOR UPDATE

**Update Needed**: CLI should call MLflow-based evaluation

**Add to Technical Details**:
```python
# CLI internally uses mlflow.evaluate()
@click.command()
def eval_run(model_id, dataset_id):
    # Uses MLflow backend
    results = mlflow.evaluate(...)
    hem = create_hem_from_run(results.run_id)
    deltaone_result = deltaone_evaluator.evaluate(model_id, results.run_id)
```

**Action**: **ADD NOTE ABOUT MLflow BACKEND**

---

### ✅ Issue #11: Add Webhook Notifications for DeltaOne Events
**Status**: KEEP AS-IS

Hokusai-specific business logic. No changes needed.

**Action**: **NO CHANGE**

---

### ✅ Issue #7: Add Privacy and Governance Controls
**Status**: KEEP AS-IS

Enterprise compliance features are Hokusai-specific. No changes needed.

**Action**: **NO CHANGE**

---

### ✅ Issue #8: Write User Documentation and Migration Guide
**Status**: KEEP WITH UPDATE

**Update Needed**: Documentation should cover MLflow 3.4 usage

**Add to Documentation Sections**:
- How to use MLflow 3.4 evaluation datasets
- How to create custom judges with make_judge()
- How to run evaluations using mlflow.evaluate()
- Migration from custom evaluation to MLflow-based

**Action**: **ADD MLflow 3.4 DOCUMENTATION SECTIONS**

---

## New Issue to CREATE

### ➕ NEW: Upgrade to MLflow 3.4 and Verify Features

**Title**: Upgrade to MLflow 3.4 and Verify GenAI Features

**Description**: Upgrade MLflow from 2.9.2 to 3.4.0 and verify all new GenAI evaluation features work correctly.

**Acceptance Criteria**:
- Update requirements.txt: `mlflow>=3.4.0`
- Install and test `mlflow.genai.make_judge()`
- Test evaluation datasets functionality
- Test `mlflow.evaluate()` with custom metrics
- Verify OpenTelemetry integration works
- Run existing tests to ensure no breaking changes
- Document any migration issues

**Priority**: CRITICAL (must be done first)

**Estimated Effort**: 1-2 days

**Dependencies**: None (this is Phase 1, step 1)

**Action**: **CREATE NEW ISSUE**

---

## Implementation Order

Based on the revised plan, implement in this order:

### Phase 1: Core MLflow 3.4 Integration
1. **NEW** - Upgrade to MLflow 3.4 ✅
2. #22 (UPDATED) - Implement HEM v2 with MLflow integration
3. **Create custom metrics** (new micro-issue for bootstrap CI)
4. #9 (SIMPLIFIED) - Create judge templates
5. #20 (UPDATED) - Update DeltaOne evaluator for MLflow runs

### Phase 2: Hokusai Integration
6. #17 (SIMPLIFIED) - Integrate existing evaluation with MLflow
7. #14 - Create API endpoints
8. #13 - Implement queue management
9. #15 (UPDATED) - CLI tool with MLflow backend
10. #11 - Webhook notifications

### Phase 3: Optional Provider Adapters
11. #18 (OPTIONAL/SIMPLIFIED) - OpenAI Evals thin adapter
12. #23 (SIMPLIFIED) - Provider interface definition

### Phase 4: Enterprise Features
13. #15 - CLI tool enhancements
14. #7 - Privacy and governance
15. #10 (SIMPLIFIED) - Comprehensive testing
16. #8 (UPDATED) - Documentation

---

## Summary Statistics

**Original Plan**:
- Total Issues: 18
- Custom LOC: ~5,000
- Estimated Time: 8-10 weeks

**Revised Plan**:
- Issues Deleted: 5 ❌
- Issues Simplified: 4 ⚠️
- Issues Kept: 9 ✅
- New Issues: 1 ➕
- **Total Active Issues: 14**
- **Custom LOC: ~1,500** (70% reduction)
- **Estimated Time: 4-5 weeks** (50% reduction)

**Complexity Reduction**:
- No custom dataset manager (use MLflow)
- No custom evaluation registry (use MLflow)
- No custom observability (use OpenTelemetry)
- Thin adapters instead of heavy providers
- Focus on DeltaOne business logic only

**Improved Capabilities**:
- Enterprise-grade evaluation framework from MLflow
- Better observability via OpenTelemetry
- Standardized evaluation datasets
- Built-in versioning and tracking
- Easier maintenance and upgrades

---

## Action Items for Linear

1. **DELETE** issues: #6, #12, #16, #19, #21
2. **CREATE** new issue: "Upgrade to MLflow 3.4"
3. **UPDATE** issues: #9, #10, #17, #18 with simplified descriptions
4. **MINOR UPDATES** to: #8, #15, #20, #22, #23
5. **NO CHANGES** to: #7, #11, #13, #14

Total Linear actions: 16 (5 deletes + 1 create + 10 updates)
