# Model 30 v2 reward cutover rehearsal (HOK-2217)

`scripts/model_30/run_v2_cutover_rehearsal.sh` runs the v2 composite-reward cutover
rehearsal end-to-end as a **dry-run**. It re-scores the baseline + candidate, publishes the
canonical v2 baseline score + spec hash, and exercises an accepted and a rejected DeltaOne
case — without ever publishing a MintRequest or minting on-chain.

## Safety contract

- **Never publishes / never mints.** It only scores, builds, verifies, and writes artifacts.
- **Non-prod only.** The synthetic reward legs are hard-blocked on `prod`/`production`/
  `mainnet` (both by the underlying tool and by this wrapper). Run on **canary/testnet**
  (recommended), `staging`, or `development`.
- **Run where MLflow is reachable** (bastion / `ecs exec` / CI), not a laptop without a tunnel.
- `--check` validates config and computes the spec hash with **no network**.

## Configure

```bash
export ENVIRONMENT=canary                                   # canary | testnet | staging | development
export MLFLOW_TRACKING_URI=...                              # target MLflow
export BASELINE_URI='models:/Technical Task Router@production'
export CANDIDATE_URI='models:/Technical Task Router@candidate'
export HOLDOUT=/path/to/cleaned_holdout.csv
export MANIFEST=/path/to/model_30_training_manifest.json
export ESCROW_WALLET="$PENDING_CLAIMS_ESCROW_ADDRESS"       # accepted-leg recipient fallback
# Baseline/candidate MLflow run IDs for attribution (or set SOURCE_ATTRIBUTION to a report):
export BASELINE_RUN_ID=...
export CANDIDATE_RUN_ID=...
export OUT_DIR=artifacts/hok-2217-rehearsal
```

## Run

```bash
# 1. Validate everything first (no network):
scripts/model_30/run_v2_cutover_rehearsal.sh --check

# 2. Full rehearsal (rescore -> baseline -> accepted -> rejected), dry-run only:
scripts/model_30/run_v2_cutover_rehearsal.sh --all

# …or run a single phase:
scripts/model_30/run_v2_cutover_rehearsal.sh --rescore
scripts/model_30/run_v2_cutover_rehearsal.sh --baseline
scripts/model_30/run_v2_cutover_rehearsal.sh --accepted
scripts/model_30/run_v2_cutover_rehearsal.sh --rejected
```

## What each phase does

| Phase | Output | Notes |
|---|---|---|
| `--check` | `OUT_DIR/rehearsal_config.txt` | Config + v2 spec sha256. No network. |
| `--rescore` | `compare_v2.json`, `compare_v1.json` | v2 is canonical (asserts `primary_metric == technical_task_router.benchmark_score_v2`); v1 kept as the guardrail comparison. Logs the v2 run to MLflow. |
| `--baseline` | `published_v2_baseline.json` | Canonical v2 baseline score + spec sha256; tags an MLflow run when reachable. |
| `--accepted` | `accepted/synthetic_mint_request.json` | Builds the synthetic MintRequest and **asserts** `benchmark_spec_id` / `metric_name` = `technical_task_router.benchmark_score/v2` and `metric_family = continuous`. Not published. |
| `--rejected` | `compare_v2_reject.json` | Scores the baseline against itself → `primary_delta = 0` → DeltaOne declines, no mint. |

## Manual follow-ups (not automated)

- **Activate the v2 BenchmarkSpec** for model 30 (`is_active=True`) via `BenchmarkSpecService`
  so `get_active_spec_for_model(30)` returns `technical_task_router.benchmark_score/v2`
  (HOK-2217 acceptance criterion 1). Specs are immutable — create a new active version.
- The **rejected leg** here demonstrates the gate via a zero delta. To exercise a
  *guardrail* rejection (candidate improves v2 but regresses the v1 success-under-budget
  guardrail), feed a candidate that does so and confirm promotion is blocked.

See [`technical-task-router-benchmark.md`](./technical-task-router-benchmark.md) for the v2
metric definition and operator rollback notes.
