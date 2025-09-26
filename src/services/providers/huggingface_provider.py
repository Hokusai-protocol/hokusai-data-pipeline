"""HuggingFace Inference Endpoints provider implementation."""

import hashlib
import logging
import time
from typing import Any

import httpx

from .base_provider import BaseProvider, DeploymentResult, PredictionResult, ProviderConfig

logger = logging.getLogger(__name__)


class HuggingFaceProvider(BaseProvider):
    """HuggingFace Inference Endpoints provider for model deployment and serving."""

    def __init__(self, config: ProviderConfig):
        """Initialize HuggingFace provider.

        Args:
        ----
            config: Provider configuration

        """
        super().__init__(config)
        self.api_key = config.credentials.get("api_key")
        self.base_url = "https://api.huggingface.co"

        if not self.api_key:
            raise ValueError("HuggingFace API key is required")

    def validate_config(self, config: ProviderConfig) -> bool:
        """Validate HuggingFace provider configuration.

        Args:
        ----
            config: Configuration to validate

        Returns:
        -------
            True if configuration is valid, False otherwise

        """
        # Check for required API key
        if not config.credentials.get("api_key"):
            logger.error("HuggingFace API key is missing from configuration")
            return False

        # Validate supported instance types
        valid_instance_types = {"cpu", "gpu", "gpu-large"}
        for instance_type in config.supported_instance_types:
            if instance_type not in valid_instance_types:
                logger.error(f"Invalid instance type: {instance_type}")
                return False

        return True

    async def deploy_model(
        self, model_id: str, model_uri: str, instance_type: str = "cpu", **kwargs
    ) -> DeploymentResult:
        """Deploy a model to HuggingFace Inference Endpoints.

        Args:
        ----
            model_id: Unique identifier for the model
            model_uri: HuggingFace model repository (e.g., "microsoft/DialoGPT-medium")
            instance_type: Type of compute instance (cpu, gpu, gpu-large)
            **kwargs: Additional parameters

        Returns:
        -------
            DeploymentResult with deployment details

        """
        try:
            # Generate unique endpoint name
            endpoint_name = self._generate_endpoint_name(model_id)

            # Create inference endpoint payload
            payload = self._create_inference_endpoint_payload(
                model_uri=model_uri,
                endpoint_name=endpoint_name,
                instance_type=instance_type,
                **kwargs,
            )

            headers = self._get_headers()

            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/inference/endpoints", json=payload, headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    return DeploymentResult(
                        success=True,
                        endpoint_url=data.get("url"),
                        provider_model_id=data.get("name"),
                        metadata={
                            "instance_type": instance_type,
                            "repository": model_uri,
                            "status": data.get("status", {}),
                        },
                    )
                else:
                    error_data = response.json()
                    error_message = error_data.get("error", f"HTTP {response.status_code}")
                    return DeploymentResult(
                        success=False, error_message=f"Deployment failed: {error_message}"
                    )

        except httpx.TimeoutException as e:
            return DeploymentResult(success=False, error_message=f"Request timeout: {str(e)}")
        except Exception as e:
            return DeploymentResult(success=False, error_message=f"Deployment error: {str(e)}")

    async def undeploy_model(self, provider_model_id: str) -> bool:
        """Remove a deployed model from HuggingFace Inference Endpoints.

        Args:
        ----
            provider_model_id: HuggingFace endpoint name

        Returns:
        -------
            True if successful, False otherwise

        """
        try:
            headers = self._get_headers()

            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.delete(
                    f"{self.base_url}/inference/endpoints/{provider_model_id}", headers=headers
                )

                return response.status_code in (200, 204)

        except Exception as e:
            logger.error(f"Error undeploying model {provider_model_id}: {str(e)}")
            return False

    async def predict(
        self, endpoint_url: str, inputs: dict[str, Any], **kwargs
    ) -> PredictionResult:
        """Make a prediction using a deployed model.

        Args:
        ----
            endpoint_url: URL of the deployed model endpoint
            inputs: Input data for prediction
            **kwargs: Additional parameters

        Returns:
        -------
            PredictionResult with prediction outputs

        """
        start_time = time.time()

        try:
            headers = self._get_headers()

            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(endpoint_url, json=inputs, headers=headers)

                response_time_ms = int((time.time() - start_time) * 1000)

                if response.status_code == 200:
                    predictions = response.json()
                    return PredictionResult(
                        success=True,
                        predictions=predictions,
                        response_time_ms=response_time_ms,
                        metadata={"endpoint_url": endpoint_url},
                    )
                else:
                    error_data = response.json()
                    error_message = error_data.get("error", f"HTTP {response.status_code}")
                    return PredictionResult(
                        success=False,
                        response_time_ms=response_time_ms,
                        error_message=f"Prediction failed: {error_message}",
                    )

        except httpx.TimeoutException as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return PredictionResult(
                success=False,
                response_time_ms=response_time_ms,
                error_message=f"Request timeout: {str(e)}",
            )
        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return PredictionResult(
                success=False,
                response_time_ms=response_time_ms,
                error_message=f"Prediction error: {str(e)}",
            )

    async def get_deployment_status(self, provider_model_id: str) -> str:
        """Get the current status of a deployed model.

        Args:
        ----
            provider_model_id: HuggingFace endpoint name

        Returns:
        -------
            Status string (running, deploying, failed, stopped, not_found)

        """
        try:
            headers = self._get_headers()

            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/inference/endpoints/{provider_model_id}", headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    hf_status = data.get("status", {}).get("state", "unknown")
                    return self._map_status_to_standard(hf_status)
                elif response.status_code == 404:
                    return "not_found"
                else:
                    logger.error(f"Error getting status: HTTP {response.status_code}")
                    return "unknown"

        except Exception as e:
            logger.error(f"Error getting deployment status for {provider_model_id}: {str(e)}")
            return "unknown"

    def _generate_endpoint_name(self, model_id: str) -> str:
        """Generate a unique endpoint name for HuggingFace.

        Args:
        ----
            model_id: Model identifier

        Returns:
        -------
            Unique endpoint name (max 32 characters)

        """
        # Create a hash of the model_id for uniqueness
        model_hash = hashlib.md5(model_id.encode()).hexdigest()[:8]
        endpoint_name = f"hokusai-model-{model_hash}"

        # Ensure it's within HuggingFace's 32-character limit
        return endpoint_name[:32]

    def _map_status_to_standard(self, hf_status: str) -> str:
        """Map HuggingFace status to standard status.

        Args:
        ----
            hf_status: HuggingFace status string

        Returns:
        -------
            Standard status string

        """
        status_mapping = {
            "Running": "running",
            "Pending": "deploying",
            "Building": "deploying",
            "Failed": "failed",
            "Stopped": "stopped",
            "Paused": "stopped",
        }
        return status_mapping.get(hf_status, "unknown")

    def _create_inference_endpoint_payload(
        self, model_uri: str, endpoint_name: str, instance_type: str, **kwargs
    ) -> dict[str, Any]:
        """Create the payload for creating an inference endpoint.

        Args:
        ----
            model_uri: HuggingFace model repository
            endpoint_name: Name for the endpoint
            instance_type: Type of compute instance
            **kwargs: Additional parameters

        Returns:
        -------
            Payload dictionary

        """
        return {
            "repository": model_uri,
            "name": endpoint_name,
            "accelerator": instance_type,
            "instance_size": self._get_instance_size(instance_type),
            "instance_type": "public",  # or "private" for dedicated instances
            "region": kwargs.get("region", "us-east-1"),
            "vendor": kwargs.get("vendor", "aws"),
            "account_id": kwargs.get("account_id"),
            "task": kwargs.get("task", "text-generation"),
        }

    def _get_instance_size(self, instance_type: str) -> str:
        """Map instance type to HuggingFace instance size.

        Args:
        ----
            instance_type: Instance type (cpu, gpu, gpu-large)

        Returns:
        -------
            HuggingFace instance size

        """
        size_mapping = {
            "cpu": "small",
            "gpu": "medium",
            "gpu-large": "large",
        }
        return size_mapping.get(instance_type, "small")

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests.

        Returns
        -------
            Headers dictionary

        """
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
