# Rework Risk baselines: trivial and classical JIT (HOK-3024)

Arms 1 and 2 of the baseline ladder, on the 12 development repos only. The 6
HOK-3028 evaluation-slice repos were never read. Target: 30-day
`corrective_rework` (`cr-0.1.0`). Features: `rr-merge-features/1.0.0`, `feature.*`
only. Datasets come from `src/arbiter/rework_dataset.py` (HOK-2818).
Hyperparameters were fixed in `src/arbiter/baselines.py` before the run and not
tuned. Full results: `hok-3024-baselines.json`. Per-repo results name repos and
are kept outside git.

**Label quality: go.** The rule was written before the run. The gradient-boosted
arm had to reach an AUC interval lower bound of at least 0.55 on the time split,
a top-decile capture lower bound of at least 15%, and AUC of at least 0.55 on at
least 9 of 12 held-out repos. It reached 0.693, 28.8% and 12 of 12.

## Time split

Train on PRs merged before 2026-02-01 whose label window closed by then: 168,870
rows, 3.0% positive. Evaluate on PRs merged from 2026-02-01: 88,938 rows, 2,191
positive (2.5%). Brackets are 95% bootstrap intervals.

| Arm | AUC | Top-decile capture | Brier skill | ECE |
| --- | --- | --- | --- | --- |
| Prior (training base rate) | 0.500 | 10% | 0 | 0.006 |
| Lines changed alone | 0.646 [0.636, 0.658] | 19.5% [17.9, 21.0] | | |
| Files touched alone | 0.647 [0.635, 0.660] | 22.6% [20.9, 24.3] | | |
| File commits, 90 days, alone | 0.593 [0.581, 0.604] | 13.8% [12.4, 15.2] | | |
| Author's prior commits alone (fewer is riskier) | 0.491 [0.479, 0.503] | 7.1% [6.3, 7.9] | | |
| Logistic regression, 4 trivial inputs | 0.650 [0.639, 0.662] | 20.7% [19.1, 22.5] | −0.001 | 0.009 |
| Logistic regression, all 28 inputs | 0.680 [0.668, 0.692] | 29.0% [27.0, 31.2] | 0.013 | 0.007 |
| Gradient boosting, all 28 inputs | **0.704 [0.693, 0.716]** | **30.5% [28.8, 32.5]** | 0.011 | 0.009 |

Within each repo (one pooled model, scored repo by repo), the gradient-boosted
arm's AUC runs from 0.58 to 0.77 (median 0.68), and its top-decile capture runs
from 17% to 45% (median 26%).

By evaluation quarter, ranking holds steady while calibration drifts:

| Quarter | Rows | Positives | GBM AUC | GBM top decile | Mean predicted | Observed |
| --- | --- | --- | --- | --- | --- | --- |
| 2026Q1 | 27,277 | 768 | 0.713 | 31.5% | 3.2% | 2.8% |
| 2026Q2 | 43,729 | 1,046 | 0.692 | 29.6% | 3.3% | 2.4% |
| 2026Q3 | 17,932 | 377 | 0.727 | 32.4% | 3.6% | 2.1% |

## Leave-repo-out

There is one model per held-out repo, trained on the other 11.

| Arm | Per-repo AUC, min / median / max | Per-repo top decile, median | Per-repo Brier skill, min / median |
| --- | --- | --- | --- |
| Lines changed alone | 0.58 / 0.65 / 0.75 | 21.8% | |
| Logistic regression, 4 trivial inputs | 0.59 / 0.66 / 0.75 | 23.7% | −0.06 / 0.008 |
| Logistic regression, all 28 inputs | 0.57 / 0.67 / 0.75 | 26.3% | −0.09 / 0.010 |
| Gradient boosting, all 28 inputs | 0.59 / 0.66 / 0.77 | 25.5% | −0.20 / 0.002 |

## What this means for the ladder

- **The label discriminates.** Merge-time features rank eventual rework at about
  0.70 AUC and put about 30% of it in the top-risk decile, three times random.
  That holds in every development repo and in every held-out repo.
- **Size carries most of the trivial signal.** Lines changed or files touched
  alone reach 0.65. Author experience alone carries none (0.49). Engineered
  features add about 0.05 AUC and 8 to 10 points of top-decile capture over
  the trivial model. This is the bar a model arm has to beat.
- **Calibration is the weak spot.** Brier skill over the base rate is close to
  zero everywhere. Over-prediction grows as the label rate falls (3.6% predicted
  against 2.1% observed by 2026Q3). On a new repo, probabilities can be badly
  off (Brier skill down to −0.20) even when ranking is fine. HOK-3028 arms should
  be compared on ranking metrics, with calibration recomputed per period and per repo
  or recalibrated.
- **Leave-repo-out favours simpler models.** The gradient-boosted arm leads on
  the time split but not across repos, where logistic regression matches it on
  ranking and is better calibrated.
- **Agent-marker drift (HOK-3023)** applies here: rates rise across the window,
  so report HOK-3028 results by period.
- The pooled out-of-fold AUC in the JSON mixes 12 models with different base
  rates (the prior arm scores 0.36 there), so use the per-repo figures.
