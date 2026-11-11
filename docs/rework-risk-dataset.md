# Rework Risk training dataset (HOK-2818)

`src/arbiter/rework_dataset.py` turns the published merge-time features and
`corrective_rework` labels into a training dataset. The split rules are enforced
in code: a configuration that would leak fails rather than warning. Every arm
(HOK-3024, HOK-3021, HOK-3028) trains and evaluates through it, and none keeps
its own split code.

## Inputs

Both roots hold one `<owner>__<name>/` directory per repo.

| Input | File | Published at |
| --- | --- | --- |
| Merge-time features, `rr-merge-features/1.0.0` (HOK-3023) | `features.jsonl.gz` | `s3://hokusai-pipeline-data-development/arbiter-corpus/hok-3023/` |
| `corrective_rework` target, definition `cr-0.1.0` (HOK-3020) | `corrective.jsonl.gz` | `.../arbiter-corpus/hok-3022/as-of=2026-10-20/` |
| S2 survival rows, which carry the merge SHA (HOK-3022) | `s2.jsonl.gz` | same |
| HOK-3028 evaluation slice | one JSON file | private: `~/.hokusai-private/hok-3028-slice.json` |

Feature rows join to labels on the PR, and the merge SHA must agree with the S2
row, so the join holds on `(repo, merge_sha)`.

## Running it

```bash
export HOKUSAI_SCAN_CMD="node /path/to/hokusai-scan.mjs"   # or hokusai-scan on PATH

# time split: train on PRs merged before 2026-02-01, evaluate from then on
python scripts/arbiter/assemble_rework_dataset.py --split time --train-until 2026-02-01 \
  --out ~/hokusai-data/arbiter-datasets/rr-time-2026-02-01

# leave-repo-out: one fold per development repo
python scripts/arbiter/assemble_rework_dataset.py --split leave-repo-out \
  --out ~/hokusai-data/arbiter-datasets/rr-lro
```

Write datasets outside git: they name the development repos. The CLI prints
pooled counts only. Exit codes: 0 assembled, 1 leakage or contract break, 2 bad
arguments or inputs.

In code:

```python
from src.arbiter.rework_dataset import load_dataset

dataset = load_dataset(path, slice_file="~/.hokusai-private/hok-3028-slice.json")
for split in dataset.splits():          # one pair for a time split, one per repo for leave-repo-out
    model.fit(split.X("train"), split.y("train"), sample_weight=split.weights("train"))
    scores = model.predict_proba(split.X("eval"))[:, 1]
```

`split.X()` returns the audited `feature.*` columns only: no label, weight,
identity or segment columns. Every pair is checked before it is yielded.

## What it refuses

| Rule | How |
| --- | --- |
| Arm inputs pass the shared validator | Feature columns go through `hokusai-scan corpus-feature-audit`; exit 1 or 2 stops assembly. A missing validator is an error, never a pass |
| Segment columns are for reporting | `segment.*` columns are carried only with `--allow-segments`, and never appear in `X` |
| One frozen feature manifest | Rows from any version other than `rr-merge-features/1.0.0` stop assembly |
| One pinned target | Label rows must share one schema, definition, labeller and `as_of`; the definition must be listed in `TARGET_DEFINITIONS` |
| The evaluation slice stays sealed | The slice file is required. Slice repos are never read, and asking for one is an error |
| Time periods do not overlap | `eval_from` before `train_until` is rejected |
| Training labels close before training ends | A training row needs `as_of + horizon <= train_until`. Rows whose label window crosses are held back as `embargo` |
| Leave-repo-out keeps repos apart | A repo on both sides is rejected |
| Labels had time to mature | A row whose label window had not closed when the labels were computed is rejected |
| Every label provenance is weighted on purpose | Only `harvested` has a weight (1.0). Owner-corrected (Tier 2b) rows are rejected until they have been used for labeller error analysis and given a weight |

`check_split` applies the split rules to any train/evaluation pair, including
one a caller built by hand.

Rejected rows are written to `rejected.jsonl.gz` with their reason, and counted
by reason in the provenance.

## Output

| File | Contents |
| --- | --- |
| `rows.parquet` | Accepted rows: identity, `as_of`, `label_observed_until`, `label`, `label_provenance`, `sample_weight`, then the feature and segment columns |
| `rejected.jsonl.gz` | One line per rejected row: repo, PR, merge SHA, reason |
| `base_rates.json` | Label base rates by repo and horizon (14, 30, 60 days), pooled, and by split role |
| `provenance.json` | Schema versions (dataset, feature manifest, label, target definition, labellers, decision-record contract), split, slice SHA-256, column audit, input file hashes, code commit, counts, and the SHA-256 of each file above |

`load_dataset` checks the file hashes, schema versions, column list and slice
hash, and runs the column audit and the split checks again.

## Tests

`tests/unit/arbiter/` covers assembly and every refusal above. The shared
conformance cases from hokusai-sdk (`leakage-conformance.json`, vendored in
`tests/fixtures/arbiter/`) run through the assembly's own column gates against
the real validator. The `Arbiter dataset` workflow builds the validator from a
pinned hokusai-sdk commit and runs the tests, failing if the validator is
missing or the vendored cases differ from the SDK.

## Not in this version

- Wavemill history and Survival Check rows. They arrive through
  `arbitration_row/v1` (HOK-2817), with the exit criterion of at least 500
  labelled Wavemill rows and the `executed_route` metadata column.
- Evaluating on the HOK-3028 slice. That run is pre-registered and will be added
  under HOK-3028 as its own entry point.
