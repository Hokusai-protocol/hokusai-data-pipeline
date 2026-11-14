# Frontier chat-model arm for Rework Risk (HOK-3027, arm 3)

**Status:** FROZEN at `llm-snap/0.1.0`, 2026-11-14 (content hash `88b8514d…dd062b`, pinned in the tests). Any change to the prompt, schema, model, effort, state rules or gate sample needs a new version.
**Model:** `claude-opus-5-5` at effort `medium`, knowledge cutoff June 2026 (owner decision, 2026-11-14).
**Code:** `src/arbiter/llm_arm.py`, `scripts/arbiter/run_llm_arm.py`, `scripts/arbiter/eval_llm_dev.py`. Registered for the gate as `hok-3027-frontier-llm`.

This session did not read the HOK-3028 evaluation slice or list the development repos. Every number below comes from development rows.

## What the model is asked

One request per PR. The model gets the same input as arm 4 (Jev): the `jev-state/0.1.0` merge-time state, with the same redaction and the same 40,000-character diff budget. It answers the 14 questions of `jev-qs/0.1.0`, worded as Jev sees them, then gives `rework_risk_percent`: its probability that the change is reverted or explicitly repaired within 30 days.

The prompt tells the model to judge only what is shown, and not to identify the project or recall what happened to the change. It gives no base rate: arm 3 has no outcome history, and a base rate would come from labels. It says only that most merged changes are never reverted or repaired.

The answer is JSON, constrained by a schema. A Choice is one option, a Score is one level and a Noul is a probability from 0 to 100.

## Scores

| Variant | Score | Use |
| --- | --- | --- |
| `frontier_llm` | The stated probability. Equal probabilities are ordered by the composite below | The arm-3 number: "just ask a frontier LLM" |
| `frontier_llm.questions` | The 14 answers composed with arm 4's frozen hand-set weights | Like-for-like with Jev's questions-only composite |

Nothing is fitted to labels. The stated probability is reported for calibration as the model gave it: unlike arm 4, arm 3 gets no isotonic step, because the pre-registration gives that treatment to arm 4 only and fitting it would need scores on training rows.

A row is left unscored when its state cannot be rebuilt, when the model refuses, or when its answer does not fit the schema. No fallback model is used, so every score comes from one model. Unscored rows are counted.

## At the gate

`FrontierLlmArm.score` draws a fixed sample of 500 PRs per evaluation repo (owner decision, 2026-11-14): rows are ordered by `sha256(seed, repo, pr_number)` and the first 500 non-bot rows of each repo are taken. Every repo gets the same number because the gate metric weights repos equally. The arm sees no labels, so the sample cannot favor positives.

The issue suggested a few hundred PRs in all. At a 2% base rate that is about 7 positives, too few for top-decile capture. Six repos at 500 each is about 3,000 PRs and, at the measured price, about $110.

To run it, the gate needs `ANTHROPIC_API_KEY`, `--content-root` set to the corpus root, and `HOK3027_MAX_USD`. Answers are cached in `HOK3027_CACHE` (default `~/.hokusai-private/hok-3027/gate-scores.jsonl`). If the spend cap or a refused request stops the run, the arm raises instead of returning part of the sample; running the gate again resumes from the cache.

## Model memory

The model's reliable knowledge cutoff is June 2026. A PR merged from July 2026 on cannot have been in its training data; an earlier one might be, along with its revert. The development run therefore scores two periods separately: merged after 2026-06-30, and in the year up to it. The after-cutoff numbers are the ones to quote. A large gap between the periods would mean the model recalls outcomes.

The gate adapter does not split by period: it never sees the evaluation window. The gate write-up should split arm 3's rows at 2026-06-30 from the record.

## Development results

1,800 non-bot development PRs were scored on 2026-11-14 with `scripts/arbiter/run_llm_arm.py`: 250 positives and 650 negatives merged after the cutoff, and the same numbers from the year before it. Every request succeeded and none was refused. The same rows were scored by Jev. Answers are in `~/.hokusai-private/hok-3027/dev-scores.jsonl`; `scripts/arbiter/eval_llm_dev.py` wrote `hok-3027-llm-dev-results.json`.

The sample has far more positives than the population (target `cr-0.2.0` at 30 days, base rate 1.7% after the cutoff). Each row is weighted back to its repo's population, so the numbers below estimate what a random sample would give. Macro averages cover the 6 repos with at least 10 scored positives in the period. Chance for top-decile capture is 10%.

**After the cutoff (the numbers to quote):**

| Score | Pooled AUC | Macro top-decile capture | Per-repo range |
| --- | --- | --- | --- |
| `frontier_llm` (arm 3) | 0.794 | 45.0% | 27.3% to 90.9% |
| `frontier_llm.questions` | 0.736 | 33.1% | 27.3% to 39.5% |
| Jev, questions only | 0.687 | 31.0% | 16.0% to 45.5% |
| Jev, `steelman_composite` (arm 4 gate score) | 0.661 | 27.9% | 12.0% to 52.3% |
| `code_risk` (four facts only) | 0.589 | 20.1% | 0.0% to 50.0% |

**Before the cutoff:**

| Score | Pooled AUC | Macro top-decile capture |
| --- | --- | --- |
| `frontier_llm` (arm 3) | 0.801 | 41.1% |
| `frontier_llm.questions` | 0.670 | 21.7% |
| Jev, questions only | 0.637 | 21.7% |
| Jev, `steelman_composite` | 0.652 | 18.8% |
| `code_risk` | 0.614 | 21.0% |

* **Arm 3 ranks well above arm 4 on these rows.** After the cutoff its macro capture is 17.2 points above Jev's gate score, but with 6 repos the 95% CI is −3.5 to +35.5. Before the cutoff the difference is 22.2 points (CI +6.6 to +32.4). Pooled AUC is about 0.13 higher in both periods.
* **No sign of recall.** Arm 3's AUC is 0.794 after the cutoff and 0.801 before it. Capture is slightly higher after the cutoff. If the model were recalling reverts, the before-cutoff numbers would be clearly better.
* **The gain is in the overall judgment, not in the 14 answers.** Opus's answers composed with arm 4's weights are level with Jev's own (+2.1 points after the cutoff, CI −8.9 to +13.6; 0.0 before). The stated probability adds 12 to 19 points on top of that composite.
* **The stated probabilities are far too high.** The model's mean is 9.8% against a base rate of 1.7% after the cutoff (ECE 0.081, Brier 0.024, pooled). It was given no base rate. The ranking is usable; the raw probability is not.
* **This sets the bar for arm 5.** These are development rows, not the gate. But a trained model that cannot beat 45% capture on comparable rows would lose the "just ask a frontier LLM" comparison in §7 of the pre-registration.

## Cost

Measured on the 1,800 requests: $67.42 in all, or $0.037 per PR. A request averages 7,850 uncached input tokens, 3,230 cached prompt tokens and 270 output tokens. Input is 85% of the cost. The sample is richer in positives, which are larger changes, so a random sample costs a little less per PR.

| Run | PRs | USD |
| --- | --- | --- |
| Dry run | 12 | 0.60 |
| Development run (includes the dry-run rows) | 1,800 | 67.42 |
| Jev on the same rows | 1,529 new | 0.43 |
| Gate sample, estimated | about 3,000 | about 110 |

The Message Batches API would halve the price. It is not used: the resumable cache needs each answer as it arrives.

## Not done

* **Gate write-up split.** Arm 3's gate rows should be reported before and after 2026-06-30 (see "Model memory").
* **Calibration.** Arm 3's probability is raw. An isotonic step fitted on these 1,800 development answers would be cheap, but it is a new arm version and a pre-registration question.
* **Dependency.** The `anthropic` package is imported only when the arm calls the model; it is not in the pinned requirements files.
