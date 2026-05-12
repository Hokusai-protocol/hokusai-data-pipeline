# Sales Custom Outcome Eval — Metric Contract (v1)

## Objective and Scope

This document is the canonical contract for the four Hokusai sales outcome metrics used by
DeltaOne comparator dispatch, HEM tag emission, and the sales outcome row schema.

**In scope:**

- Canonical Hokusai metric names and their MLflow-safe key equivalents.
- Direction, metric family, comparator, aggregation, threshold semantics, and unit of
  analysis for each metric.
- Scorer refs expected by `eval_spec` and the HEM/DeltaOne tags they emit.
- The benchmark row schema for sales outcome rows, including required and optional fields.
- Denominator behavior for the four label/coverage edge cases.
- Measurement policy values and which are mint-eligible.

**Out of scope (for this contract):**

- Scorer implementation logic (see `src/evaluation/scorers/builtin.py`).
- DeltaOne evaluator dispatch internals (see `src/evaluation/deltaone_evaluator.py`).
- Database schema changes or API endpoint additions.
- Site UI changes or `gtm-backend` implementation.

## Related Documents

- [`docs/sales-custom-evals-mint-eligibility.md`](sales-custom-evals-mint-eligibility.md) —
  Policy matrix, causal attribution rationale, and fixture index.
- [`docs/custom-outcome-evals-mlflow-foundation.md`](custom-outcome-evals-mlflow-foundation.md) —
  `eval_spec` JSONB storage contract and canonical Hokusai name vs MLflow key semantics.
- [`schema/sales_outcome_row.v1.json`](../schema/sales_outcome_row.v1.json) — JSON Schema for
  benchmark row export from `gtm-backend`.
- [`src/evaluation/sales_metrics.py`](../src/evaluation/sales_metrics.py) — Machine-readable
  constants module that encodes this contract.

---

## Metric Table

| Field | `sales:qualified_meeting_rate` | `sales:revenue_per_1000_messages` | `sales:spam_complaint_rate` | `sales:unsubscribe_rate` |
|---|---|---|---|---|
| **Hokusai name** | `sales:qualified_meeting_rate` | `sales:revenue_per_1000_messages` | `sales:spam_complaint_rate` | `sales:unsubscribe_rate` |
| **MLflow name** | `sales_qualified_meeting_rate` | `sales_revenue_per_1000_messages` | `sales_spam_complaint_rate` | `sales_unsubscribe_rate` |
| **Direction** | `higher_is_better` | `higher_is_better` | `lower_is_better` | `lower_is_better` |
| **Metric family** | `proportion` | `zero_inflated_continuous` | `proportion` | `proportion` |
| **Comparator** | `proportion` | `zero_inflated_continuous` | `proportion` | `proportion` |
| **Aggregation** | `MEAN` | `MEAN_PER_N` | `MEAN` | `MEAN` |
| **Unit of analysis** | `prospect_conversation` | `prospect_message` | `prospect_message` | `prospect_message` |
| **Unit** | `proportion` | `usd_per_1000_messages` | `proportion` | `proportion` |
| **Scorer ref** | `sales:qualified_meeting_rate` | `sales:revenue_per_1000_messages` | `sales:spam_complaint_rate` | `sales:unsubscribe_rate` |
| **HEM tags** | `hokusai.primary_metric`, `hokusai.mlflow_name`, `hokusai.scorer_ref`, `hokusai.measurement_policy` | same | same | same |
| **DeltaOne tags** | `hokusai.primary_metric`, `hokusai.mlflow_name`, `hokusai.scorer_ref`, `hokusai.measurement_policy` | same | same | same |

### Threshold Semantics

| Metric | Threshold semantics |
|---|---|
| `sales:qualified_meeting_rate` | Passes when observed rate ≥ threshold **and** improves over baseline per the proportion comparator. Threshold is a fraction in `[0, 1]`, not a percentage. |
| `sales:revenue_per_1000_messages` | Passes when observed USD per 1,000 delivered messages ≥ threshold **and** improves over baseline per the zero-inflated-continuous comparator. Threshold unit is USD per 1,000 delivered messages unless the row carries an explicit `revenue_currency` field. |
| `sales:spam_complaint_rate` | **Guardrail.** Passes when observed rate ≤ threshold. Blocking lower-is-better guardrail: a candidate fails if its spam complaint rate exceeds the threshold. Threshold is a fraction in `[0, 1]`. |
| `sales:unsubscribe_rate` | **Guardrail.** Passes when observed rate ≤ threshold. Blocking lower-is-better guardrail: a candidate fails if its unsubscribe rate exceeds the threshold. Threshold is a fraction in `[0, 1]`. |

---

## Measurement Policy Table

| Policy | Mint eligible | How outcome is attributed |
|---|---|---|
| `online_ab` | **Yes** | Prospective randomized live treatment/control split collects real outcomes for both arms. |
| `reward_model` | **Yes** (with validated/calibrated model) | A registered reward model calibrated against held-out revenue outcomes scores each message. |
| `off_policy` | **Yes** (when propensity/overlap guardrails pass) | Logged propensities from the production policy enable importance-weighted estimation over historical data. |
| `exact_observed_output` | **Yes** (byte-identical SHA-256 hash join only) | Generated output exactly matches a logged sent message via SHA-256 hash; revenue is the historically observed outcome for that exact message. |
| `diagnostic_only` | **Never** | Logs diagnostic quality signals; no causal or exact-correspondence path to revenue exists. |

## Measurement Policy Selection Guide

Choose a policy based on your data collection infrastructure and causal attribution requirements.

### `diagnostic_only`

Logs quality signals for observability without any causal attribution claim. Use when:
you want to monitor model behavior before deploying a revenue-linked policy, or when no
approved attribution mechanism is available. **Never mint-eligible.** The `mint_eligible`
flag is hardcoded `false` in the eval_spec; no amount of metric improvement triggers a mint.

### `exact_observed_output`

Requires SHA-256 hash-join between the generated message and a logged sent message in the
historical outcomes dataset. Use when your model reproduces messages that were already sent
and logged, enabling exact outcome attribution. Mint-eligible when the hash join succeeds
and DeltaOne accepts the result.

### `off_policy`

Uses importance weighting with logged propensity scores from the production policy. Use when
you have a logged-propensity dataset and the overlap between historical and candidate
distributions is acceptable (guardrails enforce this). Mint-eligible when propensity overlap
guardrails pass and DeltaOne accepts.

### `online_ab`

Prospective randomized live A/B test with real outcome collection. The gold standard - no
counterfactual assumptions. Use when you have the infrastructure to run a controlled live
experiment. Mint-eligible when DeltaOne accepts the result.

### `reward_model`

Uses a validated, calibrated reward model as a proxy for revenue outcome. Use when a
reward model has been evaluated against held-out revenue data and meets the calibration
threshold. The reward model must itself be registered in the scorer registry. Mint-eligible
when DeltaOne accepts and the reward model's calibration tag passes.

### Alias Note

The issue text (HOK-1585) used the shorthand `exact_observed`. The canonical serialized value
in eval_spec fixtures, schema enums, and HEM tags is **`exact_observed_output`**. Schema
constants and JSON Schema only accept `exact_observed_output`. Callers that receive
`exact_observed` from older sources must normalize before lookup or validation.

---

## Row Schema

The benchmark row schema for sales outcome rows is defined in
[`schema/sales_outcome_row.v1.json`](../schema/sales_outcome_row.v1.json).

The schema version sentinel is `"sales_outcome_row/v1"` (exposed as
`SALES_OUTCOME_ROW_SCHEMA_VERSION` in `src/evaluation/sales_metrics.py`).

### Required Fields

| Field | Type | Constraints | Description |
|---|---|---|---|
| `schema_version` | string | `const: "sales_outcome_row/v1"` | Schema version sentinel. |
| `row_id` | string | minLength 1 | Unique identifier for the row. |
| `benchmark_spec_id` | string | minLength 1 | ID of the benchmark spec this row belongs to. |
| `eval_id` | string | minLength 1 | Evaluation run identifier. |
| `model_id` | string | minLength 1 | Model identifier. |
| `campaign_id` | string | minLength 1 | Sales campaign identifier. |
| `unit_id` | string | minLength 1 | Identifier of the unit of analysis (prospect or message). |
| `unit_of_analysis` | string | enum: `prospect_conversation`, `prospect_message` | Observational unit for this row. |
| `measurement_policy` | string | enum of five canonical values | Measurement policy governing this row. |
| `metric_name` | string | enum of four `sales:*` canonical names | Metric this row contributes to. |
| `scorer_ref` | string | minLength 1 | Scorer registry ref. Must match the registered scorer for `metric_name`. |
| `message_count` | integer | minimum 0 | Total messages sent for this unit. |
| `delivered_count` | integer | minimum 0 | Messages confirmed delivered. |
| `numerator` | number | minimum 0 | Numerator contribution (events observed). |
| `denominator` | number | minimum 0 | Denominator contribution (eligible observations). |
| `observed_at` | string | format: date-time | Timestamp when the row was observed/computed. |
| `label_status` | string | enum: `observed`, `missing`, `delayed`, `partial` | Label availability status. |

### Optional Fields

| Field | Type | Description |
|---|---|---|
| `prospect_id` | string | Prospect (contact) identifier. |
| `conversation_id` | string | Conversation thread identifier. |
| `message_id` | string | Individual message identifier. |
| `arm` | string | A/B arm assignment (`treatment` or `control`). |
| `output_sha256` | string | SHA-256 of the generated message output, `0x`-prefixed 64-hex. |
| `label_observed_at` | string (date-time) | When the outcome label was observed. |
| `label_available_at` | string (date-time) | When the outcome label became available after the event window. |
| `outcome_window_days` | integer | Outcome observation window in days. |
| `coverage_fraction` | number | Fraction of expected labels that are available, in `[0, 1]`. |
| `qualified_meeting` | boolean or null | Whether a qualified meeting was booked (null = unobserved). |
| `revenue_amount_cents` | integer | Revenue attributed to this row in cents (integer; use `revenue_currency` for non-USD). |
| `revenue_currency` | string | ISO 4217 currency code (`^[A-Z]{3}$`), default `USD`. |
| `spam_complaint` | boolean or null | Whether a spam complaint was received (null = unobserved). |
| `unsubscribe` | boolean or null | Whether an unsubscribe event was received (null = unobserved). |
| `source_system` | string | Source system identifier (e.g., `salesforce`, `hubspot`). |
| `metadata` | object | Arbitrary additional metadata. |

### Example Rows

Concrete example rows for each metric are in `schema/examples/`:

| File | Metric | Policy |
|---|---|---|
| `sales_outcome_row.qualified_meeting.v1.json` | `sales:qualified_meeting_rate` | `online_ab` |
| `sales_outcome_row.revenue.v1.json` | `sales:revenue_per_1000_messages` | `exact_observed_output` |
| `sales_outcome_row.spam_complaint.v1.json` | `sales:spam_complaint_rate` | `online_ab` |
| `sales_outcome_row.unsubscribe.v1.json` | `sales:unsubscribe_rate` | `online_ab` |
| `sales_outcome_row.invalid_negative_count.v1.json` | — | — (invalid: negative numerator) |

---

## Scorer Input Contract

Each registered sales scorer (`src/evaluation/scorers/builtin.py`) accepts a list of
`sales_outcome_row/v1` dicts and derives all metric values from the canonical row fields
below. Scorers do **not** consume the `numerator` or `denominator` fields as authoritative
inputs; those fields exist for documentation and traceability only.

### Canonical Input Fields

| Field | Type | Used by |
|---|---|---|
| `delivered_count` | integer ≥ 0 | `revenue_per_1000_messages`, `spam_complaint_rate`, `unsubscribe_rate` |
| `qualified_meeting` | boolean or null | `qualified_meeting_rate` |
| `revenue_amount_cents` | integer ≥ 0 or null | `revenue_per_1000_messages` |
| `revenue_currency` | string (ISO 4217) | documented context only (output is always USD) |
| `spam_complaint` | boolean or null | `spam_complaint_rate` |
| `unsubscribe` | boolean or null | `unsubscribe_rate` |

### Revenue Formula

```
revenue_per_1000_messages (USD) =
    sum(revenue_amount_cents) / 100 / sum(delivered_count) * 1000
```

- Output unit is USD per 1,000 delivered messages when `revenue_currency` is omitted or `USD`.
- Rows with `delivered_count == 0` or absent are excluded from both numerator and denominator.
- Absent `revenue_amount_cents` for a delivered row contributes 0.0 cents.

### Missing-Label and Zero-Denominator Behavior

| Metric | Missing or null label field | Zero delivered / zero denominator |
|---|---|---|
| `qualified_meeting_rate` | Row excluded from numerator and denominator | Returns `0.0` |
| `revenue_per_1000_messages` | Absent `revenue_amount_cents` contributes 0.0 cents | Returns `0.0` |
| `spam_complaint_rate` | Row excluded from numerator and denominator | Returns `0.0` |
| `unsubscribe_rate` | Row excluded from numerator and denominator | Returns `0.0` |

---

## Denominator Behavior

### `sales:qualified_meeting_rate`

| Case | Behavior |
|---|---|
| **Zero messages** | Metric value is `0.0`. Row must carry `label_status` and `coverage_fraction` reflecting the zero denominator. Rows with zero denominator are not mint-sufficient and fail coverage/min-examples guardrails. |
| **Missing label** | Rows with a missing or null `qualified_meeting` label are excluded from both numerator and denominator. Do not treat a missing label as a negative outcome. |
| **Delayed label** | Before `label_available_at` or the configured outcome window closes, mark `label_status='delayed'` and exclude from mint-eligible aggregation. `diagnostic_only` rows may log delayed rows for observability. |
| **Partial coverage** | Rows must carry `coverage_fraction`. Mint-eligible policies require the eval_spec coverage_policy guardrail to pass before a MintRequest is published. |

### `sales:revenue_per_1000_messages`

| Case | Behavior |
|---|---|
| **Zero messages** | Metric value is `0.0`. Row must carry `label_status` and `coverage_fraction` reflecting the zero denominator. Rows with zero denominator are not mint-sufficient and fail coverage/min-examples guardrails. |
| **Missing label** | Missing revenue for a delivered message contributes `0.0` **only** when the outcome window has closed and the row is labeled `observed`. Otherwise mark `delayed` or `missing` and exclude from mint-eligible aggregation. |
| **Delayed label** | Before `label_available_at` or the configured outcome window closes, mark `label_status='delayed'` and exclude from mint-eligible aggregation. `diagnostic_only` rows may log delayed rows for observability. |
| **Partial coverage** | Rows must carry `coverage_fraction`. Mint-eligible policies require the eval_spec coverage_policy guardrail to pass before a MintRequest is published. |

### `sales:spam_complaint_rate` and `sales:unsubscribe_rate`

| Case | Behavior |
|---|---|
| **Zero messages** | Metric value is `0.0`. Row must carry `label_status` and `coverage_fraction` reflecting the zero denominator. Rows with zero denominator are not mint-sufficient and fail coverage/min-examples guardrails. |
| **Missing label** | Missing spam/unsubscribe event flags for delivered messages must be treated as **not observed**, not silently `false`, unless the source system guarantees absence-as-false after the event window closes. Exclude uncertain rows. |
| **Delayed label** | Before `label_available_at` or the configured outcome window closes, mark `label_status='delayed'` and exclude from mint-eligible aggregation. `diagnostic_only` rows may log delayed rows for observability. |
| **Partial coverage** | Rows must carry `coverage_fraction`. Mint-eligible policies require the eval_spec coverage_policy guardrail to pass before a MintRequest is published. |

---

## Versioning

### Dataset Versioning Contract

For `sales_outcome_row/v1` datasets, the GTM-generated `input_dataset_hash` must be persisted as
the BenchmarkSpec `dataset_version` in canonical `sha256:<64 lowercase hex>` form.

- Dataset upload responses expose the canonical value in both `sha256_hash` and
  `dataset_version`.
- `hokusai-site` should use that canonical value directly when creating Hokusai BenchmarkSpecs.
- Remote `dataset_reference` values such as `s3://bucket/sales/outcomes.json` require a canonical
  `dataset_version`; `"latest"` only works for local-file eval flows where the pipeline can hash
  the readable file content itself.

Example remote BenchmarkSpec fields:

```json
{
  "dataset_reference": "s3://bucket/sales/outcomes.json",
  "dataset_version": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

This is version `v1` of the sales outcome row contract. Future incompatible row changes (new
required fields, enum additions, type changes) should introduce a side-by-side schema version
(e.g., `sales_outcome_row/v2`) rather than mutating the v1 schema in-place. The
`schema_version` field on each row determines which schema version applies.
