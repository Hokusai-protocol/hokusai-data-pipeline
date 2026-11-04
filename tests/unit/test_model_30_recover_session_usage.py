"""HOK-3402: recover per-model token usage from Codex/Claude sessions and OpenRouter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.model_30.executed_route import route_economics
from scripts.model_30.recover_session_usage import (
    execution_economics_usage,
    load_openrouter_calls,
    openrouter_usage,
    parse_claude_lines,
    parse_codex_lines,
    record_key,
    recover_record,
    sessions_for,
)
from src.model_30.model_identity import (
    ModelPrice,
    exclusive_cache_usage,
    priced_usage_cost,
)


def _codex_lines() -> list[str]:
    def token(inp: int, cached: int, out: int, reasoning: int) -> str:
        return json.dumps(
            {
                "timestamp": "2026-08-01T10:05:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": inp,
                            "cached_input_tokens": cached,
                            "output_tokens": out,
                            "reasoning_output_tokens": reasoning,
                        }
                    },
                },
            }
        )

    return [
        json.dumps(
            {
                "timestamp": "2026-08-01T10:00:00Z",
                "type": "session_meta",
                "payload": {"id": "s1", "cwd": "/w/worktrees/add-thing"},
            }
        ),
        json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.5"}}),
        token(1000, 800, 50, 10),
        token(3000, 2600, 120, 30),  # cumulative totals: only the delta counts
    ]


def test_codex_usage_is_cumulative_delta_with_cache_excluded() -> None:
    session = parse_codex_lines(_codex_lines())
    assert session["cwd"] == "/w/worktrees/add-thing"
    usage = session["usage"]["gpt-5.5"]
    # input 3000 includes 2600 cached (OpenAI semantics) -> 400 uncached
    assert usage["inputTokens"] == 400
    assert usage["cacheReadTokens"] == 2600
    assert usage["outputTokens"] == 150  # output + reasoning, as Wavemill records


def test_claude_usage_is_deduplicated_by_message_id() -> None:
    line = {
        "type": "assistant",
        "cwd": "/w/worktrees/add-thing",
        "sessionId": "c1",
        "timestamp": "2026-10-01T00:00:00Z",
        "message": {
            "id": "msg_1",
            "model": "claude-opus-4-7",
            "usage": {
                "input_tokens": 3,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 200,
                "output_tokens": 40,
            },
        },
    }
    session = parse_claude_lines([json.dumps(line), json.dumps(line)])  # streamed twice
    assert session["usage"]["claude-opus-4-7"]["outputTokens"] == 40
    assert session["usage"]["claude-opus-4-7"]["cacheCreationTokens"] == 200


def test_execution_economics_drops_repeated_streamed_turns() -> None:
    turn = {"model": "claude-fable-5", "usage": {"outputTokens": 100, "cacheReadTokens": 5}}
    other = {"model": "claude-fable-5", "usage": {"outputTokens": 7, "cacheReadTokens": 5}}
    record = {
        "executionEconomics": [{"sessions": [{"sessionId": "x", "turns": [turn, turn, other]}]}]
    }
    usage, sessions, sources = execution_economics_usage(record, {})
    assert usage["claude-fable-5"]["outputTokens"] == 107
    assert sessions == 1
    assert sources == ["execution_economics"]


def test_sessions_match_on_worktree_slug_and_time_window() -> None:
    record = {"timestamp": "2026-08-01T12:00:00Z", "timeSeconds": 3600}
    by_slug = {
        "add-thing": [
            {"start": "2026-08-01T10:00:00Z"},  # in window
            {"start": "2026-07-25T10:00:00Z"},  # a week earlier: another run
        ]
    }
    hits = sessions_for(record, "task/add-thing", by_slug)
    assert [h["start"] for h in hits] == ["2026-08-01T10:00:00Z"]
    assert sessions_for(record, "task/other", by_slug) == []


def test_recovered_entry_is_exclusive_and_repriced(tmp_path: Path) -> None:
    session = {**parse_codex_lines(_codex_lines()), "start": "2026-08-01T10:00:00Z"}
    record = {
        "timestamp": "2026-08-01T12:00:00Z",
        "timeSeconds": 3600,
        "prUrl": "https://github.com/o/r/pull/1",
    }
    entry = recover_record(
        record,
        "task/add-thing",
        {"codex_by_slug": {"add-thing": [session]}, "claude_by_slug": {}, "claude_by_session": {}},
    )
    assert entry is not None and entry["sources"] == ["codex_sessions"]
    usage = entry["usage"]["gpt-5.5"]
    assert usage["cacheSemantics"] == "exclusive" and usage["costUsd"] == 0
    # exclusive usage is never re-subtracted
    assert exclusive_cache_usage("gpt-5.5", usage) == (usage, False)
    route = {"planner": "gpt-5.5", "coder": "gpt-5.5", "reviewer": "gpt-5.5"}
    contaminated = {
        "workflowTokenUsage": {"scripted:fixture": {"inputTokens": 5, "outputTokens": 5}},
        "pricingSnapshot": {"gpt-5.5": {"inputCostPerMTok": 5, "outputCostPerMTok": 30}},
    }
    econ = route_economics(contaminated, route, recovered=entry)
    assert econ.cost_status == "recovered:codex_sessions"
    expected = 400 * 5e-6 + 2600 * 0.5e-6 + 150 * 30e-6  # cache read defaults to 10% of input
    assert econ.total_cost_usd == pytest.approx(expected)


def test_openai_recorded_usage_no_longer_double_counts_cache() -> None:
    usage = {"inputTokens": 3000, "cacheReadTokens": 2600, "outputTokens": 150, "costUsd": 9.9}
    fixed, changed = exclusive_cache_usage("gpt-5.4", usage)
    assert changed and fixed["inputTokens"] == 400
    claude = {"inputTokens": 3, "cacheReadTokens": 2600, "outputTokens": 150}
    assert exclusive_cache_usage("claude-opus-4-7", claude) == (claude, False)


def test_missing_cache_read_price_defaults_to_ten_percent_of_input() -> None:
    price = ModelPrice(input_per_token=5e-6, output_per_token=30e-6)
    cost = priced_usage_cost({"cacheReadTokens": 1_000_000}, price)
    assert cost == pytest.approx(0.5)


def test_openrouter_calls_attributed_by_window_and_skip_overlapping_runs(tmp_path: Path) -> None:
    path = tmp_path / "activity.csv"
    path.write_text(
        "generation_id,created_at,cost_total,tokens_prompt,tokens_completion,tokens_cached,model_permaslug\n"
        "g1,2026-08-01 10:30:00.000,0.40,1000,100,600,z-ai/glm-5.2-20260616\n"
        "g2,2026-08-01 10:40:00.000,0.10,500,50,0,moonshotai/kimi-k2.7-code-20260612\n"
        "g3,2026-08-03 10:40:00.000,9.00,500,50,0,z-ai/glm-5.2-20260616\n"
    )
    calls = load_openrouter_calls(path)
    stages = {r: {"model": "glm-5.2"} for r in ("planner", "coder", "reviewer")}
    record = {
        "timestamp": "2026-08-01T11:00:00Z",
        "timeSeconds": 3600,
        "taskDescriptor": {"stages": stages},
    }
    usage, ambiguous = openrouter_usage(record, calls, [])
    assert usage["glm-5.2"]["costUsd"] == pytest.approx(0.40)
    assert usage["glm-5.2"]["inputTokens"] == 400
    assert "kimi-k2.7-code" not in usage and ambiguous == []
    lo = datetime(2026, 8, 1, 10, tzinfo=timezone.utc)
    overlapping = [("other", lo, lo.replace(hour=12), {"glm-5.2"})]
    usage, ambiguous = openrouter_usage(record, calls, overlapping)
    assert usage == {} and ambiguous == ["glm-5.2"]
    assert record_key(record) == "2026-08-01T11:00:00Z||"
