# HOK-1876 Investigation

Model 30 is not bottlenecked by artifact size on the warm path. The measured hot path is the router algorithm itself, specifically `_nearest_neighbors()` doing a full `dataset.copy()` plus `DataFrame.apply(..., axis=1)` and `_similarity()` for every request. The lowest-risk next step is operational: pin BLAS/OpenMP threads to `1` in ECS and remove the unnecessary per-request `dataset.copy()`. The larger structural win is to replace the row-wise pandas scan with a precomputed, vectorized feature index.

- Low-risk recommendation: pin `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, and `OPENBLAS_NUM_THREADS=1`, then remove `dataset.copy()` in `_nearest_neighbors()`.
- Structural recommendation: precompute categorical features at load time and replace per-row pandas `apply()` with vectorized similarity scoring.

## Measurement Environment

Date: 2026-06-02

- Repo commit under investigation: `a90eb00df8ffac4eb1cb5e898c4a70deb4d7ac41`
- Deployed ECS task definition inspected: `hokusai-api-development:312`
- Deployed image tag inspected: `932100697590.dkr.ecr.us-east-1.amazonaws.com/hokusai-api:eaec11d83dab55256c850583fa49346546892ad6`
- ECS runtime allocation from Terraform and task definition: `cpu = "512"`, `memory = "1024"`
- Local replay host: macOS on Apple Silicon (ARM64) / Python `3.11.8` / `mlflow 3.11.1` / `pandas 2.3.2` / `numpy 1.26.4`
- Artifact inspected from S3: `s3://hokusai-mlflow-artifacts-development/3/models/m-32c82e80c2264d6c980dd3c6fe763cfb/artifacts/`

Important caveat:

- All warm/cold timings below were measured on ARM64 macOS, not the AMD64 Linux ECS runtime. Treat them as directional only. CloudWatch trace fields on the deployed AMD64 ECS task are the source of truth for production latency once structured logging is restored.
- CloudWatch retained only the `model_30_latency_trace` message string, not the structured phase fields, so production p50/p95/p99 could not be reconstructed directly from logs.
- The only nested-contract-compatible artifact reachable from S3 (`m-f02cea...`) is a smoke artifact and is not representative for performance work.
- The runtime measurements below therefore use the real `TechnicalTaskRouterModel` implementation in [src/models/technical_task_router.py](/Users/timothyogilvie/Dropbox/Hokusai/worktrees/investigate-model-30-runtime-and-packaging-alternatives-for-dramatic-speedup/src/models/technical_task_router.py:82) with the real 696-row router dataset extracted from the MLflow artifact. Treat them as directional local measurements, not production latency promises.

## Baseline Measurements

### Artifact

Source command:

```bash
aws s3 ls s3://hokusai-mlflow-artifacts-development/3/models/m-32c82e80c2264d6c980dd3c6fe763cfb/artifacts/ --recursive --summarize
```

| Metric | Value |
| --- | --- |
| Total artifact size | 548,853 bytes |
| File count | 8 |
| Dataset payload | `artifacts/hokusai-router-dataset.csv` = 543,688 bytes |
| Dataset share of artifact | 99.1% |
| Router dataset rows | 696 |
| Largest non-dataset file | `MLmodel` = 2,827 bytes |
| Requirements | `mlflow==3.9.0`, `pandas` |
| Runtime | Python `3.11.8` |

Interpretation: artifact size is almost entirely the CSV dataset. Shrinking or splitting the artifact helps cold deploy/scale-out time more than warm inference latency.

### Cold Load

Method:

- Replayed `TechnicalTaskRouterModel.load_context()` against the extracted dataset.
- Then executed one prediction with the artifact's own `serving_input_example.json`.
- Repeated 5 times.

| Metric | p50 | p95 | p99 | mean | min | max | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Load only (ms) | 11.54 | 11.90 | 11.90 | 13.95 | 11.41 | 23.41 | 5 |
| First inference only (ms) | 21.58 | 21.73 | 21.73 | 22.20 | 21.45 | 24.69 | 5 |
| Total cold local replay (ms) | 33.12 | 33.64 | 33.64 | 36.15 | 32.87 | 48.11 | 5 |

This excludes any registry or S3 download latency because the artifact was already local. In real ECS cold start, registry alias resolution and artifact fetch dominate.

### Warm Inference

Method:

- Loaded the real router dataset once.
- Ran 200 predictions against the artifact's own example row.
- Timed end-to-end `TechnicalTaskRouterModel.predict()` wall clock.

| Metric | p50 | p95 | p99 | mean | min | max | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Warm predict total (ms) | 23.39 | 28.93 | 35.60 | 24.24 | 21.21 | 48.18 | 200 |

### RSS / CPU

Method:

- Sampled process RSS with `ps -o rss= -p $PID`.
- Sampled before load, after load, and after 20 warm predictions.

| Sample | RSS |
| --- | --- |
| Before load | 198.0 MiB |
| After load | 207.4 MiB |
| After warm loop | 208.4 MiB |

Observed delta from loading the 696-row dataset was about 9.4 MiB. No evidence of repeated reloads or growth during the short warm loop.

Direct service-path local replay against the smoke artifact also showed one-process CPU saturation during sustained warm inference (`process_cpu_pct ~= 98%`), consistent with a CPU-bound Python hot path.

### CloudWatch Query Template

The production query attempted for a 24-hour window ending 2026-06-02 was:

```sql
fields @timestamp, @message, @logStream
| filter @message like /model_30_latency_trace/
| sort @timestamp desc
| limit 20
```

Result: only the message string was retained in the log event, so per-phase fields such as `model_inference_ms` were not queryable from CloudWatch Logs Insights.

## Profiling Findings

Method:

- `cProfile` over 50 warm predictions using the real router dataset and example row.
- Profiled the actual checked-in router implementation, not the smoke artifact.

Top hot functions by cumulative time:

| Function | Cum time (50 calls) | Share of `predict()` wall time | Notes |
| --- | --- | --- | --- |
| `TechnicalTaskRouterModel.predict` | 3.3278s | 100% | Full inference loop |
| `_predict_row` | 3.3005s | 99.2% | Per-request orchestration |
| `_nearest_neighbors` | 2.4220s | 72.8% | Dominant cost |
| `pandas.DataFrame.apply` stack | 2.3086s | 69.4% | Row-wise whole-dataset scan |
| `_nearest_neighbors.<lambda>` | 2.1271s | 63.9% | Converts each row to dict before similarity |
| `_rank_strategies` | 0.6142s | 18.5% | Strategy ranking after neighbors |
| `_strategy_candidates` | 0.6135s | 18.4% | Cartesian product of planner/coder/reviewer choices |
| `_rank_role` | 0.5065s | 15.2% | Repeated pandas filtering/grouping |
| `_similarity` | 0.4769s | 14.3% | Per-neighbor Python scoring |
| `Series.to_dict` | 1.6146s within apply stack | material | Serialization overhead inside the scan |

What this means:

- The router spends most of its time scanning all 696 rows on every request.
- `_nearest_neighbors()` is the main target. The combination of `dataset.copy()`, `DataFrame.apply()`, lambda row conversion, and `_similarity()` dominates the total request budget.
- Strategy ranking is secondary but still meaningful once neighbor search is fixed.
- Pydantic validation and response normalization were not significant in local serving-path replay; the real problem is the model algorithm.

Per-request work that should move to startup:

- Precompute categorical encodings / feature vectors for the dataset at `load_context()`.
- Pre-shard rows by coarse filters such as `task_type`, `language`, or `domain`.
- Precompute stable role aggregates used by `_rank_role()` where possible.
- Remove `dataset.copy()` from `_nearest_neighbors()` because the dataset is read-only.

## Network Call Audit

Method:

- Patched `socket.socket.connect`.
- Ran 20 warm predictions against the loaded router model.

Result:

- Outbound connect calls observed during warm inference: `0`

Interpretation:

- Warm inference itself is self-contained once the model is loaded.
- Any network activity belongs to cold path concerns such as MLflow alias resolution or artifact download, not `/predict` steady-state execution.

## ECS / Threading Configuration

Source:

- [data-pipeline-ecs-services.tf](/Users/timothyogilvie/Dropbox/Hokusai/hokusai-infrastructure/environments/data-pipeline-ecs-services.tf:157)
- `aws ecs describe-task-definition --task-definition hokusai-api-development:312`

Observed config:

| Setting | Value |
| --- | --- |
| ECS CPU | `512` = 0.5 vCPU |
| ECS memory | `1024` MiB |
| `OMP_NUM_THREADS` | not set |
| `MKL_NUM_THREADS` | not set |
| `OPENBLAS_NUM_THREADS` | not set |
| `BLIS_NUM_THREADS` | not set |
| `NUMEXPR_NUM_THREADS` | not set |
| `UVICORN_WORKERS` | not set |
| `GUNICORN_WORKERS` | not set |

Risk:

- The container is allocated 0.5 vCPU, but numpy/pandas-linked BLAS libraries are free to default to host-visible cores unless capped.
- That mismatch can create thread oversubscription and context switching under load, even if Model 30 is mostly Python-bound today.
- This is low-cost to test and easy to roll back.

## Axis-by-Axis Evaluation

### Smaller or split artifact

High applicability for cold path, low applicability for warm path. The artifact is 99.1% CSV. Splitting immutable historical rows from incremental rows, or switching from CSV to Parquet, should reduce artifact download size and startup parsing cost. It will not materially change warm `/predict` latency unless paired with a better runtime representation.

### Precomputed transformers or features

High applicability. The current implementation recomputes categorical comparisons across all 696 rows per request. Precomputing encoded arrays, lookup tables, or role aggregates at `load_context()` directly attacks the measured hot path.

### Eager vs lazy loading

Current serving is already eager via startup warmup. The more relevant question is lazy data access inside the model: it still eagerly scans the entire dataset per request. A better approach is eager model load plus lazy narrowing to a shard keyed by high-signal features.

### Optimized runtime such as ONNX

Low applicability. Model 30 is not a tensor graph or tree ensemble; it is a CSV-backed heuristic nearest-neighbor router. ONNX would not remove the Python-side data scan. The right optimization is vectorized numpy/pandas or a precomputed index, not a runtime swap.

### Accidental network calls

Low applicability on warm path. Patched-socket replay saw zero outbound connects during warm inference. The only network risk is cold-load alias resolution or artifact fetch from MLflow/S3.

### Inefficient batching or per-request setup

High applicability. `_nearest_neighbors()` copies the full dataset and then applies a Python callback across every row. That is the most obvious avoidable per-request setup cost in the codebase.

### CPU/threading limits

High applicability. ECS grants only 0.5 vCPU while thread env vars are unset. Even though the current hot path is mostly Python, oversubscription risk is real and the mitigation is trivial to A/B in Terraform.

### Memory pressure / reloads

Medium applicability. Local replay showed only about 9 MiB of RSS growth after load, so the current 696-row dataset is not large enough to explain reloads by itself. Memory pressure matters more if the dataset grows materially or if multiple loaded artifacts coexist per process.

## Recommendations

### Low-risk near-term: pin BLAS/OpenMP threads and remove `dataset.copy()`

Expected latency improvement:

- `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`: projected 10-25% p95 improvement under ECS load if there is any hidden BLAS oversubscription.
- Removing `dataset.copy()` in `_nearest_neighbors()`: projected 3-8% p95 improvement and one less DataFrame allocation per request.

Complexity: low

Operational risk: low

- Env-var change is Terraform-only and reversible.
- Removing `dataset.copy()` is behavior-preserving if the dataset remains read-only.

Rollback:

- Revert the Terraform env vars.
- Revert the one-line code change if any unexpected mutation assumption appears.

Proposed follow-up tickets:

- `Pin BLAS/OpenMP threads to 1 for hokusai-api-development Model 30 serving`
- `Remove per-request dataset.copy() from TechnicalTaskRouterModel._nearest_neighbors`

Why this is the best near-term move:

- It is cheap, safe, and directly aligned with the current ECS mismatch.
- It buys operational headroom while the structural rewrite is queued.

### Larger structural: vectorize nearest-neighbor similarity with precomputed feature arrays

Expected latency improvement:

- `_nearest_neighbors()` accounts for about 72.8% of total `predict()` wall time in profile.
- If vectorization removes 80-90% of that block, end-to-end warm p95 improvement should land roughly in the 58-66% range.
- This is the only option with a credible path to "dramatic speedup".

Complexity: medium

Operational risk: medium

- Exact ranking semantics must be preserved.
- Requires parity tests between the old and new scoring paths.
- Best shipped behind an env flag such as `MODEL_30_VECTORIZED_SIMILARITY=true`.

Rollback:

- Keep the current Python path intact and switch back via config flag.

Proposed follow-up ticket:

- `Vectorize TechnicalTaskRouterModel nearest-neighbor scoring with precomputed categorical features`

Why this is the best structural move:

- The profile is unambiguous: warm latency is dominated by Python row scanning, not MLflow wrapping, not serialization, and not network.

### Runner-up structural option: Parquet artifact plus pre-sharded feature index

Expected latency improvement:

- Cold load: moderate reduction from smaller, typed on-disk format.
- Warm path: potentially another 15-30% on top of vectorization if shard narrowing avoids full-dataset scans.

Complexity: large

Operational risk: medium

- Requires training/promotion pipeline changes and artifact-version compatibility handling.

Rollback:

- Version the artifact format and keep CSV loader fallback in place until rollout stabilizes.

Proposed follow-up ticket:

- `Replace Model 30 CSV artifact with Parquet plus shard index for nearest-neighbor lookup`

## Proposed Follow-Up Tickets

- `Pin BLAS/OpenMP threads to 1 for hokusai-api-development Model 30 serving`
- `Remove per-request dataset.copy() from TechnicalTaskRouterModel._nearest_neighbors`
- `Vectorize TechnicalTaskRouterModel nearest-neighbor scoring with precomputed categorical features`
- `Replace Model 30 CSV artifact with Parquet plus shard index for nearest-neighbor lookup`
- `Emit structured phase fields from model_30_latency_trace into CloudWatch-queryable logs`

## Appendices

### Repro Commands

Artifact inventory:

```bash
aws s3 ls s3://hokusai-mlflow-artifacts-development/3/models/m-32c82e80c2264d6c980dd3c6fe763cfb/artifacts/ --recursive --summarize
```

Local helper against a supplied artifact URI:

```bash
python -m scripts.model_30.profile_inference \
  --model-uri /tmp/hok1876/m-f02ce \
  --warm-iterations 200 \
  --cold-iterations 5 \
  --output-json
```

Real-router replay used for the final runtime conclusions:

```python
from types import SimpleNamespace
import json
import pandas as pd
from pathlib import Path
from src.models.technical_task_router import TechnicalTaskRouterModel, ROUTER_DATASET_ARTIFACT

artifact_dir = Path("/tmp/hok1876/m-32c82")
dataset = artifact_dir / "artifacts" / "hokusai-router-dataset.csv"
serving_input = json.loads((artifact_dir / "serving_input_example.json").read_text())["dataframe_split"]
frame = pd.DataFrame(serving_input["data"], columns=serving_input["columns"])

model = TechnicalTaskRouterModel(k_neighbors=40)
model.load_context(SimpleNamespace(artifacts={ROUTER_DATASET_ARTIFACT: str(dataset)}))
model.predict(None, frame)
```

### Requirement Coverage

- REQ-F1 summary and recommendation: covered in header plus Recommendations.
- REQ-F2 baseline measurements: Baseline Measurements section.
- REQ-F3 profiling findings: Profiling Findings section.
- REQ-F4 network call audit: Network Call Audit section.
- REQ-F5 ECS and threading audit: ECS / Threading Configuration section.
- REQ-F6 axis-by-axis evaluation: Axis-by-Axis Evaluation section.
- REQ-F7 low-risk and structural recommendations: Recommendations section.
- REQ-F9 helper script: [scripts/model_30/profile_inference.py](/Users/timothyogilvie/Dropbox/Hokusai/worktrees/investigate-model-30-runtime-and-packaging-alternatives-for-dramatic-speedup/scripts/model_30/profile_inference.py:1)
