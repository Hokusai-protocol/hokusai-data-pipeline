"""Provider configuration management."""

import os
from typing import Dict, Optional

from ..services.providers.base_provider import ProviderConfig


class ProviderConfigManager:
    """Manages provider configurations from environment variables."""

    @staticmethod
    def get_huggingface_config() -> Optional[ProviderConfig]:
        """Get HuggingFace provider configuration.

        Returns
        -------
            ProviderConfig if API key is available, None otherwise

        """
        api_key = os.getenv("HUGGINGFACE_API_KEY")
        if not api_key:
            return None

        return ProviderConfig(
            provider_name="huggingface",
            credentials={"api_key": api_key},
            default_instance_type=os.getenv("HUGGINGFACE_DEFAULT_INSTANCE", "cpu"),
            timeout=float(os.getenv("HUGGINGFACE_TIMEOUT", "30.0")),
            max_retries=int(os.getenv("HUGGINGFACE_MAX_RETRIES", "3")),
        )

    @staticmethod
    def get_sagemaker_config() -> Optional[ProviderConfig]:
        """Get AWS SageMaker provider configuration.

        Returns
        -------
            ProviderConfig if AWS credentials are available, None otherwise

        """
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        if not access_key or not secret_key:
            return None

        return ProviderConfig(
            provider_name="sagemaker",
            credentials={
                "access_key": access_key,
                "secret_key": secret_key,
                "region": os.getenv("AWS_REGION", "us-east-1"),
            },
            default_instance_type=os.getenv("SAGEMAKER_DEFAULT_INSTANCE", "ml.t2.medium"),
            timeout=float(os.getenv("SAGEMAKER_TIMEOUT", "60.0")),
            max_retries=int(os.getenv("SAGEMAKER_MAX_RETRIES", "3")),
        )

    @classmethod
    def get_all_configs(cls) -> Dict[str, ProviderConfig]:
        """Get all available provider configurations.

        Returns
        -------
            Dictionary of provider name to configuration

        """
        configs = {}

        # Add HuggingFace if available
        hf_config = cls.get_huggingface_config()
        if hf_config:
            configs["huggingface"] = hf_config

        # Add SageMaker if available
        sm_config = cls.get_sagemaker_config()
        if sm_config:
            configs["sagemaker"] = sm_config

        if not configs:
            raise ValueError(
                "No provider configurations found. "
                "Please set HUGGINGFACE_API_KEY or AWS credentials in environment."
            )

        return configs
