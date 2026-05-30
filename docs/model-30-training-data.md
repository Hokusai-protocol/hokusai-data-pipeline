# Model 30 Training Data

Model 30 must be trained from the privacy-safe Wavemill router export, not from synthetic seed rows.

## Source

Generate the training export from the Wavemill repository:

```sh
cd ../../wavemill
npx tsx tools/export-hokusai-router-dataset.ts -o .wavemill/evals/hokusai-router-dataset.csv
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
