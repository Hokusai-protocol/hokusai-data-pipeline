"""Base provider interface for model deployment and serving."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ProviderConfig:
    """Configuration for a model serving provider."""

    provider_name: str
    credentials: dict[str, Any]
    default_instance_type: str = "cpu"
    supported_instance_types: list[str] = field(default_factory=lambda: ["cpu"])
    timeout: float = 30.0
    max_retries: int = 3


@dataclass
class DeploymentResult:
    """Result of a model deployment operation."""

    success: bool
    endpoint_url: Optional[str] = None
    provider_model_id: Optional[str] = None
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictionResult:
    """Result of a model prediction operation."""

    success: bool
    predictions: list[dict[str, Any]] = field(default_factory=list)
    response_time_ms: int = 0
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """Abstract base class for model serving providers."""

    def __init__(self, config: ProviderConfig):
        """Initialize the provider with configuration.

        Args:
        ----
            config: Provider configuration

        """
        self.config = config

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return self.config.provider_name

    @abstractmethod
    async def deploy_model(
        self, model_id: str, model_uri: str, instance_type: str = "cpu", **kwargs
    ) -> DeploymentResult:
        """Deploy a model to the provider's infrastructure.

        Args:
        ----
            model_id: Unique identifier for the model
            model_uri: URI where the model artifacts can be found
            instance_type: Type of compute instance (cpu, gpu, etc.)
            **kwargs: Additional provider-specific parameters

        Returns:
        -------
            DeploymentResult with deployment details

        """
        pass

    @abstractmethod
    async def undeploy_model(self, provider_model_id: str) -> bool:
        """Remove a deployed model from the provider's infrastructure.

        Args:
        ----
            provider_model_id: Provider-specific model identifier

        Returns:
        -------
            True if successful, False otherwise

        """
        pass

    @abstractmethod
    async def predict(
        self, endpoint_url: str, inputs: dict[str, Any], **kwargs
    ) -> PredictionResult:
        """Make a prediction using a deployed model.

        Args:
        ----
            endpoint_url: URL of the deployed model endpoint
            inputs: Input data for prediction
            **kwargs: Additional provider-specific parameters

        Returns:
        -------
            PredictionResult with prediction outputs

        """
        pass

    @abstractmethod
    async def get_deployment_status(self, provider_model_id: str) -> str:
        """Get the current status of a deployed model.

        Args:
        ----
            provider_model_id: Provider-specific model identifier

        Returns:
        -------
            Status string (e.g., "running", "stopped", "failed")

        """
        pass

    @abstractmethod
    def validate_config(self, config: ProviderConfig) -> bool:
        """Validate the provider configuration.

        Args:
        ----
            config: Configuration to validate

        Returns:
        -------
            True if configuration is valid, False otherwise

        """
        pass
