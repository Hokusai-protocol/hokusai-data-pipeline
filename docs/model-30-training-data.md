# Model 30 Training Data

Model 30 is trained from canonical rows (`model_30_canonical_row/v1`), not from synthetic seed rows
and not from local Wavemill files.

## Source: canonical rows (HOK-3414)

Every training source is stored as canonical rows in the contributions bucket:

| Source | Location | Written by |
|---|---|---|
| v4 contributions | `model_30/canonical/v1/<submission-id>.jsonl` | the contributions endpoint (HOK-3413), repriced from tokens |
| Frozen Wavemill history | `model_30/canonical/v1/legacy/<freeze-id>/rows.jsonl` + `manifest.json` | `scripts/model_30/convert_legacy_to_canonical.py`, once per freeze |

One builder turns them into the router CSV the trainer reads:

```sh
python scripts/model_30/build_router_corpus.py \
  --canonical s3://<bucket>/<prefix>/model_30/canonical/v1/ \
  --output union.clean.csv --prices-output model-prices.json --report corpus-report.json
# filters: --start/--end (observed_at), --source legacy_freeze|contribution, --contributor <id>
# cost trust: --trusted-cost-status (default priced + recorded_total, as v10)
```

Pass `--prices-output` to `register_technical_task_router.py --router-prices`. The price table comes
from Hokusai's own rates (`configs/model_30_token_prices.v1.json`, the catalog, pinned OpenRouter).

`cost_status` decides whether a row trains cost: `priced` (repriced from tokens), `recorded_total`
(frozen pre-May 2026 history: harness-recorded total, no tokens), `unpriced_model`, `coverage_partial`,
`no_token_evidence`. Rows outside the trusted set keep their success label and lose their cost labels.

**Freezing history.** The converter is the only reader of Wavemill eval records. It derives rows from
an eval snapshot plus recovered session usage (HOK-3402), merges the Feb–May router export
(success relabelled from score, OpenAI costs quarantined), and writes canonical rows with a manifest of
input hashes. Frozen rows keep exact token counts and costs. `scripts/model_30/compare_router_corpora.py`
checks a build against a reference CSV; the 2026-11-04 freeze reproduces `v10-final/union.clean.csv`
row for row (the old CSV rounded numbers to 6 significant figures).

## Historical source (before HOK-3414)

Generate or refresh the Wavemill exports in the adjacent repository, then clean
them in this repository. The current checked-in regeneration used the artifacts:

- `/Users/timothyogilvie/Dropbox/wavemill/.wavemill/evals/hokusai-router-dataset.csv`
- `/Users/timothyogilvie/Dropbox/wavemill/.wavemill/evals/hokusai-router-budget-benchmark.csv`

The cleaning commands used on June 4, 2026 were:

```sh
python scripts/model_30/clean_router_dataset.py \
  --input /Users/timothyogilvie/Dropbox/wavemill/.wavemill/evals/hokusai-router-dataset.csv \
  --output data/model_30/hokusai-router-dataset.clean.csv \
  --report data/model_30/hokusai-router-dataset.clean.report.json

python scripts/model_30/clean_router_dataset.py \
  --input /Users/timothyogilvie/Dropbox/wavemill/.wavemill/evals/hokusai-router-budget-benchmark.csv \
  --output data/model_30/hokusai-router-budget-benchmark.clean.csv \
  --report data/model_30/hokusai-router-budget-benchmark.clean.report.json
```

The registration command in this repository validates the export before it starts an MLflow run:

```sh
python scripts/model_30/register_technical_task_router.py \
  --router-dataset ../../wavemill/.wavemill/evals/hokusai-router-dataset.csv
```

## Repeatable Clean And Merge

Use the cleaner when a new Wavemill export or supplemental export needs to be included:

```sh
python scripts/model_30/clean_router_dataset.py \
  --input ../../wavemill/.wavemill/evals/hokusai-router-dataset.csv \
  --input path/to/additional-hokusai-router-dataset.csv \
  --output data/model_30/hokusai-router-dataset.clean.csv \
  --report data/model_30/hokusai-router-dataset.clean.report.json
```

The cleaner is deterministic:

- Merges repeated `--input` CSV exports with matching headers.
- Removes invalid IDs such as `<synthetic>` from available-model lists.
- Drops rows whose selected `planner_model`, `coder_model`, or `reviewer_model` is invalid.
- De-duplicates identical cleaned rows.
- Runs the registration validator against the output before exiting successfully.

### Current Coverage Snapshot

The June 4, 2026 regenerated artifacts in `data/model_30/` have these exact
duration-coverage results:

| Artifact | Clean rows | Positive duration rows | Positive coverage | Missing/normalized duration rows | SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| `hokusai-router-dataset.clean.csv` | 692 | 2 | 0.289% | 690 | `b5845fbfbf6a1fcf78ff403e99a8718b9aaa6d42e4b07fdec85c6cc64f88c430` |
| `hokusai-router-budget-benchmark.clean.csv` | 228 | 0 | 0.0% | 228 | `bf7e83691063099012ac51be5c07710f5339c462cb66139e39f7dd5776a6d88e` |

Additional cleaner findings from the regenerated training export:

- 4 rows were dropped because `reviewer_model=deep` was not a public model ID.
- 33 `<synthetic>` values were removed from available-model lists.
- No measured-zero duration rows were preserved in either cleaned artifact.

### Duration Label Hygiene

`actual_time_seconds > 0` is the only positive duration evidence used by Model 30.
The cleaner normalizes zero, negative, malformed, and blank duration values to a
missing CSV cell unless `actual_time_seconds_measured_zero` explicitly marks an
exact zero as measured. Rows with missing duration are still retained so cost and
reliability labels remain available. If a dataset has no positive duration evidence,
duration estimates should be treated as unavailable rather than inferred from zero.

## Validation Gate

`scripts/model_30/register_technical_task_router.py` rejects the dataset if any selected or available model identifier does not start with one of the public model-family prefixes:

- `claude-`
- `gpt-`
- `deepseek-`

The gate applies to:

- `available_planner_models`
- `available_coder_models`
- `available_reviewer_models`
- `planner_model`
- `coder_model`
- `reviewer_model`

Values such as `deep-coder-v2`, `fast-coder-v1`, `<synthetic>`, empty selected model fields, and bare `deep` fail validation before MLflow logging begins.

## Provenance Logged To MLflow

Clean registrations log:

- `router_dataset_rows`
- `router_dataset_sha256`
- `router_dataset_model_distribution`
- `hokusai.dataset.id`
- `hokusai.dataset.hash`
- `hokusai.dataset.num_samples`
- `hokusai.dataset.source`
- `router_dataset_summary.json`

When a validated holdout is available, include it during registration so the run also logs the
Model 30 baseline metrics:

```sh
python scripts/model_30/register_technical_task_router.py \
  --router-dataset data/model_30/hokusai-router-dataset.clean.csv \
  --holdout-dataset data/model_30/hokusai-router-holdout.clean.csv
```

The holdout evaluator rejects invalid benchmark rows before scoring. Rows with missing or
nonpositive `max_cost_usd`, missing observed outcomes, invalid costs, or historical selected
models outside the row's available model set are quarantined and counted in the evaluation report.
They are not silently treated as zero-budget failures.

The current local baseline report was generated with:

```sh
python scripts/model_30/register_technical_task_router.py \
  --router-dataset data/model_30/hokusai-router-dataset.clean.csv \
  --holdout-dataset data/model_30/hokusai-router-budget-benchmark.clean.csv \
  --run-name hok-1929-local-registration \
  --smoke

python scripts/model_30/evaluate_technical_task_router.py \
  --holdout-dataset data/model_30/hokusai-router-budget-benchmark.clean.csv \
  --model-uri "models:/Technical Task Router@production" \
  --model-id "Technical Task Router@production" \
  --output-report data/model_30/model_30_baseline_report.json
```

That report evaluated 109 valid holdout rows across 327 objective-scored benchmark rows,
quarantined 119 rows (`coder_model:outside_available=79`, `planner_model:outside_available=40`),
and confirmed `technical_task_router.duration_mae_seconds_v1 = null` because positive-duration
coverage on the cleaned holdout is exactly zero.

To compare a candidate model against a baseline for contributor reward decisions:

```sh
python scripts/model_30/evaluate_technical_task_router.py \
  --holdout-dataset data/model_30/hokusai-router-holdout.clean.csv \
  --baseline-model-uri "models:/Technical Task Router/4" \
  --candidate-model-uri "models:/Technical Task Router/5" \
  --output-report data/model_30/model-30-candidate-comparison.json \
  --log-mlflow
```

The comparison report includes baseline metrics, candidate metrics, deltas, the primary
`technical_task_router.benchmark_score_v1` delta, and diagnostic guardrail deltas for invalid
selection rate, cost error, duration error, and reliability calibration. When the holdout has
zero positive duration labels, the duration MAE field remains `null` and MLflow logging skips it
instead of writing a misleading `0.0`.

## Checked-In Clean Fixture

The unit fixture at `tests/unit/models/technical_task_router_fixture.csv` is intentionally small but fully valid:

| Field | Count |
| --- | ---: |
| Rows | 3 |
| `planner_model=claude-sonnet-4-6` | 2 |
| `planner_model=gpt-5.4` | 1 |
| `coder_model=claude-sonnet-4-6` | 2 |
| `coder_model=gpt-5.4` | 1 |
| `reviewer_model=claude-sonnet-4-6` | 2 |
| `reviewer_model=gpt-5.4` | 1 |

The local Wavemill export inspected on 2026-05-30 had 696 data rows but still contained invalid `<synthetic>` available-model entries and bare `reviewer_model=deep` values. Regenerate or clean that export before using it for a production Model 30 registration.
