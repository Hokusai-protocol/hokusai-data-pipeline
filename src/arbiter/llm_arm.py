# ruff: noqa: ANN101 - self needs no annotation
"""Rework Risk arm 3: a frontier chat model's snap judgment on a sample (HOK-3027).

The model sees exactly what arm 4 (Jev) sees: the ``jev-state/0.1.0`` merge-time
state. It answers the same 14 questions, then gives its own probability that the
change is reverted or explicitly repaired within 30 days. That probability is
the arm's score. Nothing here is fitted to labels.

Two variants are scored:

* ``frontier_llm``: the model's stated probability. Ties are broken by the
  question composite below, so that a model which answers in round numbers
  still ranks.
* ``frontier_llm.questions``: the model's 14 answers composed with arm 4's
  frozen hand-set weights. It is the like-for-like comparison with Jev's
  questions-only composite.

Requests hold raw PR text, so nothing here logs or stores them. The cache holds
the model's answers and names repos: keep it outside git.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.arbiter import jev_arm
from src.arbiter import jev_questions as jq
from src.arbiter import jev_state as js

ARM_ID = "hok-3027-frontier-llm"
ARM_VERSION = "llm-snap/0.1.0"
# A pinned snapshot: one arm is scored by one model. The response's model is recorded per row.
MODEL = "claude-opus-5-5"
# The model's default effort, set explicitly so that a changed default cannot change the arm.
EFFORT = "medium"
MAX_TOKENS = 16_000
# "Reliable knowledge cutoff: Jun 2026" (platform.claude.com/docs/en/about-claude/models/overview,
# read 2026-11-14). A PR merged after this date cannot have been seen in training.
KNOWLEDGE_CUTOFF = "2026-06-30"
# USD per million tokens (same page). Cache writes cost 1.25 times the input price.
USD_PER_MTOK = {
    "input_tokens": 4.0,
    "cache_creation_input_tokens": 5.0,
    "cache_read_input_tokens": 0.20,
    "output_tokens": 20.0,
}

KEY_VARIABLE = "ANTHROPIC_API_KEY"
CACHE_VARIABLE = "HOK3027_CACHE"
MAX_USD_VARIABLE = "HOK3027_MAX_USD"
DEFAULT_GATE_CACHE = "~/.hokusai-private/hok-3027/gate-scores.jsonl"

# The gate sample: this many rows per evaluation repo, the same for every repo
# because the gate metric gives each repo equal weight. See ``sample_rows``.
SAMPLE_PER_REPO = 500
SAMPLE_SEED = 20261114
BOT_COLUMN = "feature.author.is_bot"

RISK_FIELD = "rework_risk_percent"
# The composite is at most 1, so this term is at most 0.0001: it orders rows whose
# stated probabilities are equal, or closer than a hundredth of a percentage point.
TIE_BREAK = 1e-4

SYSTEM_INTRO = """\
You are assessing one merged pull request for a study of software changes.

The user message is a JSON object, `change`, holding what was known at the moment \
the change merged: `title`, `description`, `files` and `diff`. Project names, \
links, issue numbers and people's names were removed. Large diffs are shown in \
part, and `change` says so when that happens.

The event to predict: within 30 days of merging, the change is reverted, or a \
later change explicitly repairs something this change broke.

Judge only what is shown. Do not try to identify the project or to recall what \
happened to this change afterwards.

First answer each question below. Then give `rework_risk_percent`: your \
probability, from 0 to 100, that the event happens for this change. Most merged \
changes are never reverted or repaired, so most answers should be low; use fine \
steps (for example 0.5, 3, 12) so that changes can be ranked against each other.

Questions:
"""


def _render_question(name: str, question: Mapping[str, Any]) -> str:
    lines = [f"`{name}`: {question['instructions']}"]
    kind = question["type"]
    if kind == "choice":
        lines.append("  Answer with one of:")
        lines += [f"  - `{option}`: {text}" for option, text in question["criteria"].items()]
    elif kind == "score":
        lines.append("  Answer with the number of the level that fits best:")
        lines += [f"  - {level}: {text}" for level, text in enumerate(question["criteria"])]
    else:
        lines.append("  Answer with your probability, from 0 to 100, that this is true.")
        lines.append(f"  - True: {question['criteria']['true']}")
        lines.append(f"  - False: {question['criteria']['false']}")
    return "\n".join(lines)


def system_prompt() -> str:
    """Return the instructions: the same for every PR, so the provider can cache them."""
    return SYSTEM_INTRO + "\n\n".join(_render_question(n, q) for n, q in jq.QUESTIONS.items())


def output_schema() -> dict[str, Any]:
    """Return the JSON schema of one answer: the 14 questions, then the overall risk."""
    properties: dict[str, Any] = {}
    for name, question in jq.QUESTIONS.items():
        if question["type"] == "choice":
            properties[name] = {"type": "string", "enum": list(question["criteria"])}
        elif question["type"] == "score":
            properties[name] = {"type": "integer", "enum": list(range(len(question["criteria"])))}
        else:
            properties[name] = {"type": "number"}
    properties[RISK_FIELD] = {"type": "number"}
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def frozen_sha256() -> str:
    """Hash everything that decides arm 3's score. Pinned in the tests."""
    content = {
        "arm_version": ARM_VERSION,
        "model": MODEL,
        "effort": EFFORT,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt(),
        "schema": output_schema(),
        "state_version": js.STATE_VERSION,
        "questions_sha256": jq.frozen_sha256(),
        "tie_break": TIE_BREAK,
        "sample": [SAMPLE_PER_REPO, SAMPLE_SEED],
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------- answers


class AnswerError(ValueError):
    """The model's JSON does not answer the questions as asked."""


def _percent(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value != value:
        raise AnswerError(f"{name}: not a number")
    return min(max(float(value), 0.0), 100.0) / 100.0


def to_jev_answers(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Recast the model's answers in the shape of Jev's, so arm 4's composition applies.

    A chat model gives one option or level, not a distribution, so the chosen
    one gets probability 1.
    """
    answers: dict[str, dict[str, Any]] = {}
    for name, question in jq.QUESTIONS.items():
        if name not in raw:
            raise AnswerError(f"{name}: missing")
        value = raw[name]
        if question["type"] == "choice":
            if value not in question["criteria"]:
                raise AnswerError(f"{name}: unknown option")
            probabilities = {option: float(option == value) for option in question["criteria"]}
            answers[name] = {"type": "choice", "choice": value, "probabilities": probabilities}
        elif question["type"] == "score":
            levels = len(question["criteria"])
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < levels:
                raise AnswerError(f"{name}: not a level")
            probabilities = {str(i): float(i == value) for i in range(levels)}
            answers[name] = {"type": "score", "score": value, "probabilities": probabilities}
        else:
            answers[name] = {"type": "noul", "noul": _percent(value, name)}
    return answers


def scores(raw: Mapping[str, Any]) -> dict[str, float]:
    """Return ``probability`` (as stated), ``composite`` and the ranking ``score``."""
    probability = _percent(raw.get(RISK_FIELD), RISK_FIELD)
    composite = jq.composite(to_jev_answers(raw))
    return {
        "probability": probability,
        "composite": composite,
        "score": probability + TIE_BREAK * composite,
    }


# --------------------------------------------------------------------------- the model


class LlmError(Exception):
    """A request failed. ``transient`` says whether the same request may succeed later."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


class LlmClient:
    """Asks the model about one state. The key comes from ``ANTHROPIC_API_KEY``."""

    def __init__(self, *, max_retries: int = 6, timeout: float = 600.0) -> None:
        import anthropic  # imported here so the rest of the module needs no SDK

        self._sdk = anthropic
        self._client = anthropic.Anthropic(max_retries=max_retries, timeout=timeout)
        self._system = [
            {"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}
        ]
        self._format = {"format": {"type": "json_schema", "schema": output_schema()}}

    def ask(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Return ``model``, ``usage``, ``stop_reason`` and ``text`` for one state.

        No fallback model is configured: a refusal leaves the row unscored, so
        that every score in the arm comes from one model.
        """
        sdk = self._sdk
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=self._system,
                output_config={"effort": EFFORT, **self._format},
                messages=[{"role": "user", "content": json.dumps(state, ensure_ascii=False)}],
            )
        except (sdk.RateLimitError, sdk.APIConnectionError, sdk.InternalServerError) as error:
            raise LlmError(type(error).__name__, transient=True) from error
        except sdk.APIStatusError as error:
            transient = error.status_code in (408, 409) or error.status_code >= 500
            # The message can quote the request, which holds PR text: keep the status only.
            raise LlmError(
                f"HTTP {error.status_code} {type(error).__name__}", transient=transient
            ) from error
        usage = response.usage
        return {
            "model": response.model,
            "stop_reason": response.stop_reason,
            "usage": {name: int(getattr(usage, name, 0) or 0) for name in USD_PER_MTOK},
            "text": next((b.text for b in response.content if b.type == "text"), None),
        }


def cost_usd(usage: Mapping[str, Any]) -> float:
    """Return the listed price of one response's tokens."""
    return sum(int(usage.get(name, 0)) * price for name, price in USD_PER_MTOK.items()) / 1e6


# --------------------------------------------------------------------------- scoring rows


def row_key(repo: str, pr_number: int) -> jev_arm.Key:
    """Identify one answer: a row under one arm version and state version."""
    return (repo, int(pr_number), ARM_VERSION, js.STATE_VERSION)


def is_current(record: Mapping[str, Any]) -> bool:
    """Return whether a cached record was produced by this arm version and state version."""
    return (
        record.get("arm_version") == ARM_VERSION and record.get("state_version") == js.STATE_VERSION
    )


def score_row(
    client: LlmClient | None, row: Mapping[str, Any], base_sha: str, corpus_root: Path
) -> dict[str, Any]:
    """Build one row's state and, with a client, ask the model.

    Returns a record with ``answers``, or with ``error`` when the row cannot be
    scored however often it is tried. Failed requests raise ``LlmError``.
    """
    record: dict[str, Any] = {
        "repo": row["repo"],
        "pr_number": int(row["pr_number"]),
        "merge_sha": row["merge_sha"],
        "arm_version": ARM_VERSION,
        "state_version": js.STATE_VERSION,
    }
    try:
        built = js.state_for_row(
            corpus_root=corpus_root,
            repo=row["repo"],
            pr_number=int(row["pr_number"]),
            base_sha=base_sha,
            merge_sha=row["merge_sha"],
            as_of=row["as_of"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    except js.StateUnavailableError:
        record["error"] = "state_unavailable"
        return record
    record["state"] = built.meta
    if client is None:
        return record
    response = client.ask(built.state)
    record.update(model=response["model"], usage=response["usage"])
    if response["stop_reason"] != "end_turn" or response["text"] is None:
        record["error"] = f"stop_{response['stop_reason']}"
        return record
    try:
        raw = json.loads(response["text"])
        scores(raw)
    except (json.JSONDecodeError, AnswerError):
        record["error"] = "invalid_answer"
        return record
    record["answers"] = raw
    return record


def load_scores(cache: Path) -> pd.DataFrame:
    """Return one row per answered PR in ``cache``: scores, tokens and USD."""
    records = []
    if cache.exists():
        with open(cache) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not is_current(r) or "answers" not in r:
                    continue
                records.append(
                    {
                        "repo": r["repo"],
                        "pr_number": int(r["pr_number"]),
                        **scores(r["answers"]),
                        "truncated": bool(r["state"]["diff_truncated"]),
                        "usd": cost_usd(r["usage"]),
                        **{f"usage.{k}": int(v) for k, v in r["usage"].items()},
                    }
                )
    columns = ["repo", "pr_number", "probability", "composite", "score", "truncated", "usd"]
    frame = pd.DataFrame.from_records(records, columns=None if records else columns)
    return frame.drop_duplicates(["repo", "pr_number"])


def work_items(rows: pd.DataFrame, corpus_root: Path) -> list[tuple[dict[str, Any], str]]:
    """Pair each row with its ``base_sha``. Rows the frozen feature rows lack are dropped."""
    bases: dict[tuple[str, int], str] = {}
    for repo, group in rows.groupby("repo"):
        numbers = {int(n) for n in group["pr_number"]}
        for number, sha in js.base_shas(corpus_root, repo, numbers).items():
            bases[(repo, number)] = sha
    records = rows[["repo", "pr_number", "merge_sha", "as_of"]].to_dict("records")
    return [
        (r, bases[(r["repo"], int(r["pr_number"]))])
        for r in records
        if (r["repo"], int(r["pr_number"])) in bases
    ]


def run(
    rows: pd.DataFrame,
    *,
    corpus_root: Path,
    cache: Path,
    max_usd: float,
    workers: int = 8,
    client_factory: Callable[[], Any] = LlmClient,
    progress: Callable[[dict[str, Any]], None] | None = None,
    progress_every: int = 100,
) -> dict[str, Any]:
    """Score ``rows`` not yet in ``cache``. Stops at ``max_usd``; a rerun resumes."""
    local = threading.local()

    def score(row: Mapping[str, Any], base_sha: str) -> dict[str, Any]:
        if not hasattr(local, "client"):
            local.client = client_factory()
        return score_row(local.client, row, base_sha, corpus_root)

    return jev_arm.run(
        work_items(rows, corpus_root),
        cache=cache,
        score=score,
        workers=workers,
        max_usd=max_usd,
        progress=progress,
        progress_every=progress_every,
        key=row_key,
        current=is_current,
        cost=cost_usd,
    )


# --------------------------------------------------------------------------- the gate


def sample_rows(
    rows: pd.DataFrame, *, per_repo: int = SAMPLE_PER_REPO, seed: int = SAMPLE_SEED
) -> pd.DataFrame:
    """Return the fixed random sample arm 3 scores: ``per_repo`` rows from each repo.

    Rows are ordered by ``sha256(seed, repo, pr_number)`` and the first
    ``per_repo`` of each repo are taken, so the sample depends on nothing but
    the seed and the rows' identity. Dependency-bot PRs are left out: they are
    outside the primary analysis. No label is read.
    """
    if BOT_COLUMN in rows:
        rows = rows[rows[BOT_COLUMN] != True]  # noqa: E712 - None means unknown
    order = [
        hashlib.sha256(f"{seed}\x00{repo}\x00{int(number)}".encode()).hexdigest()
        for repo, number in zip(rows["repo"], rows["pr_number"], strict=True)
    ]
    ranked = rows.assign(_order=order).sort_values("_order")
    return ranked.groupby("repo", sort=False).head(per_repo).drop(columns="_order")


class FrontierLlmArm:
    """Gate adapter for arm 3. Scores a fixed sample; the other rows stay NaN.

    Needs ``ANTHROPIC_API_KEY`` and the runner's ``--content-root`` (the corpus
    root: clones, the private evidence capture and the frozen feature rows).
    ``HOK3027_MAX_USD`` must be set: there is no default spend. Answers go to
    ``HOK3027_CACHE``, so a run that stops is resumed by running the gate again.
    """

    arm_id = ARM_ID
    version = ARM_VERSION

    def __init__(self, client_factory: Callable[[], Any] = LlmClient) -> None:
        self._client_factory = client_factory

    def variants(self) -> Mapping[str, str]:
        """Return the stated probability first: the gate compares arm 5 with the first."""
        return {"frontier_llm": "arm3", "frontier_llm.questions": "arm3"}

    def fit(self, train: pd.DataFrame, context: Any) -> None:
        """Arm 3 has no outcome history: nothing is fitted."""
        return None

    def score(self, fitted: None, rows: pd.DataFrame, context: Any) -> Mapping[str, pd.DataFrame]:
        """Score the sample with the model and return both variants, NaN off the sample."""
        if context.content_root is None:
            raise ValueError(f"{ARM_ID} needs --content-root")
        if MAX_USD_VARIABLE not in os.environ:
            raise ValueError(f"Set {MAX_USD_VARIABLE}: the most this scoring may spend")
        cache = Path(os.environ.get(CACHE_VARIABLE, DEFAULT_GATE_CACHE)).expanduser()
        sample = sample_rows(rows)
        stats = run(
            sample,
            corpus_root=Path(context.content_root),
            cache=cache,
            max_usd=float(os.environ[MAX_USD_VARIABLE]),
            client_factory=self._client_factory,
        )
        if stats["stopped"] or stats["scored"] + stats["unscorable"] < stats["to_score"]:
            # A partly scored sample is not the fixed sample. The cache keeps what is done.
            raise RuntimeError(f"{ARM_ID} stopped early ({stats['stopped']}); run the gate again")
        scored = load_scores(cache).set_index(["repo", "pr_number"])
        keys = list(zip(sample["repo"], sample["pr_number"].astype(int), strict=True))
        found = scored.reindex(keys)
        out = {}
        for variant, column in (("frontier_llm", "score"), ("frontier_llm.questions", "composite")):
            frame = pd.DataFrame(
                {"score": np.nan, "probability": np.nan}, index=rows.index, dtype=float
            )
            frame.loc[sample.index, "score"] = found[column].to_numpy()
            if variant == "frontier_llm":
                frame.loc[sample.index, "probability"] = found["probability"].to_numpy()
            else:
                frame = frame[["score"]]
            out[variant] = frame
        return out
