from __future__ import annotations

from types import SimpleNamespace

from src.evaluation.judges.base import JudgeConfig
from src.evaluation.judges.classification import create_classification_judge


def test_create_classification_judge_uses_task_description(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_create_judge(*, base_name: str, instructions: str, config: JudgeConfig | None):
        captured["base_name"] = base_name
        captured["instructions"] = instructions
        return SimpleNamespace(name=base_name, instructions=instructions, config=config)

    monkeypatch.setattr("src.evaluation.judges.classification.create_judge", fake_create_judge)

    judge = create_classification_judge("sentiment labels: positive, neutral, negative")

    assert captured["base_name"] == "classification_correctness"
    assert "sentiment labels" in captured["instructions"]
    assert "{{ outputs }}" in captured["instructions"]
    assert "{{ expectations }}" in captured["instructions"]
    assert judge.name == "classification_correctness"
