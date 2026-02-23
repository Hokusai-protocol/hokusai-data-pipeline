from __future__ import annotations

from types import SimpleNamespace

from src.evaluation.judges.generation import create_generation_judge


def test_create_generation_judge_includes_metrics(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_create_judge(*, base_name: str, instructions: str, config=None):
        captured["base_name"] = base_name
        captured["instructions"] = instructions
        return SimpleNamespace(name=base_name, instructions=instructions)

    monkeypatch.setattr("src.evaluation.judges.generation.create_judge", fake_create_judge)

    judge = create_generation_judge(metrics=["fluency", "relevance", "faithfulness"])

    assert captured["base_name"] == "generation_quality"
    assert "fluency, relevance, faithfulness" in captured["instructions"]
    assert "{{ outputs }}" in captured["instructions"]
    assert "{{ expectations }}" in captured["instructions"]
    assert judge.name == "generation_quality"


def test_create_generation_judge_defaults_dimensions(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_create_judge(*, base_name: str, instructions: str, config=None):
        captured["instructions"] = instructions
        return SimpleNamespace(name=base_name)

    monkeypatch.setattr("src.evaluation.judges.generation.create_judge", fake_create_judge)

    create_generation_judge(metrics=[])

    assert "fluency" in captured["instructions"]
    assert "coherence" in captured["instructions"]
