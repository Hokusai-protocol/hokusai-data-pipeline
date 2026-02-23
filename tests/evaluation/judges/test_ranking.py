from __future__ import annotations

from types import SimpleNamespace

from src.evaluation.judges.ranking import create_ranking_judge


def test_create_ranking_judge_builds_expected_template(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_create_judge(*, base_name: str, instructions: str, config=None):
        captured["base_name"] = base_name
        captured["instructions"] = instructions
        return SimpleNamespace(name=base_name, instructions=instructions)

    monkeypatch.setattr("src.evaluation.judges.ranking.create_judge", fake_create_judge)

    judge = create_ranking_judge()

    assert captured["base_name"] == "ranking_quality"
    assert "NDCG-style" in captured["instructions"]
    assert "{{ outputs }}" in captured["instructions"]
    assert "{{ expectations }}" in captured["instructions"]
    assert judge.name == "ranking_quality"
