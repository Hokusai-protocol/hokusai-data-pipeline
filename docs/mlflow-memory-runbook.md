# MLflow Memory Runbook

## What this alarm means

The MLflow ECS service is running above its expected memory range.

- Warn should fire when `hokusai-mlflow-development` stays at or above 80% memory for 3 minutes.
- Critical should fire when it stays at or above 85% memory for 2 minutes.
- Recent baseline was about 76.6%, so warn is meant to catch regression before an OOM or restart loop.
- Scanner traffic against `registry.hokus.ai` is a known contributor to wasted request handling, so elevated memory may reflect either real platform usage or noisy internet probes.

## First response

1. Open Grafana and check the `MLflow Memory Utilization (7d)` panel for slope, spikes, and time spent above 80%.
2. Compare MLflow against API and Auth in `Service Memory - MLflow vs API vs Auth` to decide whether this is service-specific or cluster-wide pressure.
3. Check recent logs for the service:
   `aws logs tail /ecs/hokusai-mlflow-development --since 30m`
4. Inspect ECS service state and recent events:
   `aws ecs describe-services --cluster hokusai-development --services hokusai-mlflow-development`
5. Look for correlated symptoms:
   high 4xx volume on registry routes, container restarts, task replacement, or slow model registration requests.
6. If memory is still climbing, reduce concurrent load if possible and be ready to recycle the service with the infrastructure owner.

## Escalation

- Escalate immediately if the critical alarm is sustained for more than one evaluation window, the task is restarting, or model registration is failing.
- Escalate to infrastructure follow-up if scanner-style 4xx traffic is dominant, because mitigation belongs at the ALB or WAF layer rather than inside MLflow.
- Escalate to application owners if memory growth tracks legitimate model traffic or a recent deploy.
- Include in the handoff: current memory level, whether the trend is rising or flat, recent ECS events, and whether scanner-noise indicators were present.
