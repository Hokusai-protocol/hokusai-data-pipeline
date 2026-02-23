# MLflow Judge Templates

Reusable LLM-as-a-judge templates for common evaluation scenarios.

## Verified MLflow API Surface

The implementation is built against the **runtime API that actually exists**:

- `mlflow.genai.make_judge(name, instructions, model)` is available.
- Module-level `mlflow.genai.get_judge` is **not** available in this runtime.
- Module-level `mlflow.genai.register_judge` is **not** available in this runtime.
- Registration is supported via instance method `judge.register(...)`.
- Registered scorer listing is available via `mlflow.genai.scorers.list_scorers(...)`.

The `JudgeConfig.temperature` field is included for forward compatibility, but
`make_judge` in this API surface does not currently accept a temperature argument.

## Available Factories

- `create_classification_judge(task_description, config=None)`
- `create_generation_judge(metrics, config=None)`
- `create_ranking_judge(config=None)`
- `create_session_scorer(config=None)`

## Basic Usage

```python
from src.evaluation.judges import (
    JudgeConfig,
    create_classification_judge,
    create_generation_judge,
    create_ranking_judge,
    create_session_scorer,
    register_judge,
    list_registered_judges,
)

config = JudgeConfig(model="anthropic:/claude-opus-4-1-20250805", temperature=0.0)

classification = create_classification_judge(
    task_description="Sentiment classification with labels: positive, neutral, negative.",
    config=config,
)
generation = create_generation_judge(metrics=["fluency", "relevance", "faithfulness"], config=config)
ranking = create_ranking_judge(config=config)
session = create_session_scorer(config=config)

registered = register_judge(classification, experiment_id="123")
all_registered = list_registered_judges(experiment_id="123")
```

## DeepEval Integration Notes

`deepeval_integration.py` is exploratory by design. It checks for `mlflow.genai.get_judge` and
raises `NotImplementedError` when unavailable in the installed MLflow version.

## Session-Level Scoring Notes

No separate session-scorer constructor was found in this MLflow runtime.
The provided session scorer uses `{{ trace }}` in `make_judge` instructions to score full traces.
