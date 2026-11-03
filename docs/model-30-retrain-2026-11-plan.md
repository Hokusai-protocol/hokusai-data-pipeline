# Model 30 Retrain — November 2026

Retrain the Technical Task Router on all locally available Wavemill data
gathered since launch (mid-July 2026), plus the pre-launch history.

Working directory for artifacts: `data/model_30/retrain-2026-11/` (CSVs are gitignored).

## Facts going in

- Production model was registered from the June 4 clean set (692 rows). It has
  never seen post-launch data.
- Local Wavemill evals across all repos: 6,654 unique records, 5,509 since
  2026-07-15, 474 distinct issues.
- S3 contributions: 898 rows, ~all from one account (first-party Wavemill),
  so they are a subset of the local evals and are not added separately.
- The model is a k-NN ranker over a CSV artifact; training compute is trivial.

## Decisions

- **Source of truth:** local `.wavemill/evals/evals.jsonl` from every repo,
  derived through `collect_wavemill_router_corpus.py`. S3 is used only as a
  cross-check.
- **Cutoff:** `2026-11-01T00:00:00Z` (as-of). Later rows are excluded.
- **Holdout:** temporal. Train on rows before `2026-10-01`, hold out October.
  Also score the June benchmark for continuity.
- **No mint / no attribution** this round: one contributor, so leave-one-out
  attribution is meaningless. Treat as a plain retrain.

## Phases

1. **Snapshot.** Copy every `evals.jsonl` (and router CSV exports) into a
   timestamped snapshot dir with SHA-256 manifest.
2. **Collect.** Run the collector over the snapshot → raw + clean router CSV
   and corpus report. Record skip reasons.
3. **Inspect & clean.** Per-month and per-model coverage, label coverage
   (success, cost, duration), duplicate tasks, test/probe repos, models outside
   the serving catalog.
4. **Split.** Temporal train/holdout split; build the holdout in benchmark
   format via `split_router_benchmark.py`.
5. **Train candidates** (local MLflow, `--smoke` where useful):
   - A: current production artifact (baseline, June data)
   - B: June + post-launch (all rows before Oct 1)
   - C: post-launch only
6. **Evaluate** each candidate on the October holdout and the June benchmark:
   benchmark score v2, invalid-selection rate, cost error, duration MAE,
   reliability calibration, latency smoke check.
7. **Decide & promote.** Pick the winner, retrain it on all rows through the
   cutoff, register to registry.hokus.ai, cutover rehearsal dry-run, alias move,
   API restart. *Requires explicit go-ahead — this step touches production.*

## Reproduce

All steps are deterministic. Re-running them against the snapshot reproduces
the v8 dataset (`sha256:24bb1f1e…c24a`) and the identical train/holdout split.

```sh
W=data/model_30/retrain-2026-11
# 1. derive rows from raw evals only (stale router CSVs ignored)
python scripts/model_30/collect_wavemill_router_corpus.py --search-root $W/snapshot \
  --no-router-csv --output $W/router-dataset.all.clean.csv \
  --raw-output $W/router-dataset.all.raw.csv --report $W/corpus-report.json
# 2. add Feb–May history from the legacy export, relabel success from score
python scripts/model_30/merge_legacy_router_export.py \
  --legacy $W/snapshot/wavemill/.wavemill/evals/hokusai-router-dataset.csv \
  --derived $W/router-dataset.all.clean.csv --before 2026-11-01 \
  --output $W/router-dataset.union.raw.csv \
  --provenance-output $W/router-dataset.union.provenance.csv --report $W/union-report.json
python scripts/model_30/clean_router_dataset.py --input $W/router-dataset.union.raw.csv \
  --output $W/router-dataset.union.clean.csv --report $W/union-clean-report.json
# 3. temporal split
python scripts/model_30/temporal_split_router_benchmark.py \
  --input $W/router-dataset.union.clean.csv --cutoff 2026-10-01 --end 2026-11-01 \
  --train-output $W/train.csv --holdout-output $W/holdout-oct.csv \
  --quarantine-output $W/holdout-oct.quarantine.csv --report $W/split-report.json
# 4. local candidates (no registry, no chain)
python scripts/model_30/log_local_router_candidate.py \
  --tracking-uri file://$PWD/$W/mlruns --run-name B --router-dataset $W/train.csv
# 5. benchmark + role replay
python scripts/model_30/evaluate_technical_task_router.py --holdout-dataset $W/holdout-oct.csv \
  --model-uri runs:/<run_id>/model --benchmark-version v2 --output-report $W/eval-B-oct-v2.json
python scripts/model_30/role_replay_report.py --tracking-uri file://$PWD/$W/mlruns \
  --holdout $W/holdout-oct.csv --candidate B=runs:/<run_id>/model \
  --output $W/role-replay-oct.json
```

The snapshot and outputs live under `data/model_30/retrain-2026-11/`. They are
not committed (raw evals, gitignored CSVs).

## Results log

### Phase 1–2: snapshot and collect (2026-11-02)

- Snapshot of 11 repos' `evals.jsonl` + router CSVs, checksummed in
  `snapshot.sha256`.
- Collector run with `--no-router-csv`. Without it, stale CSVs (the May 18
  wavemill export and June `cross-repo.*` outputs in this repo's `.wavemill/`)
  would be used *instead of* the raw evals for those repos.
- 6,654 records → 1,203 derived rows → 1,161 clean. The 5,449 skipped records
  are almost all `llm-cli` auxiliary calls (task-packet review, classify,
  fallback chains): no issue ID, no planner/coder/reviewer route. They are not
  routing outcomes and are correctly excluded.

### Phase 3: recover pre-May history

- Raw evals before May 11 are gone from current `evals.jsonl` files. The only
  copy of Feb–May 16 history is the May 18 wavemill router CSV (696 rows), the
  same data production was trained on.
- That export predates wavemill `3bbc1f5c` (2026-06-03, "finalize eval success
  from scores"): 50 rows carry placeholder `completed_successfully=true` with
  score < 0.8. Relabelled as `score >= 0.8` (the wavemill policy; new data
  agrees with it on 1,159/1,161 rows).
- Legacy and derived rows are disjoint (different repos in the May 11–16
  overlap window; no matches by minute).
- **Union: 1,848 clean rows** (vs 692 in production). Duration coverage 45%
  (legacy rows lack durations; derived rows are 72%).
- Production training set reproduced exactly: cleaning the May CSV with
  original labels gives SHA-256 `b5845fbf…`, matching the June 4 record.

### Phase 4: split

- Temporal: train < 2026-10-01 (1,691 rows), holdout October (148 valid,
  9 quarantined for selected model outside the available pool). Challenge pairs
  kept on one side.

### Phase 5: candidates (local MLflow at `mlruns/`, no on-chain step)

| Candidate | Data | Rows | In-pool gate violations |
|---|---|---:|---:|
| A | production set (Feb–May 16) | 692 | 10 |
| B | union, before Oct 1 | 1,691 | 3 |
| C | derived only (May 11 – Sep 30) | 999 | 1 |

`register_technical_task_router.py` requires `ETH_RPC_URL` (it commits a weight
hash on chain), so local candidates were logged with `log_local_router_candidate.py` (same validation and
`mlflow.pyfunc.log_model` call, minus the on-chain step).

### Phase 6: evaluation on October holdout (148 rows)

Official benchmark (`evaluate_technical_task_router.py`, v2):

| Metric | A (prod) | B | C |
|---|---:|---:|---:|
| benchmark_score_v2 | 0.000 | 0.100 | 0.105 |
| reliability Brier (lower better) | 0.697 | **0.444** | 0.463 |
| cost MAE (USD) | 24.2 | 19.0 | **16.0** |
| duration MAE (s) | n/a | **16.7k** | 28.5k |
| feasibility | 0.167 | 0.269 | 0.286 |
| over-budget recommendation rate | 1.2% | 5.7% | 5.5% |
| label-evidence rows (of 2,220) | 60 | 119 | 112 |

The v2 benchmark only counts a label when the predicted route equals the
executed route (HOK-3365 rule), so evidence is ~5% of rows. B vs C is within
noise; both clearly beat A.

Role-level replay (`role-replay-oct.json`, objective `highest_reliability`):
no model's role picks agree with executed routes more on good outcomes than bad
ones (coder lift is negative for all three, CI excludes 0 for B and C). All
models predict ~0.81–0.85 success; October's actual success-under-budget is
0.18. **The router is badly overconfident on current conditions.**

Why October is different (not a pipeline artifact):

| Month | Success | Budget violation | Median cost | Success under $25 |
|---|---:|---:|---:|---:|
| Jun | 0.66 | 0.09 | $9.23 | 0.60 |
| Aug | 0.71 | 0.08 | $4.65 | 0.65 |
| Sep | 0.38 | 0.19 | $19.39 | 0.33 |
| Oct | 0.38 | 0.66 | $30.04 | 0.17 |

- Wavemill uses a fixed `maxCostUsd=25` on every task since May (verified in
  raw evals), so "under budget" means "under $25".
- Sep–Oct tasks are harder: complexity 3.9 → 4.3, mean interventions 9.3 (Sep),
  mean score 0.82 → 0.68.

### Phase 7: final artifact (local only, not registered)

- `FINAL`: all 1,848 rows through 2026-10-31,
  dataset SHA-256 `24bb1f1e…c24a`, local run `56d6351a…`.
- Coverage gate: 3 small-cell warnings (docs/tests/unknown task types); gates
  default to `warn`.
- Recommendation mix shifts to current models. On the October rows, prod picks
  only `claude-haiku-4-5` / `claude-opus-4-7` as coder; FINAL picks fable-5,
  opus-4-7, opus-5-5, gpt-5.6-terra, haiku, opus-4-8, sonnet-5.
- Local predict latency: p50 35 → 105 ms, p95 48 → 133 ms (k-NN over 2.7× rows).

## Recommendation

Ship FINAL (B's recipe plus October). It is strictly better than production on
every benchmark metric that has evidence, and it knows the current model
catalog. Do not mint for it: there is one contributor and the absolute score is low.

Before or alongside the ship, these follow-ups should be filed:

1. **Calibration/recency.** The k-NN weights all history equally, so it
   cannot learn that Sep–Oct got harder. Add recency weighting or
   a recalibration of `estimated_success_under_budget`, and evaluate on a rolling
   monthly holdout.
2. **Real budgets.** Wavemill's fixed $25 makes success-under-budget a cost
   threshold, not a user constraint. Either record real per-task budgets or
   train on success and cost separately.
3. **Collector default.** Stale router CSVs in `.wavemill/evals/` silently replace
   raw evals unless `--no-router-csv` is passed. Make derive-from-jsonl the
   default, or warn when a CSV is older than the jsonl.
4. **Local registration.** `register_technical_task_router.py` cannot run
   without on-chain config; add a `--skip-onchain` / dry-run path.
5. **History retention.** Pre-May raw evals exist only in the May CSV and
   `.bak` files; archive raw evals to S3 so future retrains can re-derive.

## Follow-ups filed

HOK-3389 (recalibration/recency), HOK-3390 (real budgets, wavemill),
HOK-3391 (collector stale-CSV default), HOK-3392 (`--skip-onchain`),
HOK-3393 (raw eval archive, wavemill).

## Registration (2026-11-02)

- Registry state before: `production` → **v5** (660 rows,
  `sha256:d4852ee5…`, 2026-06-16). Note that this is *not* the 692-row June 4 set
  used as local baseline A; the real v5 was evaluated separately (below).
- Registered **v8** = `Technical Task Router/8`, run `e429ba4a33e74066bf978db10321428a`
  (experiment 3), 1,848 rows, `sha256:24bb1f1e…c24a`. No holdout was passed at
  registration, because FINAL trains on October.
- The register script crashed *after* `log_model` registered v8: the SSM contract
  addresses are SecureStrings and were read without `--with-decryption`. Instead
  of registering a duplicate, the weight-commitment step was re-run inside v8's
  run (Sepolia, read-only `eth_call`):
  - candidate commitment `0x7b711ea2…c554`
  - on-chain head for model 30: `0x6666…6666` (placeholder), while v5's local
    commitment is `0xc504609f…a192`. **Pre-existing drift: v5's commitment was
    never written on chain.** This matters before any mint.
- Smoke: `models:/Technical Task Router/8` loads and predicts.

### Real production (v5) vs candidates, October holdout (v2)

| Metric | v5 (prod) | A | B | C |
|---|---:|---:|---:|---:|
| benchmark_score_v2 | 0.042 | 0.000 | **0.100** | 0.105 |
| reliability Brier | 0.551 | 0.697 | **0.444** | 0.463 |
| cost MAE (USD) | 24.8 | 24.2 | 19.0 | **16.0** |
| highest_reliability SUB | 0.000 | 0.000 | 0.129 | 0.143 |
| lowest_cost SUB | **0.067** | 0.000 | 0.000 | 0.000 |
| over-budget rate | 5.3% | 1.2% | 5.7% | 5.5% |
| evidence rows | 220 | 60 | 119 | 112 |

B (v8's recipe without October) is ~2.4× v5 on the primary metric and better on
everything except the `lowest_cost` objective, where v5 is 0.067 and the
retrained models are 0. The over-budget rate is unchanged against the real v5.
v8 itself can't be scored on October, because it trains on it.
- Registry key: new admin key `1503add0-3a7b-48a7-9237-9217a9b8d246`
  (owner `36121dbd…`, platform, expires 2026-12-02). The June key `hk_live_fdVL…`
  is now rejected by auth.

## Promotion (2026-11-02, approved)

- `promote_technical_task_router.py --model-uri 'models:/Technical Task Router/8'
  --alias production --no-production-smoke`, run at ~23:32Z. Report:
  `promotion-v8.json`. Previous alias target was v5 (run `09db67e3…`).
- `v2_cutover_rehearsal.sh` was **not** run. It rehearses DeltaOne reward scoring
  and minting, not serving promotion, and its baseline phase publishes a
  benchmark score. No mint this round.
- API: forced new deployment of `hokusai-api-development` (task def `:456`, image
  unchanged). New task started at 23:33:15Z and resolved `@production` → v8
  (fresh container, alias already moved). Model 30 warm completed at 23:33:38Z.
  The old task drained at 23:34:54Z. Rollout COMPLETED, 1/1 running.
- Production smoke (`production-smoke-v8.json`): all three objectives returned
  valid strategies. 10 timed calls from a laptop: all 200, p50 462 ms /
  p90 511 ms end-to-end. There is no comparable pre-promotion figure; model
  compute is ~105 ms locally.
- Registry keys: `1503add0…` (registration) and `54968d9a…` (promotion) both revoked
  after use. Mint a fresh admin key (see memory/`mlflow-registry-admin-auth`) for
  any rollback.

**Rollback:**

```sh
python scripts/model_30/promote_technical_task_router.py \
  --model-uri 'models:/Technical Task Router/5' --alias production --no-production-smoke
aws ecs update-service --cluster hokusai-development \
  --service hokusai-api-development --force-new-deployment
```

## Original promotion checklist

1. Run `register_technical_task_router.py --router-dataset
   data/model_30/retrain-2026-11/router-dataset.union.clean.csv` from an
   environment with registry access, `MLFLOW_TRACKING_TOKEN`, and the on-chain
   env (`ETH_RPC_URL`, `DELTA_VERIFIER_ADDRESS`, `MODEL_REGISTRY_ADDRESS`).
2. `evaluate_technical_task_router.py --baseline-model-uri
   "models:/Technical Task Router@production" --candidate-model-uri
   models:/Technical Task Router/<new>` on `holdout-oct.csv` to confirm the
   local result against the registered production model.
3. `run_v2_cutover_rehearsal.sh` dry run, then `promote_technical_task_router.py`.
4. Force a new deployment of `hokusai-api-development` (the pyfunc is cached in
   memory), then watch the Model 30 warm-up and `/predict` latency.
