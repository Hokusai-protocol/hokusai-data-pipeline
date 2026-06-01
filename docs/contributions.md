# Contribution Submission Endpoint

`POST /api/v1/models/{model_id}/contributions`

Owned by `hokusai-data-pipeline`. Accepts contribution batches from both
Wavemill's contribution drain and the hokusai-site contribution form so that
both can use the same upstream path without a coordinated multi-repo deploy.

## Authentication

- Bearer token in `Authorization`, or `X-API-Key`, validated by
  `APIKeyAuthMiddleware`.
- 401 if absent or invalid.
- Wavemill resolves the bearer token from the configured `endpointTokenEnv` or
  falls back to `HOKUSAI_API_KEY`.

## Accepted envelopes

### Wavemill drain

```jsonc
{
  "rows": [<ContributionRow>...],
  "metadata": { "idempotency_key": "<batch key>" }
}
```

`Idempotency-Key` is also forwarded as a header by Wavemill; the route prefers
the header but falls back to `metadata.idempotency_key`.

### hokusai-site forward

```jsonc
{
  "modelId": 30,
  "benchmarkSpecId": "spec-abc",
  "rows": [...],
  "schemaVersion": "technical_task_router_row/v1",
  "templateId": "tmpl-1"
}
```

- `modelId` (when present) must match the path `model_id`. Mismatches return
  HTTP 400.

## Row shapes

Each entry in `rows` is accepted as a JSON object. Two shapes are recognized
for observability counts (`rowSchemaCounts`):

1. **Technical task router row v1** — `schema_version =
   "technical_task_router_row/v1"`, plus `task_descriptor`, `allowed_models`,
   `selected_models`, `success_under_budget`, `completion_result`,
   `observed_at`.
2. **Submit-data legacy row** — `success_under_budget` plus optional `inputs`,
   `actual_cost_usd`, `wall_clock_seconds`, `task_id`, `harness`.

Other shapes are accepted and counted as `generic` or
`unknown:<schema_version>` for log observability.

Forbidden raw prompt-like keys (`prompt`, `messages`, `task_text`,
`raw_input`, `eval_record`, `originalprompt`, `original_prompt`,
`description`, `issue_body`) are rejected with HTTP 422.

`rows` must contain between 1 and 10,000 entries.

## Response

HTTP 202 on accepted ingestion:

```json
{
  "status": "accepted",
  "submissionId": "<uuid>",
  "jobId": "<uuid>",
  "jobIds": ["<uuid>"],
  "submittedRows": 1,
  "modelId": 30,
  "idempotencyKey": "<batch key or null>",
  "rowSchemaCounts": { "technical_task_router_row_v1": 1 }
}
```

Response header `X-Request-ID` is set for log correlation.

Wavemill consumes `jobIds` (preferred), `jobId`, `submissionId`, and the
optional `tokenReward`; any 2xx is treated as accepted.

## Error behavior

| Status | Cause |
| --- | --- |
| 400 | Body `modelId` does not match the route `model_id`. |
| 401 | Missing or invalid API key. |
| 404 | `model_id` is not in `MODEL_CONFIGS`. |
| 422 | Empty/missing `rows`, forbidden row key, or other schema violation. |

Validation failures emit a structured `validation_422` log with
`X-Request-ID` (no row payload values).

## Operational notes

- "Accepted" means ingestion was accepted, not that a token reward was awarded.
- This route does not yet persist contributions durably. Wavemill stores its
  own ledger; this endpoint logs the acceptance with the submission id,
  idempotency key, and per-row-schema counts.
- For the hokusai-site → data-pipeline forward to be active, the site must set
  `HOKUSAI_CONTRIBUTION_UPSTREAM_PATH=/api/v1/models/:modelId/contributions`.
- After deployment, Wavemill's dead-letter queue can be replayed to recover
  prior 404-rejected submissions.
