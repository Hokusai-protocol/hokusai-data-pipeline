"""Contract tests for Model 30 retired-model lineage mappings."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from src.models.technical_task_router import BORROWED_EVIDENCE_WEIGHT, MODEL_SUCCESSOR_MAP

SCHEMA_PATH = Path("schema/model_30_model_lineage.v1.json")
CONFIG_PATH = Path("configs/model_30_model_lineage.v1.json")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_model_lineage_config_matches_schema() -> None:
    schema = _load_json(SCHEMA_PATH)
    config = _load_json(CONFIG_PATH)

    Draft202012Validator(schema).validate(config)


def test_model_lineage_config_matches_router_successor_map() -> None:
    config = _load_json(CONFIG_PATH)
    config_map = {
        mapping["deprecated_model_id"]: tuple(mapping["successor_model_ids"])
        for mapping in config["mappings"]
    }

    assert config["evidence_weight_default"] == BORROWED_EVIDENCE_WEIGHT
    assert config_map == MODEL_SUCCESSOR_MAP
    assert {mapping["evidence_weight"] for mapping in config["mappings"]} == {
        BORROWED_EVIDENCE_WEIGHT
    }
