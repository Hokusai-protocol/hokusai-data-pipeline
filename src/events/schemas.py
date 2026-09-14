"""Event schemas for Hokusai ML Platform."""

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from src.utils.schema_validator import validate_json_schema
except ImportError:
    # Fallback for when running tests
    def validate_json_schema(data, schema):
        """Placeholder validation function."""
        return True


@dataclass
class ModelReadyToDeployMessage:
    """Message schema for model_ready_to_deploy events.

    This message is emitted when a model passes all baseline validations
    and is ready for token deployment.
    """

    # Required fields
    model_id: str  # Unique model identifier
    token_symbol: str  # Token symbol (e.g., "msg-ai")
    metric_name: str  # Performance metric name (e.g., "reply_rate")
    baseline_value: float  # Baseline performance value
    current_value: float  # Current model's performance value

    # Model metadata
    model_name: str  # Registered model name in MLflow
    model_version: str  # Model version
    mlflow_run_id: Optional[str] = None  # MLflow run ID when registration came from a run
    status: str = "registered"
    proposal_identifier: Optional[str] = None

    # Optional metadata
    improvement_percentage: Optional[float] = None
    contributor_address: Optional[str] = None
    experiment_name: Optional[str] = None
    tags: Optional[dict[str, str]] = None
    api_schema: Optional[dict[str, Any]] = None
    eval_spec: Optional[str] = None
    scorer_ref: Optional[str] = None
    primary_metric: Optional[str] = None
    benchmark_spec_id: Optional[str] = None

    # System fields (auto-populated)
    timestamp: Optional[datetime] = None
    message_version: str = "1.0"

    def __post_init__(self):
        """Post-initialization validation and calculations."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

        # Calculate improvement percentage if not provided
        if self.improvement_percentage is None and self.baseline_value > 0:
            improvement = self.current_value - self.baseline_value
            self.improvement_percentage = (improvement / self.baseline_value) * 100

        # Validate required fields
        if not self.model_id:
            raise ValueError("model_id is required")
        if not self.token_symbol:
            raise ValueError("token_symbol is required")
        if not isinstance(self.baseline_value, (int, float)):
            raise ValueError("baseline_value must be numeric")
        if not isinstance(self.current_value, (int, float)):
            raise ValueError("current_value must be numeric")
        if self.status not in {"registered"}:
            raise ValueError("status must be 'registered'")
        if self.proposal_identifier is None:
            self.proposal_identifier = self.token_symbol

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert datetime to ISO format
        if isinstance(data.get("timestamp"), datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        return data

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelReadyToDeployMessage":
        """Create instance from dictionary."""
        # Convert timestamp string back to datetime if present
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

    def validate(self) -> bool:
        """Validate message against schema."""
        schema = {
            "type": "object",
            "required": [
                "model_id",
                "token_symbol",
                "metric_name",
                "baseline_value",
                "current_value",
                "model_name",
                "model_version",
                "status",
            ],
            "properties": {
                "model_id": {"type": "string", "minLength": 1},
                "token_symbol": {
                    "type": "string",
                    "pattern": "^[a-z0-9-]+$",
                    "minLength": 1,
                    "maxLength": 64,
                },
                "metric_name": {"type": "string", "minLength": 1},
                "baseline_value": {"type": "number"},
                "current_value": {"type": "number"},
                "model_name": {"type": "string", "minLength": 1},
                "model_version": {"type": "string", "minLength": 1},
                "mlflow_run_id": {"type": ["string", "null"], "minLength": 1},
                "status": {"type": "string", "enum": ["registered"]},
                "proposal_identifier": {"type": ["string", "null"], "minLength": 1},
                "improvement_percentage": {"type": ["number", "null"]},
                "contributor_address": {
                    "type": ["string", "null"],
                    "pattern": "^0x[a-fA-F0-9]{40}$",
                },
                "experiment_name": {"type": ["string", "null"]},
                "tags": {"type": ["object", "null"], "additionalProperties": {"type": "string"}},
                "api_schema": {"type": ["object", "null"]},
                "eval_spec": {"type": ["string", "null"], "minLength": 1},
                "scorer_ref": {"type": ["string", "null"], "minLength": 1},
                "primary_metric": {"type": ["string", "null"], "minLength": 1},
                "benchmark_spec_id": {"type": ["string", "null"], "minLength": 1},
                "timestamp": {"type": "string", "format": "date-time"},
                "message_version": {"type": "string"},
            },
        }

        try:
            validate_json_schema(self.to_dict(), schema)
            return True
        except Exception:
            return False


@dataclass
class MessageEnvelope:
    """Generic envelope for all messages in the queue."""

    message_id: str
    message_type: str
    payload: dict[str, Any]
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 3

    def to_json(self) -> str:
        """Convert to JSON for queue storage."""
        data = {
            "message_id": self.message_id,
            "message_type": self.message_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "MessageEnvelope":
        """Create from JSON string."""
        data = json.loads(json_str)
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

    def should_retry(self) -> bool:
        """Check if message should be retried."""
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry count."""
        self.retry_count += 1


# ---------------------------------------------------------------------------
# MintRequest schemas (HOK-1276)
# Published to hokusai:mint_requests on DeltaOne acceptance.
# ---------------------------------------------------------------------------

MINT_REQUEST_SCHEMA_VERSION: Literal["1.0"] = "1.0"
MINT_REQUEST_MESSAGE_TYPE: Literal["mint_request"] = "mint_request"
_UINT256_MAX = 2**256 - 1
_ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_SHA256_HEX_RE = re.compile(r"^0x[0-9a-f]{64}$")
_ECDSA_SIG_RE = re.compile(r"^0x[0-9a-fA-F]{130}$")
_SHA256_HEX_PATTERN = r"^0x[0-9a-f]{64}$"
_ECDSA_SIG_PATTERN = r"^0x[0-9a-fA-F]{130}$"
Sha256Hex = Annotated[str, Field(pattern=_SHA256_HEX_PATTERN)]
AttesterSignatureHex = Annotated[str, Field(pattern=_ECDSA_SIG_PATTERN)]


class MintRequestContributor(BaseModel):
    """A single contributor's wallet address and allocation weight for a MintRequest."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    wallet_address: str = Field(
        ..., description="EIP-55 checksummed or lowercase 0x-prefixed Ethereum address"
    )
    weight_bps: int = Field(..., ge=1, le=10000, description="Allocation weight in basis points")
    submission_id: str | None = Field(default=None, alias="submissionId", min_length=1)
    contribution_batch_id: str | None = Field(
        default=None, alias="contributionBatchId", min_length=1
    )
    contributor_id: str | None = Field(default=None, alias="contributorId", min_length=1)
    recipient_kind: Literal["wallet", "escrow"] = Field(
        default="wallet",
        alias="recipientKind",
        description="Mint-time reward routing decision for this contributor",
    )

    @field_validator("wallet_address")
    @classmethod
    def _validate_wallet(cls, v: str) -> str:
        if not _ETH_ADDRESS_RE.match(v):
            raise ValueError(f"wallet_address must match 0x[a-fA-F0-9]{{40}}, got {v!r}")
        return v.lower()


class MintRequestEvaluation(BaseModel):
    """Evaluation scores and metadata embedded in a MintRequest."""

    model_config = ConfigDict(extra="forbid")

    metric_name: str = Field(..., min_length=1)
    metric_family: str = Field(..., min_length=1)

    # Scores in basis points
    baseline_score_bps: int = Field(..., ge=0, le=10000)
    new_score_bps: int = Field(..., ge=0, le=10000)

    # Cost fields in USDC micro-units (6 decimals)
    max_cost_usd_micro: int = Field(..., ge=0)
    actual_cost_usd_micro: int = Field(..., ge=0)

    # Statistical metadata (optional but recommended)
    sample_size_baseline: Optional[int] = Field(None, ge=0)
    sample_size_candidate: Optional[int] = Field(None, ge=0)
    ci_low_bps: Optional[int] = Field(None, ge=0, le=10000)
    ci_high_bps: Optional[int] = Field(None, ge=0, le=10000)
    p_value: Optional[float] = Field(None, ge=0.0, le=1.0)
    effect_size_bps: Optional[int] = Field(None, ge=0, le=10000)
    statistical_method: Optional[str] = Field(None, max_length=128)
    statistical_reason: Optional[str] = Field(None, max_length=1024)


class MintRequest(BaseModel):
    """MintRequest message published to hokusai:mint_requests on DeltaOne acceptance.

    All score and delta fields are in basis points (0-10000).
    Cost fields are in USDC micro-units (6 decimals).
    All SHA-256 hashes are lowercase 0x-prefixed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    # Envelope fields
    message_type: Literal["mint_request"] = MINT_REQUEST_MESSAGE_TYPE
    schema_version: Literal["1.0"] = MINT_REQUEST_SCHEMA_VERSION

    # Message identity
    message_id: str = Field(..., min_length=1, description="UUID or unique message identifier")
    timestamp: str = Field(..., min_length=1, description="ISO-8601 UTC timestamp")

    # Model and eval references
    model_id: str = Field(..., min_length=1)
    model_id_uint: str = Field(..., pattern=r"^[1-9]\d*$", description="uint256 as decimal string")
    eval_id: str = Field(..., min_length=1)

    # Cryptographic anchors
    benchmark_spec_id: str = Field(
        ..., min_length=1, description="Stable benchmark spec identifier"
    )
    dataset_hash: Sha256Hex = Field(..., description="Dataset anchor, 0x-prefixed 64-hex SHA-256")
    attestation_hash: Sha256Hex = Field(
        ..., description="SHA-256 of HEM payload, 0x-prefixed 64-hex"
    )
    idempotency_key: Sha256Hex = Field(
        ..., description="sha256(model_id_uint:attestation_hash), 0x-prefixed"
    )
    baseline_commitment: Sha256Hex = Field(
        ...,
        description=(
            "Canonical on-chain lineage head for the model, "
            "0x-prefixed 64-hex (sha256-merkle-v1)"
        ),
    )
    candidate_commitment: Sha256Hex = Field(
        ...,
        description=(
            "SHA-256 Merkle root of candidate model weights, "
            "0x-prefixed 64-hex (sha256-merkle-v1)"
        ),
    )
    attester_signatures: list[AttesterSignatureHex] = Field(
        ...,
        min_length=0,
        max_length=8,
        description=(
            "Attester ECDSA signatures over the canonical MintRequest typed data, "
            "ordered by ascending recovered signer address"
        ),
    )

    total_samples: int = Field(
        ...,
        alias="totalSamples",
        ge=1,
        description=(
            "Total sample count submitted to DeltaVerifier, "
            "derived from accepted candidate samples"
        ),
    )

    deadline: int = Field(
        ...,
        alias="deadline",
        ge=1,
        description=(
            "HOK-2170: unix timestamp past which the attester signature is no longer "
            "submittable (DeltaVerifier reverts SignatureExpired). Set to now + 5 days "
            "at attest-build time; bound into the EIP-712 digest."
        ),
    )

    # Evaluation payload
    evaluation: MintRequestEvaluation

    # Contributors — must sum to 10000 bps
    contributors: list[MintRequestContributor] = Field(..., min_length=1)

    @field_validator("model_id_uint")
    @classmethod
    def _validate_model_id_uint(cls, v: str) -> str:
        try:
            n = int(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"model_id_uint must be a decimal integer string, got {v!r}") from exc
        if n <= 0 or n > _UINT256_MAX:
            raise ValueError(f"model_id_uint {v!r} is outside uint256 range")
        return v

    @field_validator("attestation_hash", "idempotency_key", "dataset_hash")
    @classmethod
    def _validate_0x_sha256(cls, v: str) -> str:
        if not _SHA256_HEX_RE.match(v):
            raise ValueError(f"hash field must be 0x-prefixed lowercase 64-hex SHA-256, got {v!r}")
        return v

    @field_validator("baseline_commitment", "candidate_commitment")
    @classmethod
    def _validate_sha256(cls, v: str) -> str:
        if not _SHA256_HEX_RE.match(v):
            raise ValueError(f"commitment must be 0x-prefixed lowercase 64-hex SHA-256, got {v!r}")
        return v

    @field_validator("attester_signatures")
    @classmethod
    def _validate_attester_sigs(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            lowered = value.lower()
            if not _ECDSA_SIG_RE.match(value):
                raise ValueError(
                    "attester_signatures entries must be 0x-prefixed 130-hex "
                    f"(65 bytes), got {value!r}"
                )
            normalized.append(lowered)
        return normalized

    @model_validator(mode="after")
    def _validate_contributors_sum(self) -> "MintRequest":
        total = sum(c.weight_bps for c in self.contributors)
        if total != 10000:
            raise ValueError(f"contributors weight_bps must sum to 10000; got {total}")
        if len(self.contributors) > 100:
            raise ValueError("contributors list exceeds maximum of 100 entries")
        candidate_samples = self.evaluation.sample_size_candidate
        if (
            candidate_samples is not None
            and candidate_samples > 0
            and self.total_samples != candidate_samples
        ):
            raise ValueError(
                "totalSamples must match evaluation.sample_size_candidate "
                "when candidate sample size is present"
            )
        return self
