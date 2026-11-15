# ruff: noqa: ANN101, C901 - self needs no annotation; the run loop reads best as one sequence
"""Score PRs with the Jev question set, resumably (HOK-3026).

Every answer is appended to a private cache as it arrives, so a run that stops
for any reason (balance, rate limit, crash) loses nothing: running the same
command again skips the rows already answered. The cache names repos and holds
the model's answers; it holds no raw PR text. Composites are not stored: they
are computed from the answers under the frozen question-set version.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

from src.arbiter import jev_questions as jq
from src.arbiter import jev_state as js
from src.arbiter.jev_client import ContextExceededError, JevClient, cost_usd

# On a context error the diff budget is halved, at most this many times.
MAX_HALVINGS = 2
# This many transient failures in a row means the service is down, not the row.
MAX_CONSECUTIVE_FAILURES = 25

Key = tuple[str, int, str, str]


def row_key(repo: str, pr_number: int) -> Key:
    """Identify one answer: a row under one question-set and state version."""
    return (repo, int(pr_number), jq.QUESTION_SET_VERSION, js.STATE_VERSION)


def is_current(record: Mapping[str, Any]) -> bool:
    """Return whether a cached record was produced by the frozen question set and state rules."""
    questions = record.get("question_set_version")
    state = record.get("state_version")
    return (questions == jq.QUESTION_SET_VERSION or questions in jq.QUESTION_SET_ALIASES) and (
        state == js.STATE_VERSION or state in js.STATE_ALIASES
    )


def score_row(
    client: JevClient | None, row: Mapping[str, Any], base_sha: str, corpus_root: Path
) -> dict[str, Any]:
    """Build one row's state and, with a client, ask the question set.

    Returns a record with ``answers``, or with ``error`` when the row cannot be
    scored however often it is tried. Transient failures raise ``JevError``.
    """
    record: dict[str, Any] = {
        "repo": row["repo"],
        "pr_number": int(row["pr_number"]),
        "merge_sha": row["merge_sha"],
        "question_set_version": jq.QUESTION_SET_VERSION,
        "state_version": js.STATE_VERSION,
    }
    budget = js.DIFF_BUDGET_CHARS
    for halvings in range(MAX_HALVINGS + 1):
        try:
            built = js.state_for_row(
                corpus_root=corpus_root,
                repo=row["repo"],
                pr_number=int(row["pr_number"]),
                base_sha=base_sha,
                merge_sha=row["merge_sha"],
                as_of=row["as_of"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                diff_budget=budget,
            )
        except js.StateUnavailableError:
            record["error"] = "state_unavailable"
            return record
        record["state"] = built.meta | {"budget_halvings": halvings}
        if client is None:
            return record
        try:
            response = client.ask(model=jq.MODEL, state=built.state, questions=jq.QUESTIONS)
        except ContextExceededError:
            budget //= 2
            continue
        record.update(model=response["model"], usage=response["usage"], answers=response["answers"])
        return record
    record["error"] = "context_exceeded"
    return record


def _jev_cost(usage: Mapping[str, Any]) -> float:
    return cost_usd(int(usage["input_tokens"]))


def load_done(
    cache: Path,
    *,
    key: Callable[[str, int], Key] = row_key,
    current: Callable[[Mapping[str, Any]], bool] = is_current,
) -> set[Key]:
    """Return the rows the cache already settles: answered, or unscorable for good."""
    done: set[Key] = set()
    if not cache.exists():
        return done
    with open(cache) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # a line cut short by a crash; the row is scored again
            if "answers" in record or "error" in record:
                if current(record):
                    done.add(key(record["repo"], record["pr_number"]))
    return done


def run(
    rows: Iterable[tuple[Mapping[str, Any], str]],
    *,
    cache: Path,
    score: Callable[[Mapping[str, Any], str], dict[str, Any]],
    workers: int = 8,
    max_usd: float | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    progress_every: int = 500,
    key: Callable[[str, int], Key] = row_key,
    current: Callable[[Mapping[str, Any]], bool] = is_current,
    cost: Callable[[Mapping[str, Any]], float] = _jev_cost,
) -> dict[str, Any]:
    """Score ``(row, base_sha)`` pairs not yet in ``cache``, appending each result.

    Stops early, keeping what is done, when spend reaches ``max_usd``, when a
    request fails for a reason that retrying will not fix (key, balance,
    permissions), or after many transient failures in a row.

    ``score`` signals a failed request by raising an error with a boolean
    ``transient`` attribute, as ``JevError`` has. ``key``, ``current`` and
    ``cost`` (USD from a record's ``usage``) let another arm reuse this loop
    with its own versions and prices (HOK-3027).
    """
    cache.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    done = load_done(cache, key=key, current=current)
    pending = [(row, base) for row, base in rows if key(row["repo"], row["pr_number"]) not in done]
    stats = {
        "already_done": len(done),
        "to_score": len(pending),
        "scored": 0,
        "unscorable": 0,
        "transient_failures": 0,
        "input_tokens": 0,
        "usd": 0.0,
        "stopped": None,
    }
    consecutive = 0
    queue = iter(pending)

    with open(cache, "a") as out, ThreadPoolExecutor(max_workers=workers) as pool:
        cache.chmod(0o600)
        running: set[Future] = set()

        def submit() -> bool:
            if stats["stopped"]:
                return False
            if max_usd is not None and stats["usd"] >= max_usd:
                stats["stopped"] = f"spend reached the {max_usd:.2f} USD cap"
                return False
            item = next(queue, None)
            if item is None:
                return False
            running.add(pool.submit(score, *item))
            return True

        for _ in range(workers * 2):
            if not submit():
                break
        while running:
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                running.discard(future)
                try:
                    record = future.result()
                except Exception as error:  # noqa: BLE001 - only request failures are handled
                    transient = getattr(error, "transient", None)
                    if transient is None:
                        raise
                    if transient:
                        stats["transient_failures"] += 1
                        consecutive += 1
                        if consecutive >= MAX_CONSECUTIVE_FAILURES:
                            stats["stopped"] = f"{consecutive} transient failures in a row"
                    else:
                        stats["stopped"] = f"request refused: {error}"
                else:
                    consecutive = 0
                    out.write(json.dumps(record, sort_keys=True) + "\n")
                    out.flush()
                    if "answers" in record:
                        tokens = int(record["usage"]["input_tokens"])
                        stats["scored"] += 1
                        stats["input_tokens"] += tokens
                        stats["usd"] += cost(record["usage"])
                    else:
                        stats["unscorable"] += 1
                    settled = stats["scored"] + stats["unscorable"]
                    if progress and settled % progress_every == 0:
                        progress(dict(stats))
                submit()
    return stats
