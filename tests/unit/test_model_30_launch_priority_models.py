"""Contract tests for the Model 30 launch-priority model list."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("schema/model_30_launch_priority_models.v1.json")
CONFIG_PATH = Path("configs/model_30_launch_priority_models.v1.json")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_launch_priority_model_list_matches_schema() -> None:
    schema = _load_json(SCHEMA_PATH)
    config = _load_json(CONFIG_PATH)

    Draft202012Validator(schema).validate(config)


def test_launch_priority_model_ids_are_unique() -> None:
    config = _load_json(CONFIG_PATH)
    model_ids = [model["model_id"] for model in config["models"]]

    assert len(model_ids) == len(set(model_ids))


def test_launch_priority_model_list_includes_low_cost_challenger_families() -> None:
    config = _load_json(CONFIG_PATH)
    low_cost_families = {
        model["family"]
        for model in config["models"]
        if model["priority_tier"] == "low_cost_challenger"
    }

    assert {"qwen", "deepseek", "kimi"} <= low_cost_families
