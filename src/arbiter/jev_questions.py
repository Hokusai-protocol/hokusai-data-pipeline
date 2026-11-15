"""The Jev question set and its composition for Rework Risk arm 4 (HOK-3026).

Arm 4 is a steelman of a snap judgment with no outcome history: atomic questions
answered by Jev against the merge-time state, combined here with weights set by
hand. Nothing in this module is fitted to labels. The only learned step allowed
for arm 4 is score-to-probability calibration, fitted on training folds by the
shared evaluator (pre-registration §3).

The target is the ``corrective_rework`` event: the change is reverted or
explicitly repaired within 30 days of merging.

Three things are defined here and frozen together under ``QUESTION_SET_VERSION``:

* ``QUESTIONS``: the request payload, one entry per question
* ``composite``: the hand-weighted risk score from the answers, and
  ``steelman_composite``, which adds merge-time facts that code computes exactly
* ``hybrid_features``: every answer as named, typed columns for arm 6 (HOK-3029)

Any change to a question, a weight or a transform needs a new version;
``frozen_sha256`` is pinned in the tests so that a change cannot go unnoticed.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

# Frozen 2026-11-14 after owner review (HOK-3026). Answers cached under the draft
# name were produced by exactly this content, so they count as this version.
QUESTION_SET_VERSION = "jev-qs/0.1.0"
QUESTION_SET_ALIASES = frozenset({"jev-qs/0.1.0-draft"})
# A versioned id, not an alias: ``jev-latest`` moves when a release ships, and one
# arm must be scored by one model. The response's ``model`` is recorded per row.
MODEL = "jev-1.14.0"

_EVENT = "reverted or needs an explicit follow-up repair soon after merging"


def _noul(question: str, true: str, false: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": question, "criteria": {"true": true, "false": false}}


def _score(question: str, levels: list[str]) -> dict[str, Any]:
    return {"type": "score", "instructions": question, "criteria": levels}


# Each question tests one property a reviewer could judge in seconds from
# `change.title`, `change.description`, `change.files` and `change.diff`.
# Nouls are phrased so that a high value means the riskier answer, except
# ``description_explains_change``, which is protective and inverted in code.
QUESTIONS: dict[str, dict[str, Any]] = {
    "change_type": {
        "type": "choice",
        "instructions": "What kind of change is this, judged by what `change.diff` does?",
        "criteria": {
            "bug_fix": "Corrects wrong behavior in existing code.",
            "new_feature": "Adds behavior or capability that did not exist.",
            "refactor": "Restructures or renames code without intending to change behavior.",
            "performance": "Changes how fast or how much memory, without changing results.",
            "revert": "Undoes an earlier change.",
            "reland": "Re-applies a change that was reverted earlier, with or without fixes.",
            "dependency_or_build": "Changes dependency versions, build scripts, CI or toolchain.",
            "configuration": "Changes settings, defaults, flags or deployment configuration only.",
            "tests_only": "Adds or changes tests and nothing that ships.",
            "docs_or_comments_only": "Changes documentation, comments or text only.",
        },
    },
    "blast_radius": _score(
        "How much of the software depends on the code that `change.diff` modifies?",
        [
            "Nothing that ships depends on it: documentation, comments, tests or developer tooling",
            "One leaf feature or module that few other parts call",
            "A component that several other modules call",
            "Shared core code that most runs, builds or requests pass through",
        ],
    ),
    "logic_complexity": _score(
        "How intricate is the logic that `change.diff` adds or modifies?",
        [
            "No logic changes: text, renames, moves or formatting",
            "Simple local logic: a constant, one condition, or a straightforward addition",
            "Several branches or functions that have to agree with each other",
            "Intricate logic: a non-trivial algorithm, state machine, invariant or interplay "
            "between components",
        ],
    ),
    "test_adequacy": _score(
        "How well do the test changes in `change.diff` exercise the behavior it changes?",
        [
            "No runtime behavior changes, so there is nothing new to test",
            "Tests are added or updated for the changed behavior, including edge cases",
            "Tests are added or updated for the main path of the changed behavior only",
            "Test files change, but not in a way that exercises the changed behavior",
            "Runtime behavior changes and no test is added or updated",
        ],
    ),
    "pattern_consistency": _score(
        "How does the new code in `change.diff` relate to the conventions of the code around it?",
        [
            "It follows the surrounding conventions and reuses the existing helpers",
            "It mostly follows them, with small stylistic deviations",
            "It introduces a second way of doing something the surrounding code already does",
            "It bypasses or special-cases around an existing mechanism",
        ],
    ),
    "touches_auth_or_security": _noul(
        "Does `change.diff` modify authentication, authorization, permission checks, "
        "secret handling or cryptography?",
        "Code that decides who may do what, or handles credentials, tokens or keys, changes",
        "No such code changes; mentioning security in a comment or a test name does not count",
    ),
    "touches_persistence_or_format": _noul(
        "Does `change.diff` modify a database schema, a migration, or a serialized, "
        "on-disk or wire format?",
        "Stored or exchanged data changes shape, or code that reads or writes that shape changes",
        "No stored or exchanged data shape changes; ordinary in-memory data structures "
        "do not count",
    ),
    "touches_concurrency": _noul(
        "Does `change.diff` modify code whose correctness depends on locking, threads, "
        "async ordering or shared mutable state?",
        "Locks, atomics, threads, async tasks, signal handlers or shared caches are added, "
        "removed or reordered",
        "The changed code runs in one thread of control with no shared state",
    ),
    "environment_sensitive": _noul(
        "Does the behavior that `change.diff` changes depend on the platform, compiler, "
        "architecture, operating system or runtime version?",
        "The changed code has platform-, version- or configuration-specific branches, or uses "
        "features that differ between environments",
        "The changed code behaves the same in every supported environment",
    ),
    "changes_public_interface": _noul(
        "Does `change.diff` change a signature, default value, flag or observable behavior "
        "that callers outside the changed files rely on?",
        "Existing callers or users can observe a difference without changing their own code",
        "Only internals change, or the interface is new and has no existing callers",
    ),
    "removes_safeguards": _noul(
        "Does `change.diff` remove or weaken validation, error handling, assertions, or tests?",
        "A check, guard, assertion or error path is deleted or loosened, or a test is deleted, "
        "skipped or disabled",
        "No safeguard is removed; replacing a check with an equivalent or stricter one "
        "does not count",
    ),
    "scope_exceeds_intent": _noul(
        "Does `change.diff` include changes that `change.title` and `change.description` "
        "do not account for?",
        "Some changed behavior is unrelated to the stated purpose",
        "Everything changed serves the stated purpose; an empty description with a clear "
        "title counts as stated",
    ),
    "workaround_or_incomplete": _noul(
        "Does the change describe itself as a temporary workaround, a partial fix, or "
        "work that needs a follow-up?",
        "The title, description, or added comments say hack, workaround, temporary, TODO, "
        "FIXME, or that more work is needed",
        "Nothing in the change says it is temporary or incomplete",
    ),
    "description_explains_change": _noul(
        "Does `change.description` say both what the change does and why it is needed?",
        "It states the behavior that changes and the reason",
        "It is empty, a template, or restates the title without a reason",
    ),
}

# --------------------------------------------------------------------------- composition

# Hand-set before any answer was seen. Each term is a risk in [0, 1]; the weights
# sum to 1, so the composite is in [0, 1].
WEIGHTS: Mapping[str, float] = {
    "blast_radius": 0.13,
    "logic_complexity": 0.11,
    "test_adequacy": 0.11,
    "change_type": 0.10,
    "environment_sensitive": 0.09,
    "changes_public_interface": 0.07,
    "touches_concurrency": 0.06,
    "removes_safeguards": 0.07,
    "touches_persistence_or_format": 0.05,
    "scope_exceeds_intent": 0.05,
    "workaround_or_incomplete": 0.05,
    "touches_auth_or_security": 0.04,
    "pattern_consistency": 0.04,
    "description_explains_change": 0.03,
}
PROTECTIVE = frozenset({"description_explains_change"})

# Risk of each change type, in [0, 1]: the composite takes the expectation over
# the Choice's probabilities. A reland has already failed once; text-only
# changes are rarely reverted.
CHANGE_TYPE_RISK: Mapping[str, float] = {
    "reland": 1.0,
    "new_feature": 0.7,
    "performance": 0.7,
    "dependency_or_build": 0.6,
    "refactor": 0.5,
    "bug_fix": 0.5,
    "configuration": 0.4,
    "revert": 0.3,
    "tests_only": 0.1,
    "docs_or_comments_only": 0.0,
}

# ``test_adequacy`` level 0 ("nothing to test") is not the safe end of a risk
# scale that runs 1..4, so the term reads the level probabilities directly.
TEST_ADEQUACY_RISK = (0.0, 0.1, 0.4, 0.8, 1.0)


def _levels(answer: Mapping[str, Any]) -> list[float]:
    probabilities = answer["probabilities"]
    return [float(probabilities[str(i)]) for i in range(len(probabilities))]


def risk_terms(answers: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    """Each question's answer as a risk in [0, 1]. Raises if an answer is missing."""
    terms: dict[str, float] = {}
    for name, question in QUESTIONS.items():
        answer = answers[name]
        if answer["type"] != question["type"]:
            raise ValueError(f"{name}: expected a {question['type']} answer, got {answer['type']}")
        if question["type"] == "noul":
            p = float(answer["noul"])
            terms[name] = 1.0 - p if name in PROTECTIVE else p
        elif name == "test_adequacy":
            terms[name] = sum(
                p * r for p, r in zip(_levels(answer), TEST_ADEQUACY_RISK, strict=True)
            )
        elif question["type"] == "score":
            terms[name] = float(answer["score"]) / (len(question["criteria"]) - 1)
        else:
            terms[name] = sum(
                float(p) * CHANGE_TYPE_RISK[option] for option, p in answer["probabilities"].items()
            )
    return terms


def composite(answers: Mapping[str, Mapping[str, Any]]) -> float:
    """Return the questions-only risk score in [0, 1]."""
    terms = risk_terms(answers)
    return sum(WEIGHTS[name] * terms[name] for name in WEIGHTS)


# Merge-time facts that code computes exactly are not asked of the model (Jev's
# own guidance); they enter as a second hand-weighted term. Directions match the
# arm-1 trivial features. Each cap is a round number near the 99th percentile of
# the development rows' feature values; no label was read to set them.
CODE_TERMS: Mapping[str, tuple[float, float, int]] = {
    # column: (weight, cap, direction)
    "feature.shape.loc_touched": (0.35, 5000.0, 1),
    "feature.shape.files_touched": (0.15, 80.0, 1),
    "feature.history.file_commits_90d": (0.25, 500.0, 1),
    "feature.author.repo_commits_prior": (0.25, 1000.0, -1),
}
CODE_WEIGHT = 0.4
# A missing fact contributes the middle of its range.
MISSING = 0.5


def code_risk(features: Mapping[str, Any]) -> float:
    """Hand-weighted risk in [0, 1] from the four trivial merge-time features."""
    total = 0.0
    for column, (weight, cap, direction) in CODE_TERMS.items():
        value = features.get(column)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            x = MISSING
        else:
            x = min(math.log1p(max(float(value), 0.0)) / math.log1p(cap), 1.0)
            x = x if direction > 0 else 1.0 - x
        total += weight * x
    return total


def steelman_composite(
    answers: Mapping[str, Mapping[str, Any]], features: Mapping[str, Any]
) -> float:
    """Questions plus exact merge-time facts: the arm-4 gate score proposed in HOK-3026."""
    return (1.0 - CODE_WEIGHT) * composite(answers) + CODE_WEIGHT * code_risk(features)


# Three terms ranked below chance on development rows. They stay in the gate
# score, whose weights were set before any label was seen (owner decision,
# 2026-11-14). This variant without them is reported beside it and never gates.
SENSITIVITY_DROPPED = frozenset(
    {"test_adequacy", "touches_auth_or_security", "description_explains_change"}
)


def sensitivity_composite(
    answers: Mapping[str, Mapping[str, Any]], features: Mapping[str, Any]
) -> float:
    """Return the steelman score with ``SENSITIVITY_DROPPED`` removed and the rest renormalized."""
    terms = risk_terms(answers)
    kept = {name: w for name, w in WEIGHTS.items() if name not in SENSITIVITY_DROPPED}
    questions = sum(w * terms[name] for name, w in kept.items()) / sum(kept.values())
    return (1.0 - CODE_WEIGHT) * questions + CODE_WEIGHT * code_risk(features)


def frozen_sha256() -> str:
    """Hash everything that decides an arm-4 score: questions, weights, transforms and model."""
    content = {
        "model": MODEL,
        "questions": QUESTIONS,
        "weights": dict(WEIGHTS),
        "protective": sorted(PROTECTIVE),
        "change_type_risk": dict(CHANGE_TYPE_RISK),
        "test_adequacy_risk": list(TEST_ADEQUACY_RISK),
        "code_terms": {k: list(v) for k, v in CODE_TERMS.items()},
        "code_weight": CODE_WEIGHT,
        "missing": MISSING,
        "sensitivity_dropped": sorted(SENSITIVITY_DROPPED),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------- hybrid features


def hybrid_feature_spec() -> dict[str, str]:
    """Name and type of every column ``hybrid_features`` returns (the arm-6 inputs)."""
    spec: dict[str, str] = {}
    for name, question in QUESTIONS.items():
        if question["type"] == "noul":
            spec[f"jev.{name}.p"] = "probability"
        elif question["type"] == "score":
            spec[f"jev.{name}.score_norm"] = "unit_interval"
            spec[f"jev.{name}.confidence"] = "unit_interval"
            for level in range(len(question["criteria"])):
                spec[f"jev.{name}.p_level_{level}"] = "probability"
        else:
            spec[f"jev.{name}.confidence"] = "unit_interval"
            for option in question["criteria"]:
                spec[f"jev.{name}.p.{option}"] = "probability"
    return spec


def hybrid_features(answers: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    """Every answer as flat numeric columns. No weights, no composite: arm 6 learns its own."""
    out: dict[str, float] = {}
    for name, question in QUESTIONS.items():
        answer = answers[name]
        if question["type"] == "noul":
            out[f"jev.{name}.p"] = float(answer["noul"])
        elif question["type"] == "score":
            out[f"jev.{name}.score_norm"] = float(answer["score"]) / (len(question["criteria"]) - 1)
            out[f"jev.{name}.confidence"] = float(answer["confidence"])
            for level, p in enumerate(_levels(answer)):
                out[f"jev.{name}.p_level_{level}"] = p
        else:
            out[f"jev.{name}.confidence"] = float(answer["confidence"])
            for option in question["criteria"]:
                out[f"jev.{name}.p.{option}"] = float(answer["probabilities"][option])
    return out


def _check() -> None:
    if set(WEIGHTS) != set(QUESTIONS):
        raise AssertionError("every question needs exactly one weight")
    if abs(sum(WEIGHTS.values()) - 1.0) > 1e-9:
        raise AssertionError("question weights must sum to 1")
    if set(CHANGE_TYPE_RISK) != set(QUESTIONS["change_type"]["criteria"]):
        raise AssertionError("every change type needs a risk")
    if len(TEST_ADEQUACY_RISK) != len(QUESTIONS["test_adequacy"]["criteria"]):
        raise AssertionError("every test_adequacy level needs a risk")
    if abs(sum(w for w, _, _ in CODE_TERMS.values()) - 1.0) > 1e-9:
        raise AssertionError("code-term weights must sum to 1")


_check()
