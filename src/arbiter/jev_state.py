# ruff: noqa: ANN101, S603, S607 - git is called with fixed arguments; self needs no annotation
"""The merge-time state sent to a snap-judgment model for one PR (HOK-3026, HOK-3027).

The state holds what a reviewer could read at the moment of merge and nothing
later:

* the title and description as they were at ``as_of``, rebuilt from the private
  evidence capture (the same rules as ``titleAt`` / ``bodyAt`` in hokusai-sdk
  ``packages/scan/src/corpus/features.ts``), never from GitHub today
* the diff ``git diff <base_sha> <merge_sha>`` from the corpus clone

Identifiers that would let a model look the outcome up are redacted: URLs, the
repo's ``owner/name``, issue and PR references and, in prose, mentions, emails
and the project's name. The code itself still identifies a project to a model
that has memorized it; redaction only removes lookup by id.

Large diffs are cut by a fixed rule (``STATE_VERSION``), recorded per row. Raw
text is built in memory and never written to disk by this module.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Frozen 2026-11-14 with the question set. States built under the draft name used
# exactly these rules.
STATE_VERSION = "jev-state/0.1.0"
STATE_ALIASES = frozenset({"jev-state/0.1.0-draft"})

# Jev's default limits are 64k tokens per request and 32k per question, and its
# accuracy falls as the state grows. The dry run measured about 2.5 characters
# per token on average and 1.9 on the densest state, so a 40k diff budget keeps
# almost every state under the per-question limit; the caller halves the budget
# for the few that still exceed it.
DIFF_BUDGET_CHARS = 40_000
TITLE_MAX_CHARS = 300
BODY_MAX_CHARS = 6_000
MAX_FILES_LISTED = 100
# Patches are requested for at most this many files and changed lines, in priority order.
MAX_PATCH_FILES = 200
MAX_PATCH_LINES = 20_000
DIFF_FLAGS = ("--no-renames", "--no-ext-diff", "--no-textconv", "--no-color")

KIND_ORDER = ("source", "test", "docs")  # generated and binary files are listed, never shown
_GENERATED = re.compile(
    r"(^|/)(vendor|vendored|third_party|third-party|node_modules|dist)/"
    r"|(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|Cargo\.lock|go\.sum|poetry\.lock"
    r"|uv\.lock|Gemfile\.lock|composer\.lock)$"
    r"|\.(min\.js|min\.css|map|snap|pb\.go|pb\.cc|pb\.h)$|_pb2(_grpc)?\.py$|\.generated\.",
    re.IGNORECASE,
)
_TEST = re.compile(
    r"(^|/)(tests?|__tests__|specs?|testdata|testing|unittests?|e2e|fixtures)/"
    r"|(^|/)test_[^/]+$|_test\.[a-z0-9]+$|\.(test|spec)\.[a-z0-9]+$|Tests?\.(java|kt|cs|swift)$",
    re.IGNORECASE,
)
_DOCS = re.compile(
    r"(^|/)(docs?|documentation)/|\.(md|mdx|rst|adoc|txt)$"
    r"|(^|/)(LICENSE|NOTICE|CHANGELOG|CHANGES|AUTHORS)[^/]*$",
    re.IGNORECASE,
)
_SIZES = ((10, "tiny"), (50, "small"), (200, "medium"), (1000, "large"))
_STATUS = {"A": "added", "D": "deleted", "M": "modified", "T": "type changed"}


def file_kind(path: str) -> str:
    """Classify a changed path. Generated wins over test, test over docs."""
    if _GENERATED.search(path):
        return "generated"
    if _TEST.search(path):
        return "test"
    if _DOCS.search(path):
        return "docs"
    return "source"


def size_word(lines: int) -> str:
    """Return a changed-line count as a word: the model is not asked to compare numbers."""
    for limit, word in _SIZES:
        if lines <= limit:
            return word
    return "huge"


# --------------------------------------------------------------------------- evidence at as_of


def _ms(at: str) -> float:
    return datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()


def _by_time(events: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(events, key=lambda e: _ms(e["at"]))  # stable: ties keep capture order


def title_at(evidence: Mapping[str, Any], as_of: str) -> str:
    """Return the title at ``as_of``, from rename events."""
    renames = _by_time(evidence.get("renames") or [])
    if not renames:
        return evidence["title"]
    seen = [r for r in renames if _ms(r["at"]) <= _ms(as_of)]
    return seen[-1]["to"] if seen else renames[0]["from"]


def body_at(evidence: Mapping[str, Any], as_of: str) -> str | None:
    """Return the body at ``as_of``, from edit history, or None when that version is gone."""
    edits = evidence.get("body_edits") or []
    if not edits:
        return evidence.get("body") or ""
    seen = [e for e in _by_time(edits) if _ms(e["at"]) <= _ms(as_of)]
    return seen[-1]["body"] if seen else None


def _batch_item(directory: Path, pr_number: int) -> Mapping[str, Any] | None:
    """Return one PR's captured value from the batch file whose number range holds it."""
    if not directory.is_dir():
        return None
    for path in directory.iterdir():
        match = re.fullmatch(r"(\d+)-(\d+)\.json\.gz", path.name)
        if match and int(match[1]) <= pr_number <= int(match[2]):
            with gzip.open(path, "rt") as f:
                for item in json.load(f)["items"]:
                    if item["pr_number"] == pr_number:
                        return item["value"]
    return None


def read_evidence(repo_dir: Path, pr_number: int) -> dict[str, Any] | None:
    """Return a PR's evidence with its timeline events, or None when either was not captured.

    Without the timeline the title at ``as_of`` is unknown, as in hokusai-sdk's
    ``feature-run.ts``.
    """
    evidence = _batch_item(repo_dir / "feature-evidence" / "evidence", pr_number)
    timeline = _batch_item(repo_dir / "feature-evidence" / "timeline", pr_number)
    if evidence is None or timeline is None:
        return None
    merged = dict(evidence)
    for key in ("renames", "label_events", "dismissals"):
        merged[key] = timeline.get(key) or []
    return merged


# --------------------------------------------------------------------------- redaction

_URL = re.compile(r"https?://[^\s)>\]\"']+")
_REF = re.compile(r"(?<![0-9A-Za-z&#])#\d{1,7}(?![0-9A-Za-z])|\bGH-\d+\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_MENTION = re.compile(r"(?<![\w`])@[A-Za-z0-9][A-Za-z0-9-]*")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def redact(text: str, repo: str, *, prose: bool) -> str:
    """Remove identifiers that would let a model look this PR up.

    Code keeps its ``@decorators`` and bare project name: replacing them would
    corrupt the diff. Prose loses mentions, emails and the project's name too.
    """
    owner, name = repo.split("/", 1)
    text = _URL.sub("[url]", text)
    text = re.sub(re.escape(repo), "[repo]", text, flags=re.IGNORECASE)
    text = _REF.sub("#[ref]", text)
    if prose:
        text = _EMAIL.sub("[email]", text)
        text = _MENTION.sub("@[user]", text)
        for word in {owner, name}:
            if len(word) >= 4:
                text = re.sub(
                    rf"(?<![\w-]){re.escape(word)}(?![\w-])", "[project]", text, flags=re.IGNORECASE
                )
    return text


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "\n[description cut here]"


# --------------------------------------------------------------------------- diff


@dataclass(frozen=True)
class ChangedFile:
    """One path in the diff, from ``git diff --raw --numstat``."""

    path: str
    status: str
    added: int
    deleted: int
    binary: bool

    @property
    def lines(self) -> int:
        return self.added + self.deleted

    @property
    def kind(self) -> str:
        return "binary" if self.binary else file_kind(self.path)


def _git(git_dir: Path, *args: str) -> bytes | None:
    done = subprocess.run(["git", "--git-dir", str(git_dir), *args], capture_output=True)
    return done.stdout if done.returncode == 0 else None


def parse_raw_numstat(output: str) -> list[ChangedFile]:
    """Parse ``git diff --raw --numstat -z --no-renames``. Binary files count as zero lines."""
    tokens = output.split("\0")
    status: dict[str, str] = {}
    files: list[ChangedFile] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not token:
            continue
        if token.startswith(":"):
            status[tokens[i]] = token.split(" ")[4][:1]
            i += 1
            continue
        added, deleted, path = token.split("\t", 2)
        files.append(
            ChangedFile(
                path=path,
                status=_STATUS.get(status.get(path, "M"), "modified"),
                added=0 if added == "-" else int(added),
                deleted=0 if deleted == "-" else int(deleted),
                binary=added == "-",
            )
        )
    return files


def _priority(files: Sequence[ChangedFile]) -> list[ChangedFile]:
    """Files whose patch may be shown, by kind and then path."""
    shown = [f for f in files if f.kind in KIND_ORDER]
    return sorted(shown, key=lambda f: (KIND_ORDER.index(f.kind), f.path))


def _split_patch(patch: str) -> dict[str, str]:
    """Per-file hunks from one ``git diff -p``, without the git header lines."""
    out: dict[str, str] = {}
    for block in re.split(r"(?m)^diff --git ", patch)[1:]:
        lines = block.split("\n")
        path = None
        body: list[str] = []
        for n, line in enumerate(lines):
            if line.startswith("@@"):
                body = lines[n:]
                break
            if line.startswith("+++ b/"):
                path = line[6:]
            elif line.startswith("--- a/") and path is None:
                path = line[6:]
        if path is not None and body:
            out[path] = "\n".join(body).rstrip("\n")
    return out


def allocate(lengths: Sequence[int], budget: int) -> list[int]:
    """Water-fill ``budget`` over items: small ones are kept whole, large ones share the rest."""
    grant = [0] * len(lengths)
    order = sorted(range(len(lengths)), key=lambda i: lengths[i])
    left = budget
    for position, i in enumerate(order):
        share = left // (len(order) - position)
        grant[i] = min(lengths[i], share)
        left -= grant[i]
    return grant


def _cut(hunks: str, limit: int) -> str:
    if len(hunks) <= limit:
        return hunks
    kept = hunks[:limit]
    kept = kept[: kept.rfind("\n")] if "\n" in kept else ""
    return kept + "\n[the rest of this file's changes are not shown]"


def render_diff(
    files: Sequence[ChangedFile], patches: Mapping[str, str], budget: int
) -> tuple[str, dict[str, str], int]:
    """Return the diff text, how each path is shown, and the characters that were available.

    Source files are filled first, then tests, then docs; within a kind the
    budget is water-filled.
    """
    shown: dict[str, str] = {f.path: "not shown" for f in files}
    parts: list[str] = []
    available = 0
    left = budget
    for kind in KIND_ORDER:
        group = [f for f in _priority(files) if f.kind == kind and f.path in patches]
        available += sum(len(patches[f.path]) for f in group)
        grants = allocate([len(patches[f.path]) for f in group], left)
        for f, grant in zip(group, grants, strict=True):
            hunks = patches[f.path]
            if grant <= 0:
                continue
            text = _cut(hunks, grant)
            shown[f.path] = "in full" if len(hunks) <= grant else "in part"
            parts.append(f"=== {f.path} ({f.status}, {f.kind})\n{text}")
            left -= min(len(hunks), grant)
    return "\n\n".join(parts), shown, available


def read_diff(git_dir: Path, base_sha: str, merge_sha: str) -> tuple[list[ChangedFile], dict]:
    """Return the changed files and the patches of the highest-priority ones."""
    raw = _git(git_dir, "diff", *DIFF_FLAGS, "--raw", "--numstat", "-z", base_sha, merge_sha)
    if raw is None:
        raise StateUnavailableError("git could not diff the base and merge commits")
    files = parse_raw_numstat(raw.decode("utf-8", errors="replace"))
    wanted: list[str] = []
    lines = 0
    for f in _priority(files):
        if len(wanted) >= MAX_PATCH_FILES or lines >= MAX_PATCH_LINES:
            break
        wanted.append(f.path)
        lines += f.lines
    patches: dict[str, str] = {}
    if wanted:
        out = _git(git_dir, "diff", *DIFF_FLAGS, "-U3", "-p", base_sha, merge_sha, "--", *wanted)
        if out is None:
            raise StateUnavailableError("git could not produce the patch")
        patches = _split_patch(out.decode("utf-8", errors="replace"))
    return files, patches


# --------------------------------------------------------------------------- state


class StateUnavailableError(Exception):
    """The merge-time state cannot be rebuilt for this PR."""


@dataclass(frozen=True)
class BuiltState:
    """The request ``state`` and facts about how it was built. ``meta`` holds no raw text."""

    state: dict[str, Any]
    meta: dict[str, Any]


def build_state(
    *,
    repo: str,
    title: str | None,
    body: str | None,
    files: Sequence[ChangedFile],
    patches: Mapping[str, str],
    diff_budget: int = DIFF_BUDGET_CHARS,
) -> BuiltState:
    """Assemble the state from merge-time parts. ``title`` or ``body`` None means unknown."""
    diff, shown, available = render_diff(files, patches, diff_budget)
    diff = redact(diff, repo, prose=False)
    listed = sorted(files, key=lambda f: (-f.lines, f.path))[:MAX_FILES_LISTED]
    change: dict[str, Any] = {
        "title": None if title is None else redact(title, repo, prose=True)[:TITLE_MAX_CHARS],
        "description": None
        if body is None
        else _clip(redact(_HTML_COMMENT.sub("", body).strip(), repo, prose=True), BODY_MAX_CHARS),
        "files": [
            {
                "path": redact(f.path, repo, prose=False),
                "status": f.status,
                "kind": f.kind,
                "size": size_word(f.lines),
                "diff": shown[f.path],
            }
            for f in listed
        ],
        "diff": diff,
    }
    truncated = any(v == "in part" for v in shown.values()) or any(
        shown[f.path] == "not shown" for f in files if f.kind in KIND_ORDER
    )
    if len(files) > len(listed):
        change["more_files_not_listed"] = True
    if truncated:
        change["diff_is_partial"] = True
    state = {"change": change}
    encoded = json.dumps(state, sort_keys=True, ensure_ascii=False)
    return BuiltState(
        state=state,
        meta={
            "state_version": STATE_VERSION,
            "state_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "state_chars": len(encoded),
            "diff_budget_chars": diff_budget,
            "diff_chars_available": available,
            "diff_chars_shown": len(diff),
            "diff_truncated": truncated,
            "files_total": len(files),
            "files_listed": len(listed),
            "title_known": title is not None,
            "body_known": body is not None,
        },
    )


def state_for_row(
    *,
    corpus_root: Path,
    repo: str,
    pr_number: int,
    base_sha: str,
    merge_sha: str,
    as_of: str,
    diff_budget: int = DIFF_BUDGET_CHARS,
) -> BuiltState:
    """Rebuild one PR's merge-time state from the corpus clone and the private capture."""
    repo_dir = corpus_root / repo.replace("/", "__", 1)
    evidence = read_evidence(repo_dir, pr_number)
    title = None if evidence is None else title_at(evidence, as_of)
    body = None if evidence is None else body_at(evidence, as_of)
    files, patches = read_diff(repo_dir / "repo.git", base_sha, merge_sha)
    return build_state(
        repo=repo, title=title, body=body, files=files, patches=patches, diff_budget=diff_budget
    )


def base_shas(corpus_root: Path, repo: str, pr_numbers: set[int]) -> dict[int, str]:
    """Return ``base_sha`` for the asked PRs, from the frozen feature rows."""
    out: dict[int, str] = {}
    path = corpus_root / repo.replace("/", "__", 1) / "features.jsonl.gz"
    with gzip.open(path, "rt") as f:
        for line in f:
            if len(out) == len(pr_numbers):
                break
            row = json.loads(line)
            if row["pr_number"] in pr_numbers:
                out[row["pr_number"]] = row["base_sha"]
    return out
