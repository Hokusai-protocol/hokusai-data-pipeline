# ruff: noqa: T201 - a CLI stand-in prints its result
"""A stand-in for ``hokusai-scan corpus-feature-audit`` in assembly unit tests.

It speaks the real CLI's interface (exit codes and JSON) over a tiny manifest.
The real validator's rules are tested in test_leakage_conformance.py, never here.
"""

import json
import sys

VERSION = sys.argv[1]
ENTRIES = [
    {"name": "feature.shape.loc_touched", "kind": "integer", "segment": False},
    {"name": "feature.history.file_commits_90d", "kind": "integer", "segment": False},
    {"name": "feature.agent.tool_family", "kind": "category", "segment": False},
    {"name": "feature.content.title_sha256", "kind": "content_sha256", "segment": False},
    {"name": "segment.ci.checks_failed_by_merge", "kind": "integer", "segment": True},
]


def main() -> int:
    args = sys.argv[2:]
    if args[:1] != ["corpus-feature-audit"]:
        return 2
    if "--print-manifest" in args:
        print(json.dumps({"manifest_version": VERSION, "entries": ENTRIES}))
        return 0
    columns = json.load(open(args[args.index("--columns") + 1]))
    allow = "--allow-segments" in args
    declared = {e["name"]: e for e in ENTRIES}
    errors = []
    for i, name in enumerate(columns):
        if name.startswith("label."):
            code = "label_field"
        elif name not in declared:
            code = "undeclared_column"
        elif declared[name]["segment"] and not allow:
            code = "segment_in_arm_input"
        else:
            continue
        errors.append({"path": f"columns[{i}]", "code": code, "message": f"{name}: {code}"})
    print(json.dumps({"manifest_version": VERSION, "ok": not errors, "errors": errors}))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
