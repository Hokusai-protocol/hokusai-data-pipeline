#!/usr/bin/env python3
"""Recover per-model token usage for Wavemill evals whose own usage is untrusted (HOK-3402).

From 2026-06-24 to ~2026-10-26 Wavemill's cost meter recorded leaked test-fixture
tokens and dropped the real Codex/Claude sessions. The real sessions are still on
disk, so this joins each eval record to them:

* **Join key:** the record's PR head branch (``task/<slug>``, from GitHub) equals
  the harness session's working directory name (Wavemill runs each task in
  ``.../worktrees/<slug>``), with the session starting within
  ``[timestamp - timeSeconds - 24h, timestamp + 30m]``.
* **Codex** (``~/.codex/sessions``): per-model deltas of the cumulative
  ``token_count`` totals. ``outputTokens`` = output + reasoning, which is what
  Wavemill recorded. Inputs use OpenAI semantics (input *includes* cached).
  Validated: 238/238 trusted pre-window records reproduced exactly.
* **Claude Code** (``~/.claude/projects``, kept ~30 days): assistant usage,
  deduplicated by ``message.id`` (each streamed content block repeats it).
* **Wavemill ``executionEconomics``** (Claude sessions older than the local
  transcripts): the turns double-count streamed blocks; consecutive turns with
  identical (model, usage) are dropped, which matches transcripts in 97% of
  sessions.

Output: ``{record_key: {"sources": [...], "sessions": n, "usage": {model: {...}}}}``
in ``workflowTokenUsage`` shape with ``costUsd`` 0, so the collector reprices it.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.model_30.model_identity import normalize_model_id  # noqa: E402

SCHEMA_VERSION = "model_30_recovered_session_usage/v1"
WINDOW_BEFORE = timedelta(hours=24)
WINDOW_AFTER = timedelta(minutes=30)
PR_URL = re.compile(r"https://github.com/([^/]+)/([^/]+)/pull/(\d+)")
_EMPTY = {"inputTokens": 0, "cacheReadTokens": 0, "cacheCreationTokens": 0, "outputTokens": 0}
# Every recovered usage dict uses exclusive cache semantics (input excludes cache reads).
CACHE_SEMANTICS = {"cacheSemantics": "exclusive"}
_DATE_SUFFIX = re.compile(r"-20\d{6}$")
OPENROUTER_SLACK = timedelta(minutes=5)


def record_key(record: dict[str, Any]) -> str:
    """Stable key for one eval record (shared with the collector)."""
    return "|".join(str(record.get(k) or "") for k in ("timestamp", "issueId", "prUrl"))


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _add(target: dict[str, dict[str, float]], model: str, usage: dict[str, float]) -> None:
    bucket = target.setdefault(model, dict(_EMPTY))
    for key in _EMPTY:
        bucket[key] += usage.get(key, 0) or 0


# --- Codex -----------------------------------------------------------------


def parse_codex_lines(lines: Iterable[str]) -> dict[str, Any]:
    """Session meta plus per-model usage from a Codex rollout's JSONL lines."""
    meta: dict[str, Any] = {}
    start = end = model = None
    last = {"input": 0, "cached": 0, "output": 0, "reasoning": 0}
    usage: dict[str, dict[str, float]] = {}
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamp = row.get("timestamp")
        if stamp:
            start = start or stamp
            end = stamp
        kind, payload = row.get("type"), row.get("payload") or {}
        if kind == "session_meta":
            meta = payload
        elif kind == "turn_context":
            model = payload.get("model") or model
        elif kind == "event_msg" and payload.get("type") == "token_count":
            total = (payload.get("info") or {}).get("total_token_usage") or {}
            if not total:
                continue
            current = {
                "input": total.get("input_tokens") or 0,
                "cached": total.get("cached_input_tokens") or 0,
                "output": total.get("output_tokens") or 0,
                "reasoning": total.get("reasoning_output_tokens") or 0,
            }
            delta = {k: max(current[k] - last[k], 0) for k in current}
            last = current
            if model:
                _add(
                    usage,
                    model,
                    {
                        # OpenAI input includes cached reads; store them exclusive.
                        "inputTokens": max(delta["input"] - delta["cached"], 0),
                        "cacheReadTokens": delta["cached"],
                        "outputTokens": delta["output"] + delta["reasoning"],
                    },
                )
    return {
        "harness": "codex",
        "session_id": meta.get("id"),
        "cwd": meta.get("cwd"),
        "start": start,
        "end": end,
        "usage": usage,
    }


def _parse_codex_file(path: str) -> dict[str, Any]:
    if path.endswith(".zst"):
        raw = subprocess.run(  # noqa: S603
            ["zstd", "-dc", path],  # noqa: S607
            capture_output=True,
            check=False,
        ).stdout
        lines = raw.decode("utf-8", "replace").splitlines()
    else:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return {**parse_codex_lines(lines), "file": path}


# --- Claude Code -----------------------------------------------------------


def parse_claude_lines(lines: Iterable[str]) -> dict[str, Any]:
    """Transcript meta plus per-model usage, deduplicated by assistant message id."""
    cwd = branch = start = end = session_id = None
    by_message: dict[str, tuple[str, dict[str, Any]]] = {}
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        cwd = cwd or row.get("cwd")
        branch = branch or row.get("gitBranch")
        session_id = session_id or row.get("sessionId")
        stamp = row.get("timestamp")
        if stamp:
            start = start or stamp
            end = stamp
        message = row.get("message")
        if row.get("type") == "assistant" and isinstance(message, dict) and message.get("usage"):
            key = message.get("id") or row.get("uuid")
            by_message[str(key)] = (message.get("model") or "", message["usage"])
    usage: dict[str, dict[str, float]] = {}
    for model, u in by_message.values():
        if not model or model.startswith("<"):
            continue
        _add(
            usage,
            model,
            {
                "inputTokens": u.get("input_tokens") or 0,
                "cacheReadTokens": u.get("cache_read_input_tokens") or 0,
                "cacheCreationTokens": u.get("cache_creation_input_tokens") or 0,
                "outputTokens": u.get("output_tokens") or 0,
            },
        )
    return {
        "harness": "claude",
        "session_id": session_id,
        "cwd": cwd,
        "branch": branch,
        "start": start,
        "end": end,
        "usage": usage,
    }


def _parse_claude_file(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return {**parse_claude_lines(handle), "file": path}


# --- Wavemill executionEconomics -----------------------------------------------


def execution_economics_usage(
    record: dict[str, Any],
    transcripts_by_session: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, dict[str, float]], int, list[str]]:
    """Usage from ``executionEconomics`` sessions; local transcripts win when present."""
    usage: dict[str, dict[str, float]] = {}
    sessions = 0
    sources: set[str] = set()
    for block in record.get("executionEconomics") or []:
        if not isinstance(block, dict):
            continue
        for session in block.get("sessions") or []:
            sessions += 1
            local = transcripts_by_session.get(str(session.get("sessionId")))
            if local:
                for transcript in local:
                    for model, u in transcript["usage"].items():
                        _add(usage, model, u)
                sources.add("claude_transcripts")
                continue
            previous = None
            for turn in session.get("turns") or []:
                tu = turn.get("usage") or {}
                key = (turn.get("model"), json.dumps(tu, sort_keys=True))
                if key == previous:
                    continue  # repeated streamed block
                previous = key
                model = turn.get("model") or ""
                if not model or model.startswith("<"):
                    continue
                _add(
                    usage,
                    model,
                    {
                        "inputTokens": tu.get("inputTokens") or 0,
                        "cacheReadTokens": tu.get("cacheReadTokens") or 0,
                        "cacheCreationTokens": tu.get("cacheWriteTokens") or 0,
                        "outputTokens": tu.get("outputTokens") or 0,
                    },
                )
            sources.add("execution_economics")
    return usage, sessions, sorted(sources)


# --- join ------------------------------------------------------------------


def sessions_for(
    record: dict[str, Any],
    branch: str | None,
    by_slug: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Sessions whose worktree matches *branch* and that started in the record's window."""
    if not branch:
        return []
    slug = branch.split("/", 1)[-1]
    candidates = list(by_slug.get(slug, []))
    if not candidates:  # worktree directory names may be truncated
        candidates = [
            s
            for name, group in by_slug.items()
            if len(name) >= 40 and slug.startswith(name)
            for s in group
        ]
    end = _ts(record.get("timestamp"))
    if end is None:
        return []
    duration = timedelta(seconds=float(record.get("timeSeconds") or 0))
    lo, hi = end - duration - WINDOW_BEFORE, end + WINDOW_AFTER
    return [s for s in candidates if (start := _ts(s.get("start"))) and lo <= start <= hi]


def _record_window(record: dict[str, Any]) -> tuple[datetime, datetime] | None:
    end = _ts(record.get("timestamp"))
    if end is None:
        return None
    return end - timedelta(seconds=float(record.get("timeSeconds") or 0)), end


def _route_models(record: dict[str, Any]) -> set[str]:
    stages = (record.get("taskDescriptor") or {}).get("stages") or {}
    models = {
        normalize_model_id((stages.get(role) or {}).get("model"))
        for role in ("planner", "coder", "reviewer")
    }
    return {m for m in models if m}


def load_openrouter_calls(path: Path) -> list[dict[str, Any]]:
    """OpenRouter activity export rows (dashboard CSV) with normalized model ids."""
    calls = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            stamp = _ts(row["created_at"].replace(" ", "T") + "Z")
            prompt = float(row.get("tokens_prompt") or 0)
            cached = float(row.get("tokens_cached") or 0)
            calls.append(
                {
                    "t": stamp,
                    "model": normalize_model_id(_DATE_SUFFIX.sub("", row["model_permaslug"])),
                    "usage": {
                        "inputTokens": max(prompt - cached, 0),
                        "cacheReadTokens": cached,
                        "cacheCreationTokens": 0,
                        "outputTokens": float(row.get("tokens_completion") or 0),
                    },
                    "cost": float(row.get("cost_total") or 0),
                }
            )
    return calls


def openrouter_usage(
    record: dict[str, Any],
    calls: list[dict[str, Any]],
    native_windows: list[tuple[str, datetime, datetime, set[str]]],
) -> tuple[dict[str, dict[str, float]], list[str]]:
    """Billed OpenRouter usage for a native-openrouter record's route models.

    The export carries no task id, so calls are attributed by time window and
    model. A model is skipped (ambiguous) when another native-openrouter record
    using it overlaps this record's window.
    """
    window = _record_window(record)
    if window is None:
        return {}, []
    start, end = window
    key = record_key(record)
    ambiguous = {
        model
        for other_key, lo, hi, models in native_windows
        if other_key != key and lo <= end + OPENROUTER_SLACK and hi >= start - OPENROUTER_SLACK
        for model in models
    }
    route = _route_models(record)
    usage: dict[str, dict[str, float]] = {}
    for call in calls:
        model = call["model"]
        if model not in route or model in ambiguous or call["t"] is None:
            continue
        if start - OPENROUTER_SLACK <= call["t"] <= end + OPENROUTER_SLACK:
            _add(usage, model, call["usage"])
            usage[model]["costUsd"] = usage[model].get("costUsd", 0.0) + call["cost"]
    return usage, sorted(route & ambiguous)


def _merge(target: dict[str, dict[str, float]], source: dict[str, dict[str, float]]) -> None:
    for model, u in source.items():
        if model not in target:
            target[model] = dict(u)


def recover_record(
    record: dict[str, Any],
    branch: str | None,
    indexes: dict[str, Any],
) -> dict[str, Any] | None:
    """Recovered usage for one record, or None when no session evidence exists.

    *indexes*: ``codex_by_slug``, ``claude_by_slug``, ``claude_by_session`` and
    optionally ``openrouter_calls`` / ``native_windows``. Sources are tried in
    order of exactness; a later source never overrides a model already found.
    """
    usage, sources, sessions = _harness_usage(record, branch, indexes)
    ambiguous: list[str] = []
    if record.get("agentType") == "native-openrouter" and indexes.get("openrouter_calls"):
        or_usage, ambiguous = openrouter_usage(
            record, indexes["openrouter_calls"], indexes.get("native_windows") or []
        )
        if or_usage:
            _merge(usage, or_usage)
            sources.append("openrouter_activity")
    if not usage:
        return None
    entry = {
        "sources": sorted(set(sources)),
        "sessions": sessions,
        "branch": branch,
        "usage": {m: {"costUsd": 0, **u, **CACHE_SEMANTICS} for m, u in sorted(usage.items())},
    }
    if ambiguous:
        entry["ambiguous_openrouter_models"] = ambiguous
    return entry


def _harness_usage(
    record: dict[str, Any], branch: str | None, indexes: dict[str, Any]
) -> tuple[dict[str, dict[str, float]], list[str], int]:
    """Usage from Codex sessions, then executionEconomics or Claude transcripts."""
    usage: dict[str, dict[str, float]] = {}
    sources: list[str] = []
    sessions = 0
    codex = sessions_for(record, branch, indexes["codex_by_slug"])
    for session in codex:
        for model, u in session["usage"].items():
            _add(usage, model, u)
    if codex:
        sources.append("codex_sessions")
        sessions += len(codex)
    ee_usage, ee_sessions, ee_sources = execution_economics_usage(
        record, indexes["claude_by_session"]
    )
    if ee_usage:
        _merge(usage, ee_usage)
        sources.extend(ee_sources)
        sessions += ee_sessions
    else:
        claude = sessions_for(record, branch, indexes["claude_by_slug"])
        claude_usage: dict[str, dict[str, float]] = {}
        for session in claude:
            for model, u in session["usage"].items():
                _add(claude_usage, model, u)
        if claude:
            _merge(usage, claude_usage)
            sources.append("claude_transcripts")
            sessions += len(claude)
    return usage, sources, sessions


# --- I/O -------------------------------------------------------------------


def iter_eval_records(snapshot: Path) -> Iterator[dict[str, Any]]:
    """Training- or budget-eligible eval records under *snapshot*, deduplicated."""
    seen: set[str] = set()
    for path in sorted(snapshot.rglob("evals.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not (record.get("trainingEligible") or record.get("budgetEvalEligible")):
                    continue
                key = record_key(record)
                if key not in seen:
                    seen.add(key)
                    yield record


def fetch_pr_branches(urls: list[str], cache: dict[str, Any]) -> dict[str, Any]:
    """Fill *cache* with ``{pr_url: {"headRefName": ...}}`` via ``gh api graphql``."""
    missing = [u for u in urls if u not in cache and PR_URL.match(u)]
    for offset in range(0, len(missing), 40):
        chunk = missing[offset : offset + 40]
        parts = []
        for i, url in enumerate(chunk):
            owner, name, number = PR_URL.match(url).groups()  # type: ignore[union-attr]
            parts.append(
                f'p{i}: repository(owner:"{owner}",name:"{name}")'
                f"{{pullRequest(number:{number}){{headRefName createdAt}}}}"
            )
        query = "query{" + " ".join(parts) + "}"
        result = subprocess.run(  # noqa: S603
            ["gh", "api", "graphql", "-f", f"query={query}"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        data = (json.loads(result.stdout or "{}").get("data")) or {}
        for i, url in enumerate(chunk):
            pr = (data.get(f"p{i}") or {}).get("pullRequest")
            if pr:
                cache[url] = pr
    return cache


def _index(paths: list[str], parser: Callable[[str], dict[str, Any]]) -> list[dict[str, Any]]:
    with ProcessPoolExecutor() as pool:
        return [s for s in pool.map(parser, paths, chunksize=16) if s.get("usage")]


def _by_slug(sessions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for session in sessions:
        if session.get("cwd"):
            grouped[Path(session["cwd"]).name].append(session)
    return grouped


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", type=Path, required=True, help="Wavemill eval snapshot root")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pr-branch-cache", type=Path, required=True)
    parser.add_argument("--codex-root", type=Path, default=Path.home() / ".codex" / "sessions")
    parser.add_argument("--claude-root", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--since", default="2026-04-01", help="Ignore sessions before this date")
    parser.add_argument(
        "--openrouter-activity",
        type=Path,
        help="OpenRouter dashboard activity export (CSV) for native-openrouter runs",
    )
    parser.add_argument("--report", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Build the recovered-usage file."""
    args = parse_args(argv)
    records = list(iter_eval_records(args.snapshot))
    cache = json.loads(args.pr_branch_cache.read_text()) if args.pr_branch_cache.exists() else {}
    cache = fetch_pr_branches(sorted({r["prUrl"] for r in records if r.get("prUrl")}), cache)
    args.pr_branch_cache.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")

    since = args.since
    codex_files = [
        str(p)
        for p in sorted(args.codex_root.rglob("rollout-*"))
        if (m := re.search(r"rollout-(\d{4}-\d{2}-\d{2})", p.name)) and m.group(1) >= since
    ]
    codex = _index(codex_files, _parse_codex_file)
    claude = _index([str(p) for p in args.claude_root.rglob("*.jsonl")], _parse_claude_file)
    claude_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for session in claude:
        if session.get("session_id"):
            claude_by_session[str(session["session_id"])].append(session)

    indexes: dict[str, Any] = {
        "codex_by_slug": _by_slug(codex),
        "claude_by_slug": _by_slug(claude),
        "claude_by_session": claude_by_session,
    }
    if args.openrouter_activity:
        indexes["openrouter_calls"] = load_openrouter_calls(args.openrouter_activity)
        indexes["native_windows"] = [
            (record_key(r), *window, _route_models(r))
            for r in records
            if r.get("agentType") == "native-openrouter" and (window := _record_window(r))
        ]
    recovered: dict[str, Any] = {}
    for record in records:
        branch = (cache.get(record.get("prUrl") or "") or {}).get("headRefName")
        entry = recover_record(record, branch, indexes)
        if entry is not None:
            recovered[record_key(record)] = entry
    payload = {"schema_version": SCHEMA_VERSION, "records": recovered}
    args.output.write_text(json.dumps(payload, sort_keys=True) + "\n")
    report = {
        "eval_records": len(records),
        "recovered_records": len(recovered),
        "codex_sessions_indexed": len(codex),
        "claude_transcripts_indexed": len(claude),
        "pr_branches_cached": len(cache),
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
