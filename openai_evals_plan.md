⏺ Hokusai Evals Kit (HEK) - Implementation Context Document

  Project Overview

  Mission

  Build a provider-agnostic evaluation framework for Hokusai that integrates OpenAI Evals (and other evaluation frameworks) while preserving the existing
  DeltaOne token economics and MLflow infrastructure.

  Key Business Requirements

  - DeltaOne Detection: Automatically detect and reward ≥1 percentage point improvements in model performance
  - Token Economics: Performance improvements trigger token minting (1pp = 1 DeltaOne token)
  - Anti-Gaming: Statistical rigor and cooldown periods prevent manipulation
  - Provider Agnostic: Support multiple evaluation frameworks (OpenAI Evals, LM Eval Harness, native)
  - Enterprise Ready: Reproducible, auditable, with cost controls

  Architecture Overview

  System Architecture

  ┌─────────────────────────────────────────────────────────────┐
  │                        CLI / API Layer                       │
  │  (hoku eval command)            (REST endpoints)             │
  └─────────────┬───────────────────────────┬───────────────────┘
                │                           │
  ┌─────────────▼───────────────────────────▼───────────────────┐
  │                    Evaluation Orchestrator                   │
  │  - Provider Registry                                         │
  │  - Manifest Generation (HEM)                                 │
  │  - Dataset Management                                        │
  └─────────────┬───────────────────────────┬───────────────────┘
                │                           │
  ┌─────────────▼───────────┐ ┌────────────▼──────────────────┐
  │   Provider Adapters      │ │     DeltaOne Evaluator        │
  │  - OpenAI Evals         │ │  - Statistical Significance    │
  │  - Native Hokusai       │ │  - Cooldown Management        │
  │  - Mock (testing)       │ │  - Token Minting Trigger      │
  └─────────────┬───────────┘ └────────────┬──────────────────┘
                │                           │
  ┌─────────────▼───────────────────────────▼───────────────────┐
  │                    Storage & Tracking                        │
  │  - MLflow (metrics, artifacts)                              │
  │  - MinIO/S3 (datasets, generations)                         │
  │  - PostgreSQL (metadata)                                    │
  │  - Redis (queue, cache)                                     │
  └──────────────────────────────────────────────────────────────┘

  Existing Codebase Structure

  hokusai-data-pipeline/
  ├── src/
  │   ├── api/                    # FastAPI application
  │   │   ├── routes/             # API endpoints
  │   │   └── middleware/         # Auth, rate limiting
  │   ├── evaluation/             # NEW: Evaluation system
  │   │   ├── interfaces.py      # Provider protocol
  │   │   ├── manifest.py        # HEM specification
  │   │   ├── providers/         # Provider implementations
  │   │   ├── registry.yaml      # Eval configurations
  │   │   └── deltaone_evaluator.py  # EXISTING: Enhanced
  │   ├── modules/               
  │   │   └── evaluation.py      # EXISTING: Current evaluator
  │   └── services/
  │       └── model_registry.py  # EXISTING: MLflow registry
  ├── tests/
  │   └── unit/
  │       └── test_evaluation_deltaone_evaluator.py  # EXISTING
  └── hokusai-ml-platform/
      └── src/hokusai/core/
          └── registry.py         # EXISTING: Tokenized registry

  Core Concepts

  1. Hokusai Evaluation Manifest (HEM)

  The single source of truth for all evaluations, regardless of provider:

  {
      "schema": "hokusai.eval.manifest/v1",
      "model_id": "XRAY-123",
      "eval_id": "2025-01-09T12:00:00Z-abc123",
      "provider": "openai_evals",
      "dataset": {
          "name": "xray-nih",
          "version": "1.4.0",
          "hash": "sha256:a1b2c3...",  # CRITICAL: Must match for comparison
          "split": "test",
          "n_examples": 1000
      },
      "primary_metric": {
          "name": "accuracy",
          "value": 0.884,
          "direction": "maximize",
          "unit": "ratio"  # or "percentage"
      },
      "metrics": {...},
      "uncertainty": {
          "method": "bootstrap",
          "ci95": [0.874, 0.892]
      }
  }

  2. Provider Interface

  All evaluation providers must implement:

⏺ class EvalProvider(Protocol):
      def run(self, eval_spec: Dict, model_ref: str) -> EvalResult
      def validate_spec(self, eval_spec: Dict) -> bool
      def estimate_cost(self, eval_spec: Dict) -> float

  3. DeltaOne Detection Rules

  - Threshold: ≥1.0 percentage point improvement
  - Statistical Significance: 95% CI must exclude baseline
  - Dataset Integrity: Exact hash match required
  - Cooldown: 24-hour minimum between evaluations
  - Minimum Samples: 800 examples (configurable)

  Technical Standards

  Python Version & Dependencies

  - Python 3.11+
  - Key packages: FastAPI, MLflow, Click, Pydantic, pandas, numpy
  - Testing: pytest with 90% coverage requirement
  - Type hints required for all public functions

  Code Style

  # Import order
  import standard_library
  import third_party
  from typing import Dict, Any, Optional

  from src.local_modules import LocalClass

  # Type hints always
  def process_evaluation(
      model_id: str,
      spec: Dict[str, Any]
  ) -> Optional[HokusaiEvaluationManifest]:
      """Docstring required."""
      pass

  # Error handling
  try:
      result = risky_operation()
  except SpecificException as e:
      logger.error(f"Context: {e}")
      raise ValueError("User-friendly message") from e

  Logging Standards

  import logging
  logger = logging.getLogger(__name__)

  # Log levels:
  logger.debug("Detailed diagnostic info")
  logger.info("Normal flow events")
  logger.warning("Recoverable issues")
  logger.error("Failures requiring attention")

  # Always include context
  logger.info(f"Starting evaluation for model={model_id}, spec={spec_id}")

  Testing Requirements

  # tests/unit/test_<module>.py
  import pytest
  from unittest.mock import Mock, patch

  class TestClassName:
      """Group related tests."""

      def test_happy_path(self):
          """Test normal operation."""
          pass

      def test_edge_cases(self):
          """Test boundaries."""
          pass

      def test_error_handling(self):
          """Test failure modes."""
          with pytest.raises(ValueError):
              function_that_should_fail()

  Integration Points

  MLflow Integration

  import mlflow

  # Always use context manager
  with mlflow.start_run() as run:
      # Log manifest as structured data
      mlflow.log_dict(manifest.to_dict(), "evaluation_manifest.json")

      # Log metrics individually for graphing
      mlflow.log_metric("accuracy", 0.884)

      # Consistent tagging
      mlflow.set_tags({
          "eval:provider": "openai_evals",
          "eval:spec": "classification:v2",
          "dataset:hash": "sha256:abc123..."[:12]
      })

  API Authentication

  from src.middleware.auth import require_auth

  @router.post("/evaluate")
  async def endpoint(request: Request, _=Depends(require_auth)):
      # Auth handled by middleware
      pass

  Database Access

  # Use existing MLflow client
  from mlflow.tracking import MlflowClient
  client = MlflowClient()

  # For Redis (queue)
  import redis
  r = redis.Redis.from_url(os.environ["REDIS_URL"])

  Implementation Patterns

  1. Provider Adapter Pattern

  class OpenAIEvalsProvider(EvalProvider):
      def run(self, eval_spec: Dict, model_ref: str) -> EvalResult:
          # 1. Validate inputs
          if not self.validate_spec(eval_spec):
              raise ValueError("Invalid spec")

          # 2. Run evaluation
          raw_results = self._run_openai_eval(eval_spec, model_ref)

          # 3. Convert to standard format
          return self._convert_to_eval_result(raw_results)

      def _run_openai_eval(self, spec, model):
          # Provider-specific implementation
          pass

  2. Manifest Validation Pattern

⏺ @dataclass
  class HokusaiEvaluationManifest:
      def __post_init__(self):
          # Always validate on creation
          if not self.dataset or "hash" not in self.dataset:
              raise ValueError("Dataset hash required")

          # Set defaults
          if "direction" not in self.primary_metric:
              self.primary_metric["direction"] = "maximize"

      def is_comparable_to(self, other: "HokusaiEvaluationManifest") -> bool:
          # Strict comparison for DeltaOne
          return (
              self.dataset["hash"] == other.dataset["hash"] and
              self.dataset["version"] == other.dataset["version"] and
              self.primary_metric["name"] == other.primary_metric["name"]
          )

  3. Cost Control Pattern

  def run_with_cost_limit(spec: Dict, max_cost: float):
      estimated = estimate_cost(spec)
      if estimated > max_cost:
          raise ValueError(f"Cost ${estimated:.2f} exceeds limit ${max_cost:.2f}")

      # Track actual cost during execution
      with CostTracker() as tracker:
          result = run_evaluation(spec)
          if tracker.current_cost > max_cost:
              raise RuntimeError("Cost limit exceeded during execution")

      return result

  Critical Implementation Details

  Percentage Point Calculation

  # CORRECT: Convert ratio to percentage points
  def calculate_delta_pp(baseline: float, current: float, unit: str) -> float:
      if unit == "ratio":
          # 0.884 - 0.874 = 0.01 * 100 = 1.0pp
          return (current - baseline) * 100.0
      elif unit == "percentage":
          # Already in percentage
          return current - baseline
      else:
          raise ValueError(f"Unknown unit: {unit}")

  Dataset Hash Verification

  def compute_dataset_hash(df: pd.DataFrame) -> str:
      # MUST be deterministic
      df_sorted = df.sort_values(by=list(df.columns))
      content = df_sorted.to_json(orient="records", sort_keys=True)
      return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"

  Idempotency Implementation

  # Use cache with TTL
  idempotency_cache = {}

  async def handle_request(idempotency_key: str, request):
      if idempotency_key in idempotency_cache:
          return idempotency_cache[idempotency_key]

      result = await process(request)
      idempotency_cache[idempotency_key] = result
      return result

  Environment Variables

  # MLflow
  MLFLOW_TRACKING_URI=http://mlflow.hokusai-development.local:5000
  MLFLOW_TRACKING_TOKEN=<api_key>

  # Storage
  S3_BUCKET=hokusai-datasets
  MINIO_ENDPOINT=http://minio:9000

  # Database
  DATABASE_URL=postgresql://user@host:5432/hokusai
  REDIS_URL=redis://localhost:6379

  # API
  API_ENDPOINT=https://api.hokus.ai
  AUTH_SERVICE_URL=https://auth.hokus.ai

  File Naming Conventions

  src/evaluation/
  ├── interfaces.py           # Abstract interfaces
  ├── manifest.py             # Data structures
  ├── provider_registry.py    # Registry management
  ├── providers/
  │   ├── __init__.py
  │   ├── base.py            # Base implementation
  │   ├── openai_evals.py    # Specific providers
  │   └── native.py
  ├── deltaone_evaluator.py   # Business logic
  └── registry.yaml           # Configuration

  Error Handling Guidelines

  User-Facing Errors

  # Be specific and actionable
  raise ValueError(
      f"Dataset '{name}' version {version} not found. "
      f"Available versions: {available_versions}"
  )

  Internal Errors

  # Log full context, return generic message
  logger.error(f"Database query failed: {e}", exc_info=True)
  raise HTTPException(500, "Internal server error")

  Security Considerations

⏺ 1. Never log sensitive data (API keys, PII)
  2. Validate all inputs before processing
  3. Use parameterized queries for database access
  4. Sanitize file paths to prevent traversal attacks
  5. Implement rate limiting on all endpoints
  6. Hash verification for all dataset operations

  Common Pitfalls to Avoid

  1. Don't hardcode URLs - Use environment variables
  2. Don't skip hash verification - Security critical
  3. Don't ignore cooldown periods - Prevents gaming
  4. Don't mix percentage and ratio - Always clarify units
  5. Don't trust provider results - Always validate
  6. Don't forget idempotency - Critical for reliability

  Success Criteria for Implementation

  Each issue implementation should:
  1. ✅ Include comprehensive tests (90% coverage)
  2. ✅ Have proper error handling and logging
  3. ✅ Include type hints for all functions
  4. ✅ Follow the established patterns
  5. ✅ Update relevant documentation
  6. ✅ Pass CI/CD checks
  7. ✅ Be backward compatible

  Example Implementation Reference

  When implementing, refer to these existing files for patterns:
  - Authentication: src/middleware/auth.py
  - MLflow integration: src/services/model_registry.py
  - API routes: src/api/routes/models.py
  - Testing: tests/unit/test_evaluation_deltaone_evaluator.py

  Questions to Answer Before Implementation

  For each issue, consider:
  1. How does this integrate with existing systems?
  2. What are the failure modes and how to handle them?
  3. What metrics/logs are needed for debugging?
  4. How to make this testable?
  5. What documentation needs updating?
  6. Are there security implications?

  Contact & Resources

  - Repository: hokusai-data-pipeline
  - Related Repos: hokusai-infrastructure, hokusai-auth-service
  - Documentation: Internal at docs/
  - MLflow UI: https://registry.hokus.ai
  - API Docs: https://api.hokus.ai/docs

  ---
  Implementation Checklist Template

  When implementing an issue, use this checklist:

  ### Pre-Implementation
  - [ ] Read this context document fully
  - [ ] Review the specific issue requirements
  - [ ] Check dependencies and blockers
  - [ ] Understand integration points

  ### Implementation
  - [ ] Create/modify files per naming conventions
  - [ ] Add comprehensive type hints
  - [ ] Implement error handling
  - [ ] Add logging statements
  - [ ] Follow established patterns

  ### Testing
  - [ ] Write unit tests (90% coverage)
  - [ ] Add integration tests if applicable
  - [ ] Test error conditions
  - [ ] Verify backward compatibility

  ### Documentation
  - [ ] Add/update docstrings
  - [ ] Update README if needed
  - [ ] Add usage examples
  - [ ] Document environment variables

  ### Final Review
  - [ ] Run linter (ruff/black)
  - [ ] Run type checker (mypy)
  - [ ] Verify all tests pass
  - [ ] Check for hardcoded values
  - [ ] Review security implications

  This context document provides everything an LLM needs to understand the project architecture, standards, and requirements for implementing any of the HEK
  issues successfully.


