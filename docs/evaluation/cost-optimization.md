# Cost Optimization for HEK Evaluations

This guide focuses on LLM judge and evaluation cost control.

Related pages:
- [CI/CD Integration](./cicd-integration.md)
- [Troubleshooting](./troubleshooting.md)

## Primary cost drivers

- Number of rows evaluated
- Number of judges/metrics per row
- Model choice for judges
- Repeated runs without caching/resume

## Practical controls

## 1. Sample smartly

- Use stratified sampling for PR checks
- Reserve full datasets for release gates

## 2. Limit judge dimensions

`create_generation_judge(metrics=[...])` should include only dimensions you enforce.

## 3. Use resume and deterministic seeds

For CLI evaluations, prefer:
- `--resume auto`
- `--seed <fixed-value>`

This avoids unnecessary duplicate runs.

## 4. Cap runtime budget

Use `--max-cost` in CI to fail fast.

```bash
hokusai eval run my-model eval_spec.json --max-cost 5 --resume auto --output ci
```

## 5. Tier judge models by environment

- PR: cheaper/faster judge model
- Main/release: higher-quality judge model

Use `JudgeConfig(model="...")` per environment.

## 6. Cache immutable eval specs

If dataset hash and model revision are unchanged, reuse prior result or resume run.

## 7. Keep manifests small and focused

Log only required and decision-relevant metrics in HEM for easier long-term tracking.

## Example policy

- PR: 200 rows, 1 judge dimension, cost cap $1
- Main: 1,000 rows, 2-3 dimensions, cost cap $5
- Release: full dataset, full gate checks, cost cap $20
