"""Deployment service for managing model deployments across providers."""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..database.deployed_models import DeployedModel, DeployedModelStatus
from .providers.base_provider import ProviderConfig
from .providers.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


class DeploymentService:
    """Service for managing model deployments and orchestrating providers."""

    def __init__(self, db_session: Session, provider_registry: Optional[ProviderRegistry] = None):
        """Initialize deployment service.

        Args:
        ----
            db_session: Database session for persistence
            provider_registry: Registry of available providers

        """
        self.db_session = db_session
        self.provider_registry = provider_registry or ProviderRegistry()

    async def deploy_model(
        self,
        model_id: str,
        model_uri: str,
        provider_name: str,
        provider_config: ProviderConfig,
        instance_type: str = "cpu",
        **kwargs,
    ) -> dict[str, Any]:
        """Deploy a model to a provider.

        Args:
        ----
            model_id: MLFlow model ID
            model_uri: URI to model artifacts
            provider_name: Name of the provider to deploy to
            provider_config: Configuration for the provider
            instance_type: Type of compute instance
            **kwargs: Additional deployment parameters

        Returns:
        -------
            Dictionary with deployment results

        """
        try:
            # Create initial database record
            deployed_model = DeployedModel(
                model_id=model_id,
                provider=provider_name,
                status=DeployedModelStatus.PENDING,
                instance_type=instance_type,
            )
            self.db_session.add(deployed_model)
            self.db_session.commit()

            # Get provider instance
            provider = self.provider_registry.get_provider(provider_name, provider_config)

            # Attempt deployment
            deployment_result = await provider.deploy_model(
                model_id=model_id, model_uri=model_uri, instance_type=instance_type, **kwargs
            )

            # Update database record based on deployment result
            if deployment_result.success:
                deployed_model.status = DeployedModelStatus.DEPLOYED
                deployed_model.endpoint_url = deployment_result.endpoint_url
                deployed_model.provider_model_id = deployment_result.provider_model_id
                deployed_model.deployment_metadata = deployment_result.metadata
            else:
                deployed_model.status = DeployedModelStatus.FAILED
                deployed_model.error_message = deployment_result.error_message

            self.db_session.commit()

            # Return result
            if deployment_result.success:
                return {
                    "success": True,
                    "deployed_model_id": str(deployed_model.id),
                    "endpoint_url": deployment_result.endpoint_url,
                    "provider_model_id": deployment_result.provider_model_id,
                    "status": deployed_model.status.value,
                    "metadata": deployment_result.metadata,
                }
            else:
                return {
                    "success": False,
                    "deployed_model_id": str(deployed_model.id),
                    "error_message": deployment_result.error_message,
                    "status": deployed_model.status.value,
                }

        except Exception as e:
            logger.error(f"Error deploying model {model_id}: {str(e)}")

            # Update database record with error if it exists
            try:
                if "deployed_model" in locals():
                    deployed_model.status = DeployedModelStatus.FAILED
                    deployed_model.error_message = str(e)
                    self.db_session.commit()
                    return {
                        "success": False,
                        "deployed_model_id": str(deployed_model.id),
                        "error_message": str(e),
                        "status": deployed_model.status.value,
                    }
            except:
                pass

            return {"success": False, "error_message": str(e)}

    async def undeploy_model(
        self, deployed_model_id: str, provider_configs: dict[str, ProviderConfig]
    ) -> dict[str, Any]:
        """Remove a deployed model.

        Args:
        ----
            deployed_model_id: UUID of the deployed model record
            provider_configs: Dictionary of provider configurations

        Returns:
        -------
            Dictionary with undeployment results

        """
        try:
            # Find deployed model record
            deployed_model = (
                self.db_session.query(DeployedModel).filter_by(id=deployed_model_id).first()
            )

            if not deployed_model:
                return {
                    "success": False,
                    "error_message": f"Deployed model {deployed_model_id} not found",
                }

            # Get provider configuration
            provider_config = provider_configs.get(deployed_model.provider)
            if not provider_config:
                return {
                    "success": False,
                    "error_message": f"No configuration found for provider {deployed_model.provider}",
                }

            # Get provider instance
            provider = self.provider_registry.get_provider(deployed_model.provider, provider_config)

            # Attempt undeployment
            success = await provider.undeploy_model(deployed_model.provider_model_id)

            if success:
                deployed_model.status = DeployedModelStatus.STOPPED
                self.db_session.commit()

                return {
                    "success": True,
                    "message": f"Model {deployed_model_id} undeployed successfully",
                }
            else:
                return {
                    "success": False,
                    "error_message": f"Failed to undeploy model from provider {deployed_model.provider}",
                }

        except Exception as e:
            logger.error(f"Error undeploying model {deployed_model_id}: {str(e)}")
            return {"success": False, "error_message": str(e)}

    async def get_deployment_status(
        self, deployed_model_id: str, provider_configs: dict[str, ProviderConfig]
    ) -> dict[str, Any]:
        """Get the current status of a deployed model.

        Args:
        ----
            deployed_model_id: UUID of the deployed model record
            provider_configs: Dictionary of provider configurations

        Returns:
        -------
            Dictionary with status information

        """
        try:
            # Find deployed model record
            deployed_model = (
                self.db_session.query(DeployedModel).filter_by(id=deployed_model_id).first()
            )

            if not deployed_model:
                return {
                    "success": False,
                    "error_message": f"Deployed model {deployed_model_id} not found",
                }

            database_status = deployed_model.status.value

            # If model is not deployed, return database status only
            if deployed_model.status != DeployedModelStatus.DEPLOYED:
                return {
                    "success": True,
                    "status": database_status,
                    "database_status": database_status,
                    "provider_status": None,
                }

            # Get provider configuration
            provider_config = provider_configs.get(deployed_model.provider)
            if not provider_config:
                return {
                    "success": False,
                    "error_message": f"No configuration found for provider {deployed_model.provider}",
                }

            # Get provider instance and check status
            provider = self.provider_registry.get_provider(deployed_model.provider, provider_config)

            provider_status = await provider.get_deployment_status(deployed_model.provider_model_id)

            return {
                "success": True,
                "status": provider_status,
                "database_status": database_status,
                "provider_status": provider_status,
            }

        except Exception as e:
            logger.error(f"Error getting deployment status for {deployed_model_id}: {str(e)}")
            return {"success": False, "error_message": str(e)}

    async def predict(
        self,
        deployed_model_id: str,
        inputs: dict[str, Any],
        provider_configs: dict[str, ProviderConfig],
        **kwargs,
    ) -> dict[str, Any]:
        """Make a prediction using a deployed model.

        Args:
        ----
            deployed_model_id: UUID of the deployed model record
            inputs: Input data for prediction
            provider_configs: Dictionary of provider configurations
            **kwargs: Additional prediction parameters

        Returns:
        -------
            Dictionary with prediction results

        """
        try:
            # Find deployed model record
            deployed_model = (
                self.db_session.query(DeployedModel).filter_by(id=deployed_model_id).first()
            )

            if not deployed_model:
                return {
                    "success": False,
                    "error_message": f"Deployed model {deployed_model_id} not found",
                }

            # Check if model is deployed
            if deployed_model.status != DeployedModelStatus.DEPLOYED:
                return {
                    "success": False,
                    "error_message": f"Model is not deployed (status: {deployed_model.status.value})",
                }

            # Get provider configuration
            provider_config = provider_configs.get(deployed_model.provider)
            if not provider_config:
                return {
                    "success": False,
                    "error_message": f"No configuration found for provider {deployed_model.provider}",
                }

            # Get provider instance
            provider = self.provider_registry.get_provider(deployed_model.provider, provider_config)

            # Make prediction
            prediction_result = await provider.predict(
                endpoint_url=deployed_model.endpoint_url, inputs=inputs, **kwargs
            )

            return {
                "success": prediction_result.success,
                "predictions": prediction_result.predictions,
                "response_time_ms": prediction_result.response_time_ms,
                "error_message": prediction_result.error_message,
                "metadata": prediction_result.metadata,
            }

        except Exception as e:
            logger.error(f"Error making prediction for {deployed_model_id}: {str(e)}")
            return {"success": False, "error_message": str(e)}

    def list_deployed_models(
        self, status: Optional[DeployedModelStatus] = None, provider: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """List deployed models with optional filtering.

        Args:
        ----
            status: Filter by deployment status
            provider: Filter by provider name

        Returns:
        -------
            List of deployed model dictionaries

        """
        try:
            query = self.db_session.query(DeployedModel)

            # Apply filters
            if status:
                query = query.filter_by(status=status)
            if provider:
                query = query.filter_by(provider=provider)

            deployed_models = query.all()
            return [model.to_dict() for model in deployed_models]

        except Exception as e:
            logger.error(f"Error listing deployed models: {str(e)}")
            return []

    def get_deployed_model_info(self, deployed_model_id: str) -> Optional[dict[str, Any]]:
        """Get information about a specific deployed model.

        Args:
        ----
            deployed_model_id: UUID of the deployed model record

        Returns:
        -------
            Deployed model dictionary or None if not found

        """
        try:
            deployed_model = (
                self.db_session.query(DeployedModel).filter_by(id=deployed_model_id).first()
            )

            if deployed_model:
                return deployed_model.to_dict()
            else:
                return None

        except Exception as e:
            logger.error(f"Error getting deployed model info for {deployed_model_id}: {str(e)}")
            return None
