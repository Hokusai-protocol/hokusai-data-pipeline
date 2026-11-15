# Jev question set for Rework Risk arm 4 (HOK-3026)

**Status:** FROZEN, 2026-11-14, after owner review. Any change to a question, weight, transform or state rule needs a new version.
**Versions:** `jev-qs/0.1.0` (questions and composition, content hash `9190f64a…a9adc4`, pinned in the tests), `jev-state/0.1.0` (state and truncation), model `jev-1.14.0`. Answers cached under the `-draft` names were produced by exactly this content and count as these versions.
**Code:** `src/arbiter/jev_questions.py`, `src/arbiter/jev_state.py`, `src/arbiter/jev_client.py`, `src/arbiter/jev_arm.py`, `scripts/arbiter/run_jev_dry_run.py`, `scripts/arbiter/run_jev_arm.py`, `scripts/arbiter/eval_jev_dev.py`.

This session did not read the HOK-3028 evaluation slice or list the development repos. Every number below comes from development rows.

## Decisions raised before the dry run

1. **TypeSafe's terms.** The Master Customer Agreement, §2.3(b), says a customer will not "use the Services or any Output to perform model distillation, train a model to imitate the output of the Services, or develop (or to facilitate the development of) a similar or competing product or service". Arm 6 trains Rework Risk on Jev outputs, and arm 4 benchmarks Jev for a product positioned against it. Whether either is allowed is a legal reading, not an engineering one. Nothing is sent until the owner decides.
2. **Data retention.** TypeSafe commits not to train on inputs (Privacy Policy). The Data Processing Agreement gives no retention period: data is kept "as long as necessary". Zero data retention is offered to enterprise customers only. The text sent is public PR content with identifiers redacted.
3. **Gate score.** The proposed arm-4 gate score is `steelman_composite`: the questions plus four merge-time facts that code computes exactly. The alternative is the questions alone. See "Composition".
4. **How the gate score is chosen.** The brief says weights are set by hand and never fitted to labels. The pre-registration (§4) allows tuning decisions on development repos. Proposal: weights stay hand-set; development results may be used only to fix a question's wording and to choose between the two composites above.

**Owner decisions, 2026-11-14:** (5) the three below-chance terms stay in the gate score; the question set and state rules are frozen. (1) the competitive-use clause is not treated as a blocker; whether to run arm 6 at all is open. (2) Retention terms accepted. (3) `steelman_composite` is the proposed gate score. (4) Agreed: weights stay hand-set; development results only fix wording and choose between the two composites.

## What Jev is asked

One request per PR: the state plus all 14 questions, answered in parallel. Each question tests one property a reviewer could judge in seconds. Facts that code can compute exactly (size, churn, author history) are not asked, following TypeSafe's guidance that Jev does not count or compare numbers reliably.

| Question | Type | Asks | Weight |
| --- | --- | --- | --- |
| `blast_radius` | Score, 4 levels | How much of the software depends on the changed code | 0.13 |
| `logic_complexity` | Score, 4 levels | How intricate the changed logic is | 0.11 |
| `test_adequacy` | Score, 5 levels | How well the test changes exercise the changed behavior | 0.11 |
| `change_type` | Choice, 10 options | Bug fix, feature, refactor, performance, revert, reland, dependency or build, configuration, tests only, docs only | 0.10 |
| `environment_sensitive` | Noul | Behavior depends on platform, compiler, architecture or runtime version | 0.09 |
| `changes_public_interface` | Noul | Existing callers can observe a difference | 0.07 |
| `removes_safeguards` | Noul | Validation, error handling, assertions or tests removed or weakened | 0.07 |
| `touches_concurrency` | Noul | Locks, threads, async ordering or shared state change | 0.06 |
| `touches_persistence_or_format` | Noul | Schema, migration, or serialized, on-disk or wire format changes | 0.05 |
| `scope_exceeds_intent` | Noul | The diff does things the title and description do not account for | 0.05 |
| `workaround_or_incomplete` | Noul | The change calls itself temporary, partial or needing a follow-up | 0.05 |
| `touches_auth_or_security` | Noul | Authentication, authorization, secrets or cryptography change | 0.04 |
| `pattern_consistency` | Score, 4 levels | Whether the new code follows or bypasses the surrounding conventions | 0.04 |
| `description_explains_change` | Noul | The description says what changes and why (protective) | 0.03 |

The exact wording and level descriptions are in `QUESTIONS`. They cover the six dimensions in the issue: load-bearing paths (`blast_radius`), structural complexity, test-coverage delta, pattern consistency, scope creep, and risky archetypes (the `touches_*` questions, `environment_sensitive` and `change_type`).

## Composition

Each answer becomes a risk in [0, 1]:

* **Noul:** P(true). `description_explains_change` is inverted.
* **Score:** score divided by the top level. `test_adequacy` is the exception: its level 0 is "nothing to test", so its risk is the expectation of (0, 0.1, 0.4, 0.8, 1.0) over the level probabilities.
* **Choice:** the expectation of a per-type risk over the option probabilities. Reland is 1.0, new feature and performance 0.7, dependency or build 0.6, refactor and bug fix 0.5, configuration 0.4, revert 0.3, tests only 0.1, docs only 0.0.

`composite` is the weighted sum of the 14 risks. The weights sum to 1. They were set by hand before any answer or label was seen.

`steelman_composite = 0.6 × composite + 0.4 × code_risk`. `code_risk` is a hand-weighted sum of the four arm-1 trivial features with arm 1's directions: lines touched (0.35), files touched (0.15), commits to the touched files in 90 days (0.25), and the author's prior commits (0.25, inverted). Each is log-scaled to a cap near the 99th percentile of development feature values. No label was read to set a cap.

Why include `code_risk`: the pre-registration compares two models that "see the same frozen merge-time information". Without these facts, arm 4 would lose to arm 5 partly for lack of history the manifest already holds, which is the strawman the issue rules out.

The shared evaluator fits isotonic calibration on training folds and reports raw and recalibrated numbers (pre-registration §3). That is the only learned step.

**Rows Jev cannot score.** If the state cannot be rebuilt, or the request still exceeds the context after two halvings of the diff budget, the row's `composite` is the median `composite` of the training fold. Such rows are counted and reported.

## State

```
{"change": {"title", "description", "files": [{path, status, kind, size, diff}], "diff"}}
```

* **Title and description** are the versions at `as_of`, rebuilt from the private capture with the same rules as `titleAt` and `bodyAt` in hokusai-sdk. HTML comments are removed. The description is cut at 6,000 characters. A version that no longer exists is sent as `null`.
* **Diff** is `git diff <base_sha> <merge_sha>` with three lines of context and git's header lines removed.
* **Files** lists up to 100 paths, largest first, each with its kind (source, test, docs, generated, binary), a size word instead of a number, and whether its diff is shown in full, in part or not at all.
* **Redaction:** URLs, the repo's `owner/name`, and issue and PR references everywhere; in prose also mentions, emails and the project's name. In 300 development states the repo's `owner/name` never survived. The code itself can still identify a project to a model that memorized it.

**Truncation rule.** The diff budget is 40,000 characters. If a request still exceeds the context, the budget is halved, at most twice. Generated, vendored, lock and binary files are never shown. Source files are filled first, then tests, then docs. Within a kind the budget is water-filled: small files are kept whole and large files share what is left, each cut at a line boundary with a marker. The state says when the diff is partial. Long context (262k tokens) is not used: TypeSafe documents it as slower and less accurate.

Measured on 300 random non-bot development PRs: every state built; 11% needed truncation; the encoded state has a median of 5.8k characters, a mean of 12.7k and a maximum of 69k.

## Hybrid arm inputs (HOK-3029)

`hybrid_features` exports 45 columns, all in [0, 1], with no weights and no composite:

| Question type | Columns |
| --- | --- |
| Noul | `jev.<question>.p` |
| Score | `jev.<question>.score_norm`, `jev.<question>.confidence`, `jev.<question>.p_level_<k>` |
| Choice | `jev.change_type.confidence`, `jev.change_type.p.<option>` |

`hybrid_feature_spec()` returns every name and type. HOK-3029 has to declare these columns in the feature manifest: the leakage validator rejects undeclared columns.

## Dry run

Twelve development PRs (six positives, six negatives, non-bot, seed 20261114) were scored on 2026-11-14. Per-row results are in `~/.hokusai-private/hok-3026/dry-run.jsonl`.

* Every request succeeded on `jev-1.14.0`. None exceeded the context, so no budget was halved.
* Input tokens per request: median 3.8k, mean 8.5k, maximum 24.6k, against a 32k per-question limit.
* The answers are not degenerate: 13 of the 14 risk terms range widely across the 12 PRs. `touches_auth_or_security` stayed below 0.05, as expected for a rare archetype.
* `steelman_composite` ran from 0.22 to 0.56. Twelve rows say nothing about ranking quality, and none is claimed.

## Development results

40,000 random non-bot development rows were scored on 2026-11-14 with `scripts/arbiter/run_jev_arm.py`: every request succeeded, none exceeded the context, and the run cost $9.52. Answers are in `~/.hokusai-private/hok-3026/dev-scores.jsonl`. `scripts/arbiter/eval_jev_dev.py` wrote `hok-3026-jev-dev-results.json`. The target is `cr-0.2.0` at 30 days; 894 rows are positive (2.2%). Scores are raw rankings, before calibration.

| Score | Pooled AUC | Macro top-decile capture (11 repos) | Per-repo range |
| --- | --- | --- | --- |
| `composite` (questions only) | 0.675 | 22.7% | 12.8% to 40.7% |
| `steelman_composite` | 0.682 | 23.9% | 8.7% to 39.3% |
| `code_risk` (four facts only) | 0.634 | 19.3% | 0.0% to 39.3% |

Chance is 10%. One repo had fewer than 10 positives in the sample and is left out of the macro average.

* **Gate score.** `steelman_composite` is 1.1 points above `composite` (95% CI −4.0 to +5.6): the data does not separate them. It is 4.6 points above `code_risk` alone (CI +0.3 to +10.8), so the questions add ranking power to the exact facts. `steelman_composite` stays the proposed gate score, on the design argument rather than on this difference.
* **Three terms rank below chance on their own:** `test_adequacy` (AUC 0.47), `touches_auth_or_security` (0.46) and `description_explains_change` as a protective term (0.45). Together they carry 0.18 of the weight. A plausible reading is size: larger changes come with tests and fuller descriptions, and are reverted more. That is a fact about the outcome, not a wording fault, so changing their direction or weight would be fitting to labels. They are left as set (owner decision, 2026-11-14). Removing them would raise macro capture by 1.2 points (95% CI −2.9 to +4.2), which is inside the noise. `sensitivity_composite`, the gate score without the three terms, is reported beside the gate score on the evaluation slice and never gates.
* **Not comparable with HOK-3024.** The published arm 1–2 numbers use target `cr-0.1.0` and different rows.

## Cost

Jev charges $0.042 per million input tokens; output is free. The dry run's `usage` fits about 1,100 tokens for the 14 questions plus one token per 2.5 characters of state. The state is billed once, not once per question. The densest state ran at 1.9 characters per token.

| Sample | Mean input tokens per PR | USD per 1,000 PRs |
| --- | --- | --- |
| Dry run (balanced, so larger PRs than usual) | 8,500 | 0.36 |
| 300 random development PRs, from the fit | 6,300 | 0.26 |

Scoring 100,000 PRs costs about $26. The slice's row count was not looked up. Arm 4's calibration also needs scores on training rows; all 169k development training rows would cost about $45.

## Model memory

TypeSafe publishes no training cutoff for Jev. Jev 1.14 was released on 2026-10-14, and the development rows end on 2026-08-01, so every PR may predate the cutoff. A before-and-after split needs the cutoff from TypeSafe. Until then, results are reported by merge quarter, and the most recent quarter is the closest to an honest number.

## Not done

* **Training cutoff.** Ask TypeSafe (see "Model memory").
* **Shared evaluator.** Per-repo macro averaging and the paired bootstrap belong to HOK-3028; `src/arbiter/baselines.py` has the metric functions to reuse. The rule for rows Jev cannot score is written above but not coded.
