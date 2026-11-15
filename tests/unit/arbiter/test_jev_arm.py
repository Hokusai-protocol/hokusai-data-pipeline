# ruff: noqa: S603, S607 - git is called with fixed arguments
"""HOK-3026: the Jev question set, its composition, the merge-time state and the client."""

from __future__ import annotations

import gzip
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.arbiter import jev_client as jc
from src.arbiter import jev_questions as jq
from src.arbiter import jev_state as js

REPO = "acme/widgets"


def answers(risky: bool) -> dict[str, dict[str, Any]]:
    """Answers with every question at its riskiest or its safest."""
    out: dict[str, dict[str, Any]] = {}
    for name, question in jq.QUESTIONS.items():
        if question["type"] == "noul":
            high = risky != (name in jq.PROTECTIVE)
            out[name] = {"type": "noul", "noul": 1.0 if high else 0.0}
        elif question["type"] == "score":
            top = len(question["criteria"]) - 1
            level = top if risky else 0
            out[name] = {
                "type": "score",
                "score": float(level),
                "confidence": 1.0,
                "probabilities": {str(i): float(i == level) for i in range(top + 1)},
            }
        else:
            pick = "reland" if risky else "docs_or_comments_only"
            out[name] = {
                "type": "choice",
                "choice": pick,
                "confidence": 1.0,
                "probabilities": {o: float(o == pick) for o in question["criteria"]},
            }
    return out


# --------------------------------------------------------------------------- questions


def test_request_payload_fits_the_api_limits():
    for name, question in jq.QUESTIONS.items():
        assert question["type"] in {"noul", "score", "choice"}, name
        if question["type"] == "score":
            assert 2 <= len(question["criteria"]) <= 10
        if question["type"] == "choice":
            assert 1 <= len(question["criteria"]) <= 255
        if question["type"] == "noul":
            assert set(question["criteria"]) == {"true", "false"}


def test_composite_spans_zero_to_one():
    assert jq.composite(answers(risky=False)) == pytest.approx(0.0)
    assert jq.composite(answers(risky=True)) == pytest.approx(1.0)


def test_a_good_description_lowers_the_composite():
    explained = answers(risky=True)
    explained["description_explains_change"]["noul"] = 1.0
    assert jq.composite(explained) == pytest.approx(1.0 - jq.WEIGHTS["description_explains_change"])


def test_nothing_to_test_is_the_safe_end_of_test_adequacy():
    safe = answers(risky=False)
    assert jq.risk_terms(safe)["test_adequacy"] == 0.0
    tested = answers(risky=False)
    tested["test_adequacy"]["probabilities"] = {"0": 0, "1": 1, "2": 0, "3": 0, "4": 0}
    assert jq.risk_terms(tested)["test_adequacy"] == pytest.approx(0.1)


def test_change_type_risk_is_an_expectation_over_probabilities():
    mixed = answers(risky=False)
    mixed["change_type"]["probabilities"] = {
        o: 0.0 for o in jq.QUESTIONS["change_type"]["criteria"]
    } | {"reland": 0.5, "docs_or_comments_only": 0.5}
    assert jq.risk_terms(mixed)["change_type"] == pytest.approx(0.5)


def test_an_answer_of_the_wrong_type_is_refused():
    wrong = answers(risky=False)
    wrong["blast_radius"] = {"type": "noul", "noul": 0.5}
    with pytest.raises(ValueError, match="blast_radius"):
        jq.composite(wrong)


def test_code_risk_follows_the_arm_1_directions():
    small = {
        "feature.shape.loc_touched": 0,
        "feature.shape.files_touched": 0,
        "feature.history.file_commits_90d": 0,
        "feature.author.repo_commits_prior": 10**6,
    }
    large = {
        "feature.shape.loc_touched": 10**6,
        "feature.shape.files_touched": 10**6,
        "feature.history.file_commits_90d": 10**6,
        "feature.author.repo_commits_prior": 0,
    }
    assert jq.code_risk(small) == pytest.approx(0.0)
    assert jq.code_risk(large) == pytest.approx(1.0)
    assert jq.code_risk({"feature.author.repo_commits_prior": float("nan")}) == pytest.approx(0.5)


def test_steelman_mixes_questions_and_code_terms():
    features = {column: None for column in jq.CODE_TERMS}
    assert jq.steelman_composite(answers(risky=True), features) == pytest.approx(
        (1 - jq.CODE_WEIGHT) * 1.0 + jq.CODE_WEIGHT * 0.5
    )


def test_hybrid_features_match_their_spec():
    features = jq.hybrid_features(answers(risky=True))
    assert set(features) == set(jq.hybrid_feature_spec())
    assert all(0.0 <= value <= 1.0 for value in features.values())
    assert features["jev.change_type.p.reland"] == 1.0
    assert features["jev.blast_radius.score_norm"] == 1.0


# --------------------------------------------------------------------------- evidence


def test_title_at_ignores_renames_after_merge():
    evidence = {
        "title": "final title",
        "renames": [
            {"at": "2026-01-02T00:00:00Z", "from": "first", "to": "second"},
            {"at": "2026-01-09T00:00:00Z", "from": "second", "to": "final title"},
        ],
    }
    assert js.title_at(evidence, "2026-01-05T00:00:00Z") == "second"
    assert js.title_at(evidence, "2026-01-01T00:00:00Z") == "first"
    assert js.title_at({"title": "only", "renames": []}, "2026-01-05T00:00:00Z") == "only"


def test_body_at_uses_the_version_at_merge_or_admits_it_is_gone():
    edits = [
        {"at": "2026-01-02T00:00:00Z", "body": "original"},
        {"at": "2026-01-09T00:00:00Z", "body": "edited after merge"},
    ]
    evidence = {"body": "edited after merge", "body_edits": edits}
    assert js.body_at(evidence, "2026-01-05T00:00:00Z") == "original"
    assert js.body_at(evidence, "2026-01-01T00:00:00Z") is None
    assert js.body_at({"body": None, "body_edits": []}, "2026-01-05T00:00:00Z") == ""


# --------------------------------------------------------------------------- redaction and diff


def test_redaction_removes_lookup_ids_from_prose():
    text = (
        "Fixes #1234 in acme/widgets, see https://github.com/acme/widgets/pull/99 "
        "cc @octocat (dev@example.com). Widgets crashes."
    )
    out = js.redact(text, REPO, prose=True)
    for gone in ("1234", "acme", "github", "octocat", "example.com", "Widgets"):
        assert gone not in out
    assert "#[ref]" in out and "[url]" in out and "@[user]" in out


def test_redaction_leaves_code_intact():
    code = "@property\ncolor = '#fff'\nwidgets = load()  # see #77"
    out = js.redact(code, REPO, prose=False)
    assert "@property" in out and "'#fff'" in out and "widgets = load()" in out
    assert "#77" not in out


def test_file_kinds():
    assert js.file_kind("src/app/main.py") == "source"
    assert js.file_kind("src/app/main_test.go") == "test"
    assert js.file_kind("tests/unit/test_x.py") == "test"
    assert js.file_kind("docs/guide.md") == "docs"
    assert js.file_kind("package-lock.json") == "generated"
    assert js.file_kind("vendor/lib/tests/a.c") == "generated"


def test_allocate_keeps_small_files_whole_and_shares_the_rest():
    assert js.allocate([10, 1000, 1000], 510) == [10, 250, 250]
    assert js.allocate([10, 20], 100) == [10, 20]
    assert sum(js.allocate([500, 500, 500], 100)) <= 100


def test_parse_raw_numstat_reads_status_and_binary():
    raw = (
        ":100644 100644 aaa bbb M\0src/a.py\0"
        ":000000 100644 000 ccc A\0img.png\0"
        "3\t1\tsrc/a.py\0-\t-\timg.png\0"
    )
    files = js.parse_raw_numstat(raw)
    assert [(f.path, f.status, f.lines, f.kind) for f in files] == [
        ("src/a.py", "modified", 4, "source"),
        ("img.png", "added", 0, "binary"),
    ]


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(cwd),
        },
    )
    return done.stdout.strip()


@pytest.fixture()
def corpus(tmp_path: Path) -> dict[str, Any]:
    """One repo in the corpus layout: a clone with one change, and its captured evidence."""
    repo_dir = tmp_path / "acme__widgets"
    work = tmp_path / "work"
    work.mkdir()
    repo_dir.mkdir()
    _git(work, "init", "-q")
    (work / "src").mkdir()
    (work / "src" / "big.py").write_text("x = 0\n")
    (work / "src" / "small.py").write_text("y = 0\n")
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "base")
    base = _git(work, "rev-parse", "HEAD")
    (work / "src" / "big.py").write_text("".join(f"x{i} = {i}  # see #{i}\n" for i in range(400)))
    (work / "src" / "small.py").write_text("y = 1  # acme/widgets\n")
    (work / "tests").mkdir()
    (work / "tests" / "test_small.py").write_text("def test_y():\n    assert True\n")
    (work / "package-lock.json").write_text('{"lock": true}\n')
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "change")
    merge = _git(work, "rev-parse", "HEAD")
    _git(tmp_path, "clone", "-q", "--bare", str(work), str(repo_dir / "repo.git"))

    def batch(kind: str, value: dict[str, Any]) -> None:
        path = repo_dir / "feature-evidence" / kind / "1-9.json.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt") as f:
            json.dump(
                {
                    "captured_at": "2026-11-01T00:00:00Z",
                    "items": [{"pr_number": 7, "value": value, "error": None}],
                },
                f,
            )

    batch(
        "evidence",
        {
            "pr_number": 7,
            "title": "Title edited after merge",
            "body": "<!-- template -->\nBumps y. Fixes #12.",
            "body_edits": [],
            "renames": [],
        },
    )
    batch(
        "timeline",
        {
            "pr_number": 7,
            "renames": [{"at": "2026-02-01T00:00:00Z", "from": "Bump y", "to": "Title edited"}],
            "label_events": [],
            "dismissals": [],
        },
    )
    with gzip.open(repo_dir / "features.jsonl.gz", "wt") as f:
        f.write(json.dumps({"pr_number": 7, "base_sha": base, "merge_sha": merge}) + "\n")
    return {
        "corpus_root": tmp_path,
        "repo": REPO,
        "pr_number": 7,
        "base_sha": base,
        "merge_sha": merge,
        "as_of": "2026-01-15T00:00:00Z",
    }


def test_state_for_row_is_merge_time_redacted_and_repeatable(corpus):
    built = js.state_for_row(**corpus)
    change = built.state["change"]
    assert change["title"] == "Bump y"  # the rename happened after as_of
    assert change["description"] == "Bumps y. Fixes #[ref]."
    encoded = json.dumps(built.state)
    assert "acme/widgets" not in encoded and "template" not in encoded
    shown = {f["path"]: f["diff"] for f in change["files"]}
    assert shown["package-lock.json"] == "not shown"
    assert shown["src/small.py"] == "in full"
    assert '"lock"' not in change["diff"]
    assert built.meta["diff_truncated"] is False
    assert js.state_for_row(**corpus).meta["state_sha256"] == built.meta["state_sha256"]
    assert js.base_shas(corpus["corpus_root"], REPO, {7}) == {7: corpus["base_sha"]}


def test_a_small_budget_cuts_the_large_file_and_says_so(corpus):
    built = js.state_for_row(**corpus, diff_budget=600)
    change = built.state["change"]
    shown = {f["path"]: f["diff"] for f in change["files"]}
    assert shown["src/big.py"] == "in part"
    assert shown["src/small.py"] == "in full"  # source is filled before tests
    assert change["diff_is_partial"] is True
    assert built.meta["diff_truncated"] is True
    assert "not shown" in change["diff"]


def test_missing_capture_leaves_title_and_description_unknown(corpus):
    (
        corpus["corpus_root"] / "acme__widgets" / "feature-evidence" / "timeline" / "1-9.json.gz"
    ).unlink()
    built = js.state_for_row(**corpus)
    assert built.state["change"]["title"] is None
    assert built.meta["title_known"] is False and built.meta["body_known"] is False


def test_an_unknown_commit_is_reported_not_guessed(corpus):
    corpus["merge_sha"] = "0" * 40
    with pytest.raises(js.StateUnavailableError):
        js.state_for_row(**corpus)


# --------------------------------------------------------------------------- client


class FakeResponse:
    def __init__(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self) -> Any:
        return self._body


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def test_client_retries_overload_then_returns_the_body():
    ok = {"model": "jev-1.14.0", "answers": {"q": {"type": "noul", "noul": 0.2}}, "usage": {}}
    session = FakeSession(
        [FakeResponse(529, "busy"), FakeResponse(429, "slow"), FakeResponse(200, ok)]
    )
    waits: list[float] = []
    client = jc.JevClient(api_key="k", session=session, sleep=waits.append)
    assert client.ask(model="jev-1.14.0", state={"a": 1}, questions={"q": {}}) == ok
    assert waits == [1.0, 2.0]
    assert session.calls[0]["headers"] == {"Authorization": "Bearer k"}


def test_client_reports_context_overflow_and_missing_answers():
    over = FakeResponse(400, '{"detail": "max_tokens_exceeded"}')
    client = jc.JevClient(api_key="k", session=FakeSession([over]))
    with pytest.raises(jc.ContextExceededError):
        client.ask(model="m", state="s", questions={"q": {}})
    partial = FakeResponse(200, {"model": "m", "answers": {}, "usage": {}})
    client = jc.JevClient(api_key="k", session=FakeSession([partial]))
    with pytest.raises(jc.JevError, match="lacks answers"):
        client.ask(model="m", state="s", questions={"q": {}})


def test_client_needs_a_key(monkeypatch):
    monkeypatch.delenv(jc.KEY_VARIABLE, raising=False)
    with pytest.raises(jc.JevError, match=jc.KEY_VARIABLE):
        jc.JevClient()


def test_cost_uses_the_listed_input_price():
    assert jc.cost_usd(1_000_000) == pytest.approx(0.042)


# --------------------------------------------------------------------------- resumable run


def _rows(n: int) -> list[tuple[dict[str, Any], str]]:
    return [({"repo": REPO, "merge_sha": f"sha{i}", "pr_number": i}, "base") for i in range(n)]


def _answered(row: dict[str, Any], _base: str) -> dict[str, Any]:
    return {
        "repo": row["repo"],
        "merge_sha": row["merge_sha"],
        "pr_number": row["pr_number"],
        "question_set_version": jq.QUESTION_SET_VERSION,
        "state_version": js.STATE_VERSION,
        "answers": {},
        "usage": {"input_tokens": 1_000_000},
    }


def test_run_appends_answers_and_a_second_run_skips_them(tmp_path):
    from src.arbiter import jev_arm

    cache = tmp_path / "private" / "scores.jsonl"
    first = jev_arm.run(_rows(5), cache=cache, score=_answered, workers=2)
    assert first["scored"] == 5 and first["stopped"] is None
    assert first["usd"] == pytest.approx(5 * 0.042)
    again = jev_arm.run(_rows(7), cache=cache, score=_answered, workers=2)
    assert again["already_done"] == 5 and again["scored"] == 2
    assert len(cache.read_text().splitlines()) == 7


def test_run_stops_at_the_spend_cap_and_keeps_what_it_has(tmp_path):
    from src.arbiter import jev_arm

    cache = tmp_path / "scores.jsonl"
    stats = jev_arm.run(_rows(50), cache=cache, score=_answered, workers=1, max_usd=0.1)
    assert "cap" in stats["stopped"]
    assert 3 <= stats["scored"] < 50
    assert len(cache.read_text().splitlines()) == stats["scored"]


def test_run_stops_on_a_refused_request_but_not_on_a_transient_one(tmp_path):
    from src.arbiter import jev_arm

    def refused(row: dict[str, Any], base: str) -> dict[str, Any]:
        if row["pr_number"] == 2:
            raise jc.JevError("HTTP 402: no balance", 402)
        return _answered(row, base)

    stats = jev_arm.run(_rows(40), cache=tmp_path / "a.jsonl", score=refused, workers=1)
    assert "402" in stats["stopped"] and stats["scored"] < 40

    def flaky(row: dict[str, Any], base: str) -> dict[str, Any]:
        if row["pr_number"] == 2:
            raise jc.JevError("HTTP 529: busy", 529)
        return _answered(row, base)

    stats = jev_arm.run(_rows(10), cache=tmp_path / "b.jsonl", score=flaky, workers=1)
    assert stats["stopped"] is None
    assert stats["scored"] == 9 and stats["transient_failures"] == 1


def test_a_cache_line_cut_short_is_scored_again(tmp_path):
    from src.arbiter import jev_arm

    cache = tmp_path / "scores.jsonl"
    jev_arm.run(_rows(2), cache=cache, score=_answered, workers=1)
    with open(cache, "a") as f:
        f.write('{"repo": "acme/widgets", "merge_sh')
    assert len(jev_arm.load_done(cache)) == 2


# --------------------------------------------------------------------------- freeze


def test_the_frozen_question_set_has_not_changed():
    # Frozen 2026-11-14 (HOK-3026). If this fails, a question, weight or transform
    # changed: give the set a new QUESTION_SET_VERSION and pin the new hash.
    assert jq.QUESTION_SET_VERSION == "jev-qs/0.1.0"
    assert jq.frozen_sha256() == (
        "9190f64ad0082d73dc84de4657943d27fceb5f4a7d5300137d43facebfa9adc4"
    )


def test_the_frozen_state_rules_have_not_changed():
    assert js.STATE_VERSION == "jev-state/0.1.0"
    assert (js.DIFF_BUDGET_CHARS, js.BODY_MAX_CHARS, js.TITLE_MAX_CHARS) == (40_000, 6_000, 300)
    assert (js.MAX_FILES_LISTED, js.MAX_PATCH_FILES, js.MAX_PATCH_LINES) == (100, 200, 20_000)


def test_answers_cached_under_the_draft_name_count_as_frozen(tmp_path):
    from src.arbiter import jev_arm

    draft = {"question_set_version": "jev-qs/0.1.0-draft", "state_version": "jev-state/0.1.0-draft"}
    assert jev_arm.is_current(draft)
    assert not jev_arm.is_current(draft | {"question_set_version": "jev-qs/0.2.0"})


def test_sensitivity_composite_ignores_the_dropped_terms():
    features = {column: None for column in jq.CODE_TERMS}
    risky = answers(risky=True)
    for name in jq.SENSITIVITY_DROPPED - jq.PROTECTIVE:
        if jq.QUESTIONS[name]["type"] == "noul":
            risky[name]["noul"] = 0.0
    assert jq.sensitivity_composite(risky, features) == pytest.approx(0.6 * 1.0 + 0.4 * 0.5)
