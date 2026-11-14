# ruff: noqa: F811 - the corpus fixture is imported, then named as an argument
"""HOK-3027: the frontier chat-model arm: its prompt, answers, sample and gate adapter."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import pytest

from src.arbiter import jev_questions as jq
from src.arbiter import llm_arm as la
from src.arbiter.gate import ArmContext
from src.arbiter.gate_arms import ARM_FACTORIES
from tests.unit.arbiter.test_jev_arm import REPO, corpus  # noqa: F401 - a fixture


def raw_answers(risky: bool, percent: float = 5.0) -> dict[str, Any]:
    """A model answer with every question at its riskiest or its safest."""
    out: dict[str, Any] = {}
    for name, question in jq.QUESTIONS.items():
        if question["type"] == "noul":
            out[name] = 100 if risky != (name in jq.PROTECTIVE) else 0
        elif question["type"] == "score":
            out[name] = len(question["criteria"]) - 1 if risky else 0
        else:
            out[name] = "reland" if risky else "docs_or_comments_only"
    out[la.RISK_FIELD] = percent
    return out


class FakeClient:
    """Answers every state the same way and counts the calls."""

    calls = 0

    def __init__(self, answer: dict[str, Any] | None = None, stop_reason: str = "end_turn") -> None:
        self.answer = raw_answers(risky=True) if answer is None else answer
        self.stop_reason = stop_reason

    def ask(self, state: dict[str, Any]) -> dict[str, Any]:
        assert set(state) == {"change"}
        FakeClient.calls += 1
        return {
            "model": la.MODEL,
            "stop_reason": self.stop_reason,
            "usage": {"input_tokens": 1000, "output_tokens": 500},
            "text": json.dumps(self.answer),
        }


def _row(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "repo": c["repo"],
        "pr_number": c["pr_number"],
        "merge_sha": c["merge_sha"],
        "as_of": pd.Timestamp(c["as_of"]),
    }


# --------------------------------------------------------------------------- prompt and answers


def test_the_prompt_asks_every_jev_question_and_the_schema_requires_them():
    prompt = la.system_prompt()
    schema = la.output_schema()
    for name, question in jq.QUESTIONS.items():
        assert f"`{name}`" in prompt and question["instructions"] in prompt
    assert schema["required"] == [*jq.QUESTIONS, la.RISK_FIELD]
    assert set(schema["properties"]["change_type"]["enum"]) == set(jq.CHANGE_TYPE_RISK)
    assert schema["additionalProperties"] is False


def test_answers_compose_with_arm_4_weights():
    assert la.scores(raw_answers(risky=True))["composite"] == pytest.approx(1.0)
    assert la.scores(raw_answers(risky=False))["composite"] == pytest.approx(0.0)


def test_the_stated_probability_ranks_and_the_composite_only_breaks_ties():
    low_risky = la.scores(raw_answers(risky=True, percent=3))
    high_safe = la.scores(raw_answers(risky=False, percent=3.1))
    same_safe = la.scores(raw_answers(risky=False, percent=3))
    assert low_risky["probability"] == pytest.approx(0.03)
    assert high_safe["score"] > low_risky["score"] > same_safe["score"]


def test_out_of_range_percentages_are_clamped_and_bad_answers_refused():
    assert la.scores(raw_answers(risky=True, percent=250))["probability"] == 1.0
    for field, value in (("change_type", "rewrite"), ("blast_radius", 9), (la.RISK_FIELD, "high")):
        bad = raw_answers(risky=True)
        bad[field] = value
        with pytest.raises(la.AnswerError):
            la.scores(bad)
    missing = raw_answers(risky=True)
    del missing["touches_concurrency"]
    with pytest.raises(la.AnswerError):
        la.scores(missing)


def test_cost_counts_every_token_class():
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
        "cache_creation_input_tokens": 1_000_000,
    }
    assert la.cost_usd(usage) == pytest.approx(4.0 + 20.0 + 0.20 + 5.0)


def test_the_frozen_arm_has_not_changed():
    # Any change to the prompt, schema, model, effort, state rules or sample needs a new version.
    assert la.ARM_VERSION == "llm-snap/0.1.0"
    assert la.frozen_sha256() == "88b8514d22debf57f25992a425b35757ac3244eebe0a52566e20bd9e25dd062b"


# --------------------------------------------------------------------------- scoring rows


def test_score_row_records_answers_and_no_text(corpus):
    record = la.score_row(FakeClient(), _row(corpus), corpus["base_sha"], corpus["corpus_root"])
    assert record["answers"][la.RISK_FIELD] == 5.0
    assert record["arm_version"] == la.ARM_VERSION and la.is_current(record)
    assert "Bump y" not in json.dumps(record)


def test_a_refusal_or_a_cut_off_answer_leaves_the_row_unscored(corpus):
    for client in (FakeClient(stop_reason="refusal"), FakeClient(answer={"change_type": "x"})):
        record = la.score_row(client, _row(corpus), corpus["base_sha"], corpus["corpus_root"])
        assert "answers" not in record and record["error"]
        assert record["usage"]["input_tokens"] == 1000


def test_run_caches_answers_and_a_second_run_asks_nothing(corpus, tmp_path):
    rows = pd.DataFrame([_row(corpus)])
    cache = tmp_path / "private" / "scores.jsonl"
    kwargs = {"corpus_root": corpus["corpus_root"], "cache": cache, "max_usd": 1.0}
    first = la.run(rows, client_factory=FakeClient, **kwargs)
    assert first["scored"] == 1
    assert first["usd"] == pytest.approx((1000 * 4 + 500 * 20) / 1e6)
    before = FakeClient.calls
    again = la.run(rows, client_factory=FakeClient, **kwargs)
    assert again["already_done"] == 1 and FakeClient.calls == before
    scored = la.load_scores(cache)
    assert scored["probability"].tolist() == [0.05]
    assert scored["composite"].tolist() == pytest.approx([1.0])


# --------------------------------------------------------------------------- the gate


def _eval_rows(per_repo: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "repo": [r for r in ("a/a", "b/b") for _ in range(per_repo)],
            "pr_number": list(range(per_repo)) * 2,
            la.BOT_COLUMN: [i % 5 == 0 for i in range(per_repo * 2)],
        }
    )


def test_the_sample_is_fixed_equal_per_repo_and_skips_bots():
    rows = _eval_rows(50)
    sample = la.sample_rows(rows, per_repo=10)
    assert sample.groupby("repo").size().tolist() == [10, 10]
    assert not sample[la.BOT_COLUMN].any()
    shuffled = rows.sample(frac=1.0, random_state=3)
    again = la.sample_rows(shuffled, per_repo=10)
    assert set(sample.index) == set(again.index)
    assert set(la.sample_rows(rows, per_repo=10, seed=1).index) != set(sample.index)


def test_the_gate_adapter_scores_its_sample_and_leaves_the_rest_empty(
    corpus,
    tmp_path,
    monkeypatch,
):
    rows = pd.DataFrame([_row(corpus), {**_row(corpus), "pr_number": 8}])
    rows[la.BOT_COLUMN] = [False, True]  # the bot PR is outside the sample
    context = ArmContext(feature_columns=(), categories={}, content_root=corpus["corpus_root"])
    arm = la.FrontierLlmArm(client_factory=FakeClient)
    monkeypatch.setenv(la.CACHE_VARIABLE, str(tmp_path / "gate.jsonl"))
    monkeypatch.delenv(la.MAX_USD_VARIABLE, raising=False)
    with pytest.raises(ValueError, match=la.MAX_USD_VARIABLE):
        arm.score(None, rows, context)
    monkeypatch.setenv(la.MAX_USD_VARIABLE, "1")
    scored = arm.score(arm.fit(rows, context), rows, context)
    assert list(scored) == list(arm.variants()) == ["frontier_llm", "frontier_llm.questions"]
    stated = scored["frontier_llm"]
    assert stated["probability"].iloc[0] == pytest.approx(0.05)
    assert stated["score"].iloc[0] == pytest.approx(0.05 + la.TIE_BREAK)
    assert np.isnan(stated["score"].iloc[1])
    assert scored["frontier_llm.questions"]["score"].iloc[0] == pytest.approx(1.0)


def test_a_sample_cut_short_by_the_spend_cap_is_not_returned(
    corpus,
    tmp_path,
    monkeypatch,
):
    rows = pd.DataFrame([_row(corpus)])
    context = ArmContext(feature_columns=(), categories={}, content_root=corpus["corpus_root"])
    monkeypatch.setenv(la.CACHE_VARIABLE, str(tmp_path / "gate.jsonl"))
    monkeypatch.setenv(la.MAX_USD_VARIABLE, "0")
    with pytest.raises(RuntimeError, match="stopped early"):
        la.FrontierLlmArm(client_factory=FakeClient).score(None, rows, context)


def test_the_arm_is_registered_for_the_gate():
    assert ARM_FACTORIES[la.ARM_ID] is la.FrontierLlmArm
    assert REPO == "acme/widgets"
