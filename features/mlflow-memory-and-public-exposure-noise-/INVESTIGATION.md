# HOK-1980 Investigation

## Recommendation

Decision: Keep public + tighten.

Reasons:
- External callers are active today in this repo: production env config points clients at `https://registry.hokus.ai/api/mlflow`, deployment verification calls the public MLflow endpoints directly, and the main README shows the public registry URL in copy-paste examples.
- User-facing docs continue to instruct operators and users to set `MLFLOW_TRACKING_URI` to the public registry endpoint, so making MLflow internal-only would break the documented registration path immediately.
- Scanner traffic is materially higher on MLflow than the API service, so the problem is not that exposure is unnecessary; the problem is that the public surface needs tighter filtering and earlier memory alerts.

## Caller Inventory

| Repo | File | Line | Purpose | Could use internal URL? |
|------|------|------|---------|--------------------------|
| hokusai-data-pipeline | `README.md` | 31 | Example `ModelRegistry` client initialization | No, this is user-facing sample code |
| hokusai-data-pipeline | `README.md` | 91 | Example `MLFLOW_TRACKING_URI` setup | No, this is user-facing sample code |
| hokusai-data-pipeline | `.env.production` | 4 | Production `MLFLOW_SERVER_URL` | No, production clients need the public endpoint |
| hokusai-data-pipeline | `.env.production` | 5 | Production `MLFLOW_TRACKING_URI` | No, production clients need the public endpoint |
| hokusai-data-pipeline | `verify_mlflow_deployment.sh` | 144 | Deployment verification for experiment search | No, this validates the public route |
| hokusai-data-pipeline | `verify_mlflow_deployment.sh` | 167 | Deployment verification for artifact access | No, this validates the public route |
| hokusai-data-pipeline | `verify_mlflow_deployment.sh` | 213 | Inline client example for public tracking URI | No, it documents the public path |
| hokusai-data-pipeline | `documentation/cli/model-registration.md` | 154 | CLI documentation for model registration | No, this is a public user workflow |
| hokusai-data-pipeline | `documentation/cli/model-registration.md` | 280 | CLI example flag `--mlflow-uri` | No, this is a public user workflow |
| hokusai-data-pipeline | `documentation/cli/model-registration.md` | 289 | CLI env var example | No, this is a public user workflow |
| hokusai-data-pipeline | `documentation/getting-started/mlflow-access.md` | 32 | Onboarding export for `MLFLOW_TRACKING_URI` | No, onboarding targets external users |
| hokusai-data-pipeline | `documentation/getting-started/mlflow-access.md` | 99 | Authentication guidance for `registry.hokus.ai/mlflow` | No, this describes the public access contract |

Internal URL note:
- An internal service URL exists in local architecture notes as `http://mlflow.hokusai-development.local:5000`, but that is appropriate for service-to-service traffic inside the cluster, not for CLI users, CI that validates the internet path, or public documentation examples.

## MLflow ALB Traffic Characterization

Source of evidence:
- `features/investigate-and-suppress-scanner-noise-4xx-traffic/INVESTIGATION.md` recorded 2753 MLflow 4xx responses versus 560 on the API service.
- The API service received `ScannerFilterMiddleware` in `src/api/main.py`, but MLflow does not run through that FastAPI middleware path.

What we can conclude:
- MLflow sees about 4.9x as many 4xx responses as the API service from scanner-style traffic.
- The sampled scanner paths from HOK-1977 were generic exploit probes such as `/.env`, `/wp-admin/`, `/cgi-bin/`, `/ui/login`, and `/mgmt/tm/util/bash`, which are unrelated to legitimate MLflow usage.
- That traffic is waste on a Python service that is already the highest-memory ECS workload in the cluster.

Methodology and limitation:
- This dev machine does not have live ALB log sampling in scope for the task, so this write-up reuses the documented HOK-1977 investigation artifact rather than attempting fresh production log access.
- The characterization is therefore based on the prior investigation counts plus the deny-list paths shipped for the API scanner filter.

## Alarm Specifications

Warn alarm for early headroom loss:

```hcl
resource "aws_cloudwatch_metric_alarm" "mlflow_memory_warn" {
  alarm_name          = "hokusai-mlflow-memory-warn-development"
  alarm_description   = "MLflow ECS memory utilization is above 80% for 3 minutes"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "hokusai-development"
    ServiceName = "hokusai-mlflow-development"
  }

  alarm_actions = [aws_sns_topic.hokusai_alerts.arn]
  ok_actions    = [aws_sns_topic.hokusai_alerts.arn]
}
```

Critical alarm for fast sustained pressure:

```hcl
resource "aws_cloudwatch_metric_alarm" "mlflow_memory_critical" {
  alarm_name          = "hokusai-mlflow-memory-critical-development"
  alarm_description   = "MLflow ECS memory utilization is above 85% for 2 minutes"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 85
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "hokusai-development"
    ServiceName = "hokusai-mlflow-development"
  }

  alarm_actions = [aws_sns_topic.hokusai_alerts.arn]
  ok_actions    = [aws_sns_topic.hokusai_alerts.arn]
}
```

Notes:
- The existing shared alarm already covers 85% memory utilization, but it evaluates on `period = 300` and `evaluation_periods = 2`, so it takes about 10 minutes to fire.
- The proposed MLflow-specific alarms tighten that response window to 3 minutes at warn and 2 minutes at critical.
- Use the existing SNS topic abstraction from the infrastructure repo rather than hardcoding any account-specific ARN in this document.

## Cross-repo Handoff

Files to update in `hokusai-infrastructure`:
- `environments/ecs-deployment-monitoring.tf`: add the two MLflow-specific CloudWatch alarms above, wired to the existing alerts SNS topic and `AWS/ECS` dimensions for `hokusai-development` and `hokusai-mlflow-development`.
- Registry ALB listener or WAF config in development and production: add the scanner-path deny rules already identified in HOK-1977 so exploit probes are rejected before they reach MLflow.
- Any service-auth configuration for registry routes: verify that all MLflow API and artifact routes require authenticated access and that unauthenticated requests cannot hit the backend.

Recommended follow-up change set:
1. Add `mlflow_memory_warn` and `mlflow_memory_critical` resources alongside the current shared ECS memory alarm.
2. Apply ALB fixed-response rules or equivalent WAF rules for `/.env`, `/wp-admin/*`, `/cgi-bin/*`, `/ui/login`, `/login.action`, `/api/jsonws*`, and `/mgmt/*`.
3. Validate alarm delivery through the existing `hokusai-alerts-<environment>` SNS topic and confirm dashboard visibility after deploy.
