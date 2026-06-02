# HOK-1982 Investigation

## Summary

- The repeated `503` responses on `POST /api/v1/models/30/contributions` were app-originated, not ALB-originated.
- The live ECS task definition for `hokusai-api-development` does not set `HOKUSAI_CONTRIBUTIONS_BUCKET`.
- In the contribution service, a missing `HOKUSAI_CONTRIBUTIONS_BUCKET` deterministically raises `ContributionPersistenceUnavailableError`, which the router maps to HTTP `503`.
- CloudWatch shows `HTTPCode_Target_5XX_Count` spikes at the exact contribution timestamps, while `HTTPCode_ELB_5XX_Count` remains zero.
- The target group stayed healthy (`HealthyHostCount=1`, `UnHealthyHostCount=0`) and `/health` kept returning `200` from the same task around the failures.
- These retries are not transient. They will keep failing until contribution persistence is configured in the running service.

## Incident Timeline

- `2026-06-01T22:21:06Z`: commit `0fca86d` added the contributions endpoint and S3-backed persistence layer.
- `2026-06-01T22:49:03Z`: PR `#219` merged the contribution endpoint work onto the integration line.
- `2026-06-02T01:25:06.773Z` through `2026-06-02T05:35:17.003Z`: the service still returned `404` on `POST /api/v1/models/30/contributions`, showing callers were probing the new path before the later working route was live in the running service.
- `2026-06-02T12:26:23.122Z`: first retained `503` on `POST /api/v1/models/30/contributions`.
- `2026-06-02T13:10:35.200Z`, `2026-06-02T13:16:08.056Z`, `2026-06-02T14:10:04.623Z`, `2026-06-02T14:48:09.599Z`, `2026-06-02T15:00:39.910Z`: additional retained `503` retries on the same endpoint.
- `2026-06-02T14:35:58.011Z` and `2026-06-02T14:35:58.704Z`: `/health` still returned `200` from healthy API tasks between the failed contribution attempts.

Notes:

- The retained API access logs do not include the Wavemill queue UUIDs `436e5080-c5dc-4e0b-97cb-280e4a444414` and `5f8d66cf-767e-4425-80ed-fbdbec1b6dfb`, so the exact one-to-one mapping from each retained `503` to HOK-1958 vs HOK-1876 could not be reconstructed from service logs alone.
- HOK-1959 did not reach this endpoint and is not part of the `503` root cause.

## Evidence

### E1. The `503`s were target-originated, not ALB-originated

- CloudWatch metric `AWS/ApplicationELB HTTPCode_Target_5XX_Count` for target group `targetgroup/hokusai-reg-api-development/aab4ed4b619b04c0` recorded `Sum=1` at:
  - `2026-06-02T12:26:00Z`
  - `2026-06-02T13:10:00Z`
  - `2026-06-02T13:16:00Z`
  - `2026-06-02T14:10:00Z`
  - `2026-06-02T14:48:00Z`
  - `2026-06-02T15:00:00Z`
- CloudWatch metric `AWS/ApplicationELB HTTPCode_ELB_5XX_Count` for load balancer `app/hokusai-registry-development/78840d73e3e9652e` had no datapoints in the same window.

Interpretation:

- The load balancer was not generating the `503`s.
- The API task returned the `503`s itself.

### E2. The target stayed healthy while the `503`s happened

- CloudWatch metric `HealthyHostCount` for `targetgroup/hokusai-reg-api-development/aab4ed4b619b04c0` stayed at `1` throughout `2026-06-02T12:00:00Z` to `2026-06-02T16:00:00Z`.
- CloudWatch metric `UnHealthyHostCount` for the same target group stayed at `0` throughout the same window.
- `describe-target-groups` shows the live health check path is `/health`, matcher `200`, not `/ready`.

Interpretation:

- This was not an ALB no-healthy-target event.
- Model 30 `/ready` warmup behavior was not controlling target registration for this traffic path.

### E3. The app served healthy traffic around the failed contribution calls

Retained CloudWatch access-log lines from `/ecs/hokusai-api-development`:

- `2026-06-02 12:26:23.122` `POST /api/v1/models/30/contributions` -> `503 Service Unavailable`
- `2026-06-02 13:10:35.200` `POST /api/v1/models/30/contributions` -> `503 Service Unavailable`
- `2026-06-02 13:16:08.056` `POST /api/v1/models/30/contributions` -> `503 Service Unavailable`
- `2026-06-02 14:10:04.623` `POST /api/v1/models/30/contributions` -> `503 Service Unavailable`
- `2026-06-02 14:35:58.011` `GET /health` -> `200 OK`
- `2026-06-02 14:35:58.704` `GET /health` -> `200 OK`
- `2026-06-02 14:48:09.599` `POST /api/v1/models/30/contributions` -> `503 Service Unavailable`
- `2026-06-02 15:00:39.910` `POST /api/v1/models/30/contributions` -> `503 Service Unavailable`

Interpretation:

- The service was up and passing health checks while contribution submissions failed.
- That pattern fits a path-specific configuration problem, not a service-wide outage.

### E4. The running task definition is missing contribution persistence config

`aws ecs describe-task-definition --task-definition hokusai-api-development:312` shows these environment variables on the running container:

- `API_HOST`
- `API_PORT`
- `AUTH_SERVICE_URL`
- `DB_HOST`
- `DB_NAME`
- `DB_PORT`
- `DB_USER`
- `ENVIRONMENT`
- `MLFLOW_MTLS_ENABLED`
- `MLFLOW_SERVER_URL`
- `REDIS_TLS_ENABLED`

It does not include:

- `HOKUSAI_CONTRIBUTIONS_BUCKET`
- `HOKUSAI_CONTRIBUTIONS_PREFIX`

Revision `311` is missing the same variables.

Interpretation:

- The running API service cannot build the default S3 contribution store.
- That matches the deterministic `503` branch in the code.

## Local Code Analysis

Direct `503` mapping:

- `src/api/endpoints/contributions.py:81` catches `ContributionPersistenceUnavailableError` and returns HTTP `503` with `error="persistence_unavailable"`.

Contribution-service paths that can raise `ContributionPersistenceUnavailableError`:

- `src/api/services/contribution_service.py:108` S3 `get_object` failures other than `NoSuchKey` / `404` are wrapped as persistence unavailable.
- `src/api/services/contribution_service.py:121` unreadable persisted JSON is wrapped as persistence unavailable.
- `src/api/services/contribution_service.py:150` S3 `put_object` failures are wrapped as persistence unavailable.
- `src/api/services/contribution_service.py:261` a missing `HOKUSAI_CONTRIBUTIONS_BUCKET` raises persistence unavailable before any S3 call is attempted.

Non-matching hypotheses that were ruled out:

- `src/api/middleware/scanner_filter.py:43` allowlists `/api/v1/`, so the scanner filter does not short-circuit this route.
- `src/middleware/auth.py:27` and downstream auth handling return `401`/`402` style failures, not `503`, for auth and usage-debit rejection cases.
- `src/api/routes/health.py:520` can emit a `503` only when `can_serve_traffic` is false, but the live target group checks `/health` and CloudWatch showed the target remained healthy through the incident window.

## Root Cause

Root cause: app-originated `503` caused by missing contribution persistence configuration in the running API task definition.

Justification:

- The running ECS task definition omitted `HOKUSAI_CONTRIBUTIONS_BUCKET`.
- The contribution service treats that exact condition as `ContributionPersistenceUnavailableError`.
- The router maps that exception to HTTP `503`.
- ALB metrics prove the `5xx` responses came from the target, while target health stayed green.

## Retry-Safety Assessment

Verdict: retries will NOT succeed until `HOKUSAI_CONTRIBUTIONS_BUCKET` is configured in the deployed `hokusai-api-development` service.

Why:

- The failure is deterministic for every contribution request that reaches `ContributionService.store` without an injected store.
- Nothing in the retained evidence suggests a transient S3 outage, target-health flap, or deployment gap during the `503` window.
- The current pending queue rows should remain stuck in the same `transient_http_failure` loop until the service is redeployed with a valid contribution bucket configuration.

## Recommended Remediation

1. Add `HOKUSAI_CONTRIBUTIONS_BUCKET` to the ECS task definition inputs for `hokusai-api-development`, and set `HOKUSAI_CONTRIBUTIONS_PREFIX` if a non-root prefix is desired.
2. Redeploy `hokusai-api-development`, then replay the pending contribution queue rows for HOK-1958 and HOK-1876.
3. Add a deployment-time or startup-time guard so new contribution features cannot ship without their required environment variables.
4. Add one structured warning log on the `ContributionPersistenceUnavailableError` path so future production incidents expose the precise cause without requiring task-definition inspection.

Risk / cost:

- Config-only fix: low risk.
- Replay required after deploy: moderate operational coordination, but no schema or contract change.

## Follow-up Issues

- Recommended: file an infrastructure/config follow-up to wire `HOKUSAI_CONTRIBUTIONS_BUCKET` into the API task definition for development and production.
- Recommended: file a small observability follow-up to log structured cause details for contribution `503`s.
- No code patch was required in this investigation branch because the live-service evidence is already conclusive.

## How This Investigation Was Conducted

Commands run from this worktree:

```bash
aws sts get-caller-identity

aws ecs describe-services \
  --cluster hokusai-development \
  --services hokusai-api-development

aws ecs describe-task-definition \
  --task-definition hokusai-api-development:312

aws ecs describe-task-definition \
  --task-definition hokusai-api-development:311

aws elbv2 describe-target-groups \
  --target-group-arns \
  arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-reg-api-development/aab4ed4b619b04c0

aws logs start-query \
  --log-group-name /ecs/hokusai-api-development \
  --start-time <unix-seconds> \
  --end-time <unix-seconds> \
  --query-string 'fields @timestamp, @message | filter @message like /POST \/api\/v1\/models\/30\/contributions/ | sort @timestamp asc'

aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_5XX_Count \
  --dimensions \
    Name=TargetGroup,Value=targetgroup/hokusai-reg-api-development/aab4ed4b619b04c0 \
    Name=LoadBalancer,Value=app/hokusai-registry-development/78840d73e3e9652e \
  --start-time 2026-06-02T12:00:00Z \
  --end-time 2026-06-02T16:00:00Z \
  --period 60 \
  --statistics Sum

aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_ELB_5XX_Count \
  --dimensions \
    Name=LoadBalancer,Value=app/hokusai-registry-development/78840d73e3e9652e \
  --start-time 2026-06-02T12:00:00Z \
  --end-time 2026-06-02T16:00:00Z \
  --period 60 \
  --statistics Sum

aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HealthyHostCount \
  --dimensions \
    Name=TargetGroup,Value=targetgroup/hokusai-reg-api-development/aab4ed4b619b04c0 \
    Name=LoadBalancer,Value=app/hokusai-registry-development/78840d73e3e9652e \
  --start-time 2026-06-02T12:00:00Z \
  --end-time 2026-06-02T16:00:00Z \
  --period 60 \
  --statistics Minimum

aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name UnHealthyHostCount \
  --dimensions \
    Name=TargetGroup,Value=targetgroup/hokusai-reg-api-development/aab4ed4b619b04c0 \
    Name=LoadBalancer,Value=app/hokusai-registry-development/78840d73e3e9652e \
  --start-time 2026-06-02T12:00:00Z \
  --end-time 2026-06-02T16:00:00Z \
  --period 60 \
  --statistics Maximum
```
