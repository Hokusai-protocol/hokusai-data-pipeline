# Rework Risk gate runner (HOK-3028)

The gate runner scores every arm once on the evaluation slice and applies the
decision gate in `hokusai-sdk/docs/arbiter/rework-risk-preregistration.md`. Its
thresholds are copies of that document. The 2026-11-14 change-log entry there
settles three things the runner implements: which rows train an arm, what arm 5
reads, and how the runner reads §6.

Code:
- `src/arbiter/gate.py`: rules, row building, the bootstrap and the outcome.
- `src/arbiter/gate_arms.py`: arm adapters and the registry.
- `scripts/arbiter/run_gate.py`: the command line.

## Who sees what

| Step | Reads | Prints |
| --- | --- | --- |
| Slice check | `~/.hokusai-private/hok-3028-slice.json`, by path | Whether its SHA-256 matches §4. Never the repos, the window or the salt |
| Training rows | Development repos. A row's 30-day label window must close before the evaluation window starts | Rehearsal only. On the sealed slice the counts would date the window |
| Evaluation rows | Slice repos, merged inside the window | Power pass or fail |
| Arm `fit` | Training rows: identity, merge time, `feature.*`, content hashes, `label`, `sample_weight` | n/a |
| Arm `score` | Evaluation rows: the same columns without labels or segments | n/a |
| Record | Everything, in `~/.hokusai-private/hok-3028-gate/` | The outcome line and the record path |
| Public summary | The record without per-repo numbers or input lists | Written to `--public-out` |

Arm code never needs the repo names or the dates, so arm sessions stay blind.
At scoring time an arm could still infer the window from the training rows'
latest merge time. That is harmless, because by then every arm is frozen.

## Adding an arm

An arm is a class registered in `ARM_FACTORIES` (`src/arbiter/gate_arms.py`):

```python
class MyArm:
    arm_id = "hok-30xx-my-arm"
    version = "my-arm/1.0.0"            # frozen before scoring

    def variants(self) -> dict[str, str]:
        return {"my_arm": "arm5"}        # variant id -> role (arm1 ... arm6)

    def fit(self, train: pd.DataFrame, context: ArmContext) -> object: ...

    def score(self, fitted, rows: pd.DataFrame, context: ArmContext) -> dict[str, pd.DataFrame]:
        # one frame per variant, indexed like rows:
        #   score        float, used for ranking
        #   probability  float in [0, 1], used for calibration
        #                (required for arms 4 and 5; arm 4's is the recalibrated one)
        ...
```

- Every evaluation row must get a score, except under arm 3, which scores a
  sample and leaves the other rows NaN.
- `context.content_columns` names the `feature.content.*` hashes.
- `context.content_root` points at the private evidence cache. Content arms
  (arms 3–6) read the diff, title and body from there.
- Arm 3 is registered as `hok-3027-frontier-llm`. It also needs
  `ANTHROPIC_API_KEY` and `HOK3027_MAX_USD`; see `hok-3027-frontier-llm-arm.md`.

## Running it

```bash
export HOKUSAI_SCAN_CMD="node /path/to/hokusai-scan.mjs"

# The sealed slice: check the hash and the power. Nothing is scored.
python scripts/arbiter/run_gate.py preflight

# Rehearsal: 6 development repos stand in for the slice, and arms 1-2 stand in
# for arms 4-5. Safe to repeat.
python scripts/arbiter/run_gate.py rehearse --until 2026-08-01 --stand-ins \
  --resamples 1000 --record-dir ~/.hokusai-private/hok-3028-rehearsal \
  --public-out ~/.hokusai-private/hok-3028-rehearsal/summary.json

# The gate, once every arm is frozen and committed:
python scripts/arbiter/run_gate.py score \
  --arms hok-3024-baselines,<arm 3>,<arm 4>,<arm 5>,<arm 6> \
  --content-root <private evidence cache> --public-out docs/arbiter/hok-3028-gate-result.json
```

`score` refuses to run in any of these cases:
- the working tree is dirty;
- a rehearsal stand-in arm is listed;
- the slice has already been scored and no `--rerun-reason` is given. A rerun
  (§8.1) re-runs every arm and writes a new record next to the original.

A 10,000-resample run takes about 20 minutes on a laptop.

## The outcome

The runner checks the outcomes in this order:

1. **INCONCLUSIVE**: fewer than 5 repos, or fewer than 500 positives, among the
   primary rows (dependency bots excluded).
2. **TABLE-STAKES FAIL**: arm 5 doesn't beat every arm-1 and arm-2 variant,
   with a paired CI lower bound above 0.
3. **LOSS**: the CI upper bound of Δ is below 0.
4. **COMPELLING**: every condition below holds:
   - Δ ≥ 10 pp;
   - the CI lower bound of Δ is above 0;
   - the ratio is at least 1.25×;
   - Δ > 0 in at least ⅔ of repos;
   - arm 5 beats arms 1 and 2;
   - Brier and ECE are non-inferior on the CI upper bound.
5. **HALF-WIN**: every ranking condition holds, but calibration doesn't.
6. **TIE**: anything else.

All CIs come from the same 10,000 two-stage resamples: repos drawn with
replacement, then PRs drawn with replacement inside each repo.

The secondary questions are reported and never gate:
- arm 6 against the better of arms 4 and 5;
- arm 3 against arm 5, on arm 3's sample;
- the dependency-bot segment;
- the 14- and 60-day horizons, via `--horizon`.

The label-noise diagnostic for a TIE uses the HOK-3269 audit numbers already
recorded in the pre-registration. Results for the agent-authored segment
(HOK-2808) are not computed here yet.

## Rehearsal result, 2026-11-14

The rehearsal used 6 development repos as the stand-in slice and the other 6
for training. Arm 4 was played by JIT LR and arm 5 by JIT GBM, with 1,000
resamples. The outcome was **TABLE-STAKES FAIL**, which is what it should be:
the stand-in arm 5 is also an arm-2 variant, so its difference from arm 2 is
exactly 0.

The rehearsal also shows how wide the intervals are with 6 evaluation repos.
On paired differences in macro top-decile capture, the 95% CIs span about 10 to
15 points. For example, the stand-in arm 5 against lines changed was +0.6 pp,
with CI −5.8 to +7.2. To beat every arm-1 and arm-2 variant with the CI lower
bound above 0, arm 5 needs a real margin over even the trivial arms.
