# Model 30 Typed Routing Input Contract

Model 30 is served at `POST /api/v1/models/30/predict` with the public schema
`technical_task_router_inputs/v2`.

## Request Shape

Send typed fields under `inputs`. The API accepts both camelCase and snake_case
field names for backward compatibility; SDKs should emit camelCase.

```json
{
  "inputs": {
    "task": {
      "description": "Refactor billing webhook retry handling",
      "taskType": "refactor",
      "language": "python",
      "framework": "fastapi",
      "repoType": "monorepo"
    },
    "routing": {
      "availableModels": ["gpt-5.4", "claude-sonnet-4-6"],
      "availablePlannerModels": ["claude-sonnet-4-6"],
      "availableCoderModels": ["gpt-5.4", "claude-sonnet-4-6"],
      "availableReviewerModels": ["claude-sonnet-4-6"],
      "preferredModels": ["claude-sonnet-4-6"],
      "objective": "highest_reliability",
      "maxCostUsd": 0.5,
      "maxLatencySeconds": 30,
      "prioritizeQuality": true,
      "prioritizeSpeed": false
    },
    "context": {
      "domain": "payments",
      "repoSizeBucket": "large",
      "requiresTests": true,
      "riskLevel": "medium",
      "fileCount": 6,
      "estimatedComplexity": "medium",
      "securitySensitive": true
    },
    "workflow": {
      "surface": "wavemill",
      "stages": ["plan", "code", "review"],
      "executionEnvironment": "ci",
      "humanReviewRequired": true
    },
    "metadata": {
      "externalTaskId": "task-123",
      "runId": "run-456",
      "integrationVersion": "2026.05",
      "idempotencyKey": "idem-789"
    }
  }
}
```

## Candidate-Pool Policy

Candidate pools are typed arrays, never CSV strings in metadata.

Omitting all `available*Models` fields means unconstrained global ranking.
Explicit empty arrays are rejected by schema validation.

`availableModels` is the general candidate pool. Role-specific pools override it
for that role; if a role-specific field is omitted, that role falls back to
`availableModels`.

Two or more unique models in an effective role pool are ranking-eligible. A
singleton effective role pool is accepted as non-ranking for that role. A request
where every constrained role is singleton is `non_ranking`; a mix of singleton
and multi-model role pools is `partially_ranking`.

## Contribution Fidelity

Contribution rows with two or more unique `allowed_models` are
`training_eligible` when the rest of the success-under-budget fields are present.
Rows with a singleton `allowed_models` pool are classified as `non_ranking`.
They are accepted for telemetry, returned in `rowFidelityTiers`, and excluded
from Model 30 ranking/training assembly.

Rows with route/model identity but missing cost or budget remain `partial`.
Rows missing route identity or model selection are `invalid`.

## Compatibility

Existing Model 30 `/predict` callers using snake_case fields continue to work.
Existing Model 21 `/predict` callers are unaffected because this contract is
only used by the Model 30 MLflow registry entry.
