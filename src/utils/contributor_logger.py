"""Utilities for contributor attribution metadata in DSPy executions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

ROLE_TO_TAG_KEY = {
    "prompt_author": "hokusai.contributor.prompt_author_id",
    "training_data_uploader": "hokusai.contributor.training_data_uploader_id",
    "human_labeler": "hokusai.contributor.human_labeler_id",
}
CONTRIBUTOR_ID_TAG_KEY = "contributor_id"
CONTRIBUTOR_ROLES_TAG_KEY = "hokusai.contributor.roles"
CONTRIBUTORS_JSON_TAG_KEY = "hokusai.contributors"


def _normalize_role(role: str) -> str:
    return role.strip().lower().replace("-", "_").replace(" ", "_")


@dataclass(slots=True)
class ContributorAttribution:
    """Normalized contributor attribution payload."""

    contributors_by_role: dict[str, str] = field(default_factory=dict)

    @property
    def primary_contributor_id(self) -> str | None:
        """Return a deterministic primary contributor ID."""
        for preferred_role in ("prompt_author", "training_data_uploader", "human_labeler"):
            contributor_id = self.contributors_by_role.get(preferred_role)
            if contributor_id:
                return contributor_id

        if self.contributors_by_role:
            first_role = sorted(self.contributors_by_role.keys())[0]
            return self.contributors_by_role[first_role]
        return None

    def to_mlflow_tags(self) -> dict[str, str]:
        """Convert attribution payload to MLflow tag keys."""
        tags: dict[str, str] = {}

        primary_id = self.primary_contributor_id
        if primary_id:
            tags[CONTRIBUTOR_ID_TAG_KEY] = primary_id

        if self.contributors_by_role:
            tags[CONTRIBUTORS_JSON_TAG_KEY] = json.dumps(self.contributors_by_role, sort_keys=True)
            tags[CONTRIBUTOR_ROLES_TAG_KEY] = ",".join(sorted(self.contributors_by_role.keys()))

        for role, contributor_id in self.contributors_by_role.items():
            tag_key = ROLE_TO_TAG_KEY.get(role)
            if tag_key:
                tags[tag_key] = contributor_id

        return tags

    def to_metadata(self) -> dict[str, Any]:
        """Convert attribution payload to execution result metadata."""
        return {
            "primary_contributor_id": self.primary_contributor_id,
            "contributors_by_role": dict(self.contributors_by_role),
        }


def build_contributor_attribution(
    *,
    contributor_id: str | None = None,
    contributor_role: str | None = None,
    contributors_by_role: dict[str, str] | None = None,
    inputs: dict[str, Any] | None = None,
) -> ContributorAttribution:
    """Build normalized contributor attribution from explicit args + execution inputs."""
    normalized: dict[str, str] = {}

    if contributors_by_role:
        for role, role_contributor_id in contributors_by_role.items():
            if role_contributor_id is None:
                continue
            role_key = _normalize_role(role)
            value = str(role_contributor_id).strip()
            if value:
                normalized[role_key] = value

    if contributor_id:
        role_key = _normalize_role(contributor_role or "prompt_author")
        value = str(contributor_id).strip()
        if value:
            normalized[role_key] = value

    source = inputs or {}
    for role in ROLE_TO_TAG_KEY:
        input_key = f"{role}_id"
        source_value = source.get(input_key)
        if source_value is not None and str(source_value).strip():
            normalized[role] = str(source_value).strip()

    if "contributor_id" in source and str(source["contributor_id"]).strip():
        inferred_role = _normalize_role(source.get("contributor_role", "prompt_author"))
        normalized[inferred_role] = str(source["contributor_id"]).strip()

    return ContributorAttribution(contributors_by_role=normalized)
