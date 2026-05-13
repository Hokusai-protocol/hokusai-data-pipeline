"""Pydantic models for token mint hook input/output contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TokenMintRequest(BaseModel):
    """Input payload for a token mint request."""

    model_id: str = Field(..., min_length=1, description="Model identifier")
    token_id: str = Field(..., min_length=1, description="Token identifier")
    delta_value: float = Field(..., ge=0, description="Value delta used for reward minting")
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        description="Optional idempotency key for deduplication in downstream mint service",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenMintVestingDetails(BaseModel):
    """Optional vesting details returned by downstream mint services."""

    liquid_amount: str | None = None
    vested_amount: str | None = None
    vault_address: str | None = None
    schedule_id: str | None = None
    claimable_amount: str | None = None
    vesting_config: dict[str, Any] | None = None

    @field_validator("liquid_amount", "vested_amount", "claimable_amount", mode="before")
    @classmethod
    def _validate_amount_fields(cls: type[TokenMintVestingDetails], value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Amount fields must be strings in base units")
        if not value:
            raise ValueError("Amount fields must not be empty")
        return value

    def payload(self: TokenMintVestingDetails) -> dict[str, Any]:
        """Return only populated vesting fields."""
        return {key: value for key, value in self.model_dump().items() if value is not None}

    def has_values(self: TokenMintVestingDetails) -> bool:
        """Whether any vesting field was provided."""
        return bool(self.payload())


class TokenMintResult(BaseModel):
    """Result payload returned by the token mint hook."""

    _FLAT_VESTING_FIELDS: ClassVar[tuple[str, ...]] = (
        "liquid_amount",
        "vested_amount",
        "vault_address",
        "schedule_id",
        "claimable_amount",
        "vesting_config",
    )

    status: Literal["success", "failed", "skipped", "dry_run"]
    audit_ref: str = Field(..., min_length=1, description="Audit UUID for this mint invocation")
    timestamp: datetime
    error: str | None = None
    vesting: TokenMintVestingDetails | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_vesting_fields(cls: type[TokenMintResult], value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        data = dict(value)
        nested_vesting = data.get("vesting")
        flat_vesting = {
            field_name: data[field_name]
            for field_name in cls._FLAT_VESTING_FIELDS
            if field_name in data
        }

        if nested_vesting is None and not flat_vesting:
            return data

        combined_vesting: dict[str, Any] = {}
        if isinstance(nested_vesting, dict):
            combined_vesting.update(nested_vesting)
        elif nested_vesting is not None:
            combined_vesting = nested_vesting
        if isinstance(combined_vesting, dict):
            combined_vesting.update(flat_vesting)
            data["vesting"] = combined_vesting

        return data

    @model_validator(mode="after")
    def _drop_empty_vesting(self: TokenMintResult) -> TokenMintResult:
        if self.vesting is not None and not self.vesting.has_values():
            self.vesting = None
        return self

    def has_vesting_details(self: TokenMintResult) -> bool:
        """Whether the result includes any vesting details."""
        return self.vesting is not None and self.vesting.has_values()

    def vesting_payload(self: TokenMintResult) -> dict[str, Any] | None:
        """Return the vesting payload only when vesting details are present."""
        if not self.has_vesting_details():
            return None
        return self.vesting.payload()
