from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.evaluation.judges.base import (
    JudgeConfig,
    create_judge,
    list_registered_judges,
    register_judge,
)


def test_judge_config_defaults() -> None:
    config = JudgeConfig()
    assert config.model == "anthropic:/claude-opus-4-1-20250805"
    assert config.temperature == 0.0
    assert config.name_prefix == "hokusai"


def test_judge_config_rejects_invalid_temperature() -> None:
    with pytest.raises(ValueError, match="temperature"):
        JudgeConfig(temperature=1.2)


def test_create_judge_calls_make_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str] = {}

    def fake_make_judge(*, name: str, instructions: str, model: str):
        calls["name"] = name
        calls["instructions"] = instructions
        calls["model"] = model
        return SimpleNamespace(name=name, instructions=instructions, model=model)

    monkeypatch.setattr("src.evaluation.judges.base._import_make_judge", lambda: fake_make_judge)

    config = JudgeConfig(model="openai:/gpt-4", name_prefix="test")
    judge = create_judge("classification", "Evaluate {{ outputs }}", config=config)

    assert calls["name"] == "test_classification"
    assert calls["instructions"] == "Evaluate {{ outputs }}"
    assert calls["model"] == "openai:/gpt-4"
    assert judge.name == "test_classification"


def test_register_judge_uses_instance_register() -> None:
    class DummyJudge:
        def __init__(self) -> None:
            self.called = False

        def register(self, *, name: str | None = None, experiment_id: str | None = None):
            self.called = True
            return {"name": name, "experiment_id": experiment_id}

    judge = DummyJudge()
    out = register_judge(judge, name="judge_a", experiment_id="123")
    assert judge.called is True
    assert out == {"name": "judge_a", "experiment_id": "123"}


def test_register_judge_warns_when_register_missing() -> None:
    with pytest.warns(RuntimeWarning, match="does not support register"):
        assert register_judge(object()) is not None


def test_list_registered_judges_uses_mlflow_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.evaluation.judges.base._import_list_scorers",
        lambda: (lambda *, experiment_id=None: [SimpleNamespace(name="j1", exp=experiment_id)]),
    )

    judges = list_registered_judges(experiment_id="exp-1")
    assert len(judges) == 1
    assert judges[0].name == "j1"
    assert judges[0].exp == "exp-1"


def test_list_registered_judges_returns_empty_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise() -> None:
        raise ImportError("mlflow missing")

    monkeypatch.setattr("src.evaluation.judges.base._import_list_scorers", _raise)
    assert list_registered_judges() == []
