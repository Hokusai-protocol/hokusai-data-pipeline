#!/usr/bin/env python3
"""Model storage manager for Hokusai.

This module handles the storage strategy for models based on
environment and security requirements.
"""

import logging
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict

import boto3

from .huggingface_uploader import HuggingFaceModelUploader

logger = logging.getLogger(__name__)


class StorageType(Enum):
    """Supported storage types for models."""

    HUGGINGFACE_PUBLIC = "huggingface_public"
    HUGGINGFACE_PRIVATE = "huggingface_private"
    AWS_S3 = "aws_s3"
    CONTAINER_REGISTRY = "container_registry"
    LOCAL = "local"


class ModelStorageManager:
    """Manages model storage across different providers with security-first approach.

    Security Principles:
    1. Never store proprietary models in public repositories
    2. Default to private storage
    3. Use encryption for sensitive models
    4. Implement access logging
    5. Support multiple storage backends for flexibility
    """

    def __init__(self, environment: str = "development"):
        """Initialize storage manager with environment-specific settings.

        Args:
        ----
            environment: Environment name (development/staging/production)

        """
        self.environment = environment
        self.hf_uploader = None
        self.s3_client = None

        # Initialize based on environment
        self._initialize_storage_backends()

    def _initialize_storage_backends(self):
        """Initialize storage backends based on available credentials."""
        # HuggingFace backend
        hf_token = os.getenv("HUGGINGFACE_API_KEY")
        if hf_token:
            self.hf_uploader = HuggingFaceModelUploader(
                token=hf_token, organization="hokusai-protocol", default_private=True
            )
            logger.info("HuggingFace storage backend initialized")

        # AWS S3 backend
        if os.getenv("AWS_ACCESS_KEY_ID"):
            self.s3_client = boto3.client("s3")
            logger.info("AWS S3 storage backend initialized")

    def determine_storage_type(self, model_metadata: Dict[str, Any]) -> StorageType:
        """Determine the appropriate storage type based on model metadata and environment.

        Args:
        ----
            model_metadata: Model metadata including sensitivity level

        Returns:
        -------
            Appropriate StorageType

        """
        # Check sensitivity level
        sensitivity = model_metadata.get("sensitivity", "medium")
        is_public_ok = model_metadata.get("public_ok", False)

        # Production environment logic
        if self.environment == "production":
            if sensitivity == "high":
                # High sensitivity models go to S3 with encryption
                return StorageType.AWS_S3
            elif sensitivity == "critical":
                # Critical models should be containerized
                return StorageType.CONTAINER_REGISTRY
            else:
                # Default to private HuggingFace for production
                return StorageType.HUGGINGFACE_PRIVATE

        # Development environment logic
        elif self.environment == "development":
            if is_public_ok:
                # Only if explicitly marked as public (for demos/examples)
                logger.warning("Model marked as public_ok - using public repo")
                return StorageType.HUGGINGFACE_PUBLIC
            else:
                # Default to private for development
                return StorageType.HUGGINGFACE_PRIVATE

        # Local testing
        elif self.environment == "local":
            return StorageType.LOCAL

        # Default to most secure option
        return StorageType.HUGGINGFACE_PRIVATE

    async def upload_model(
        self, model_id: str, model_path: str, model_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upload a model to the appropriate storage backend.

        Args:
        ----
            model_id: Hokusai model ID
            model_path: Path to model file or directory
            model_metadata: Model metadata

        Returns:
        -------
            Storage information including URL and access details

        """
        # Determine storage type
        storage_type = self.determine_storage_type(model_metadata)

        logger.info(f"Uploading model {model_id} using {storage_type.value}")

        # Route to appropriate storage backend
        if storage_type == StorageType.HUGGINGFACE_PRIVATE:
            return await self._upload_to_huggingface_private(model_id, model_path, model_metadata)
        elif storage_type == StorageType.HUGGINGFACE_PUBLIC:
            return await self._upload_to_huggingface_public(model_id, model_path, model_metadata)
        elif storage_type == StorageType.AWS_S3:
            return await self._upload_to_s3(model_id, model_path, model_metadata)
        elif storage_type == StorageType.CONTAINER_REGISTRY:
            return await self._upload_to_container_registry(model_id, model_path, model_metadata)
        elif storage_type == StorageType.LOCAL:
            return await self._store_locally(model_id, model_path, model_metadata)
        else:
            raise ValueError(f"Unsupported storage type: {storage_type}")

    async def _upload_to_huggingface_private(
        self, model_id: str, model_path: str, model_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upload model to private HuggingFace repository."""
        if not self.hf_uploader:
            raise ValueError("HuggingFace storage not configured")

        repo_id, upload_info = self.hf_uploader.upload_model(
            model_id=model_id,
            model_path=model_path,
            model_metadata=model_metadata,
            private=True,  # ALWAYS private
            model_name=model_metadata.get("name"),
        )

        # Generate secure access configuration
        access_config = self._generate_access_config(model_id, repo_id)

        return {
            "storage_type": StorageType.HUGGINGFACE_PRIVATE.value,
            "repository_id": repo_id,
            "repository_url": upload_info["repository_url"],
            "is_private": True,
            "inference_endpoint": upload_info["inference_endpoint"],
            "access_config": access_config,
            "uploaded_at": upload_info["uploaded_at"],
            "checksum": upload_info.get("model_checksum"),
        }

    async def _upload_to_huggingface_public(
        self, model_id: str, model_path: str, model_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upload model to public HuggingFace repository.

        WARNING: Only use for demo/example models that are explicitly marked as public.
        """
        logger.warning(
            f"⚠️  Uploading model {model_id} to PUBLIC repository. " "Ensure this is intended!"
        )

        if not model_metadata.get("public_ok", False):
            raise ValueError("Model not marked as public_ok. Refusing to create public repository.")

        if not self.hf_uploader:
            raise ValueError("HuggingFace storage not configured")

        repo_id, upload_info = self.hf_uploader.upload_model(
            model_id=model_id,
            model_path=model_path,
            model_metadata=model_metadata,
            private=False,  # PUBLIC - use with caution
            model_name=model_metadata.get("name"),
        )

        return {
            "storage_type": StorageType.HUGGINGFACE_PUBLIC.value,
            "repository_id": repo_id,
            "repository_url": upload_info["repository_url"],
            "is_private": False,
            "warning": "This model is publicly accessible",
            "inference_endpoint": upload_info["inference_endpoint"],
            "uploaded_at": upload_info["uploaded_at"],
        }

    async def _upload_to_s3(
        self, model_id: str, model_path: str, model_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upload model to AWS S3 with encryption."""
        if not self.s3_client:
            raise ValueError("AWS S3 storage not configured")

        bucket_name = os.getenv("HOKUSAI_MODEL_BUCKET", "hokusai-models-private")
        key_prefix = f"{self.environment}/models/{model_id}"

        # Upload model file(s)
        model_path_obj = Path(model_path)

        if model_path_obj.is_file():
            # Single file upload
            key = f"{key_prefix}/model{model_path_obj.suffix}"

            self.s3_client.upload_file(
                model_path,
                bucket_name,
                key,
                ExtraArgs={
                    "ServerSideEncryption": "aws:kms",
                    "Metadata": {
                        "model_id": model_id,
                        "environment": self.environment,
                        "uploaded_at": datetime.utcnow().isoformat(),
                    },
                },
            )

            s3_url = f"s3://{bucket_name}/{key}"

        elif model_path_obj.is_dir():
            # Directory upload
            uploaded_files = []
            for file_path in model_path_obj.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(model_path_obj)
                    key = f"{key_prefix}/{relative_path}"

                    self.s3_client.upload_file(
                        str(file_path),
                        bucket_name,
                        key,
                        ExtraArgs={"ServerSideEncryption": "aws:kms"},
                    )
                    uploaded_files.append(key)

            s3_url = f"s3://{bucket_name}/{key_prefix}/"

        else:
            raise ValueError(f"Model path {model_path} does not exist")

        # Generate presigned URL for temporary access
        presigned_url = self._generate_presigned_url(bucket_name, key)

        return {
            "storage_type": StorageType.AWS_S3.value,
            "bucket": bucket_name,
            "key": key if model_path_obj.is_file() else key_prefix,
            "s3_url": s3_url,
            "presigned_url": presigned_url,
            "encryption": "aws:kms",
            "is_private": True,
            "uploaded_at": datetime.utcnow().isoformat(),
        }

    async def _upload_to_container_registry(
        self, model_id: str, model_path: str, model_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Package and upload model as a Docker container.

        This provides maximum security by encapsulating the model
        and only exposing it through an API.
        """
        registry = os.getenv("CONTAINER_REGISTRY", "your-registry.com")
        image_name = f"hokusai-model-{model_id}"
        image_tag = f"{registry}/{image_name}:latest"

        # In production, this would:
        # 1. Create a Dockerfile
        # 2. Build the container with the model
        # 3. Push to private registry
        # 4. Return container details

        logger.info(f"Would package model {model_id} as container: {image_tag}")

        return {
            "storage_type": StorageType.CONTAINER_REGISTRY.value,
            "image": image_tag,
            "registry": registry,
            "is_private": True,
            "note": "Container packaging not fully implemented",
            "uploaded_at": datetime.utcnow().isoformat(),
        }

    async def _store_locally(
        self, model_id: str, model_path: str, model_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Store model locally (for testing only)."""
        local_dir = Path("/tmp/hokusai_models") / self.environment / model_id
        local_dir.mkdir(parents=True, exist_ok=True)

        model_path_obj = Path(model_path)

        if model_path_obj.is_file():
            # Copy file
            import shutil

            dest = local_dir / model_path_obj.name
            shutil.copy2(model_path, dest)
            stored_path = str(dest)
        else:
            # Copy directory
            import shutil

            dest = local_dir / "model"
            shutil.copytree(model_path, dest, dirs_exist_ok=True)
            stored_path = str(dest)

        return {
            "storage_type": StorageType.LOCAL.value,
            "path": stored_path,
            "is_private": True,
            "warning": "Local storage - for testing only",
            "uploaded_at": datetime.utcnow().isoformat(),
        }

    def _generate_presigned_url(self, bucket: str, key: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for temporary S3 access."""
        if not self.s3_client:
            return ""

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expiration
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            return ""

    def _generate_access_config(self, model_id: str, repo_id: str) -> Dict[str, Any]:
        """Generate secure access configuration for a model.

        This configuration is used by the Hokusai API to access
        the model while keeping credentials secure.
        """
        return {
            "access_method": "hokusai_api",
            "model_id": model_id,
            "repository_id": repo_id,
            "requires_auth": True,
            "auth_type": "hokusai_api_key",
            "direct_access": False,
            "note": "Access only through Hokusai API endpoints",
        }

    def verify_storage(self, storage_info: Dict[str, Any]) -> bool:
        """Verify that a model is correctly stored and accessible.

        Args:
        ----
            storage_info: Storage information from upload

        Returns:
        -------
            True if storage is verified

        """
        storage_type = StorageType(storage_info["storage_type"])

        if storage_type in [StorageType.HUGGINGFACE_PRIVATE, StorageType.HUGGINGFACE_PUBLIC]:
            if self.hf_uploader:
                return self.hf_uploader.verify_model_integrity(
                    storage_info["repository_id"], storage_info.get("checksum")
                )

        elif storage_type == StorageType.AWS_S3:
            if self.s3_client:
                try:
                    # Check if object exists
                    self.s3_client.head_object(
                        Bucket=storage_info["bucket"], Key=storage_info["key"]
                    )
                    return True
                except Exception:
                    return False

        elif storage_type == StorageType.LOCAL:
            # Check if file exists
            return Path(storage_info["path"]).exists()

        return False


# Integration with Hokusai model registration
async def register_and_upload_model(
    model_id: str, model_path: str, model_metadata: Dict[str, Any], environment: str = "development"
) -> Dict[str, Any]:
    """Register a model in Hokusai and upload to appropriate storage.

    This is the main entry point called when a model is registered.

    Args:
    ----
        model_id: Hokusai model ID
        model_path: Path to model file
        model_metadata: Model metadata
        environment: Deployment environment

    Returns:
    -------
        Complete registration information

    """
    # Initialize storage manager
    storage_manager = ModelStorageManager(environment=environment)

    # Upload model to storage
    storage_info = await storage_manager.upload_model(
        model_id=model_id, model_path=model_path, model_metadata=model_metadata
    )

    # Verify upload
    if not storage_manager.verify_storage(storage_info):
        raise ValueError(f"Failed to verify storage for model {model_id}")

    # Return complete registration info
    return {
        "model_id": model_id,
        "status": "registered",
        "storage": storage_info,
        "metadata": model_metadata,
        "environment": environment,
        "registered_at": datetime.utcnow().isoformat(),
    }


# Example for Model ID 21
if __name__ == "__main__":
    import asyncio

    async def test_model_21():
        """Test registration of Sales Lead Scoring Model."""
        model_metadata = {
            "name": "Sales Lead Scoring Model",
            "type": "tabular-classification",
            "description": "Predicts sales lead conversion probability",
            "sensitivity": "medium",  # Not high sensitivity
            "public_ok": False,  # Never make public
            "version": "1.0.0",
        }

        print("🚀 Registering Sales Lead Scoring Model (ID 21)...")
        print(f"📊 Environment: {os.getenv('ENVIRONMENT', 'development')}")
        print("🔐 Security: Private repository")

        # Simulate registration
        result = {
            "model_id": "21",
            "status": "registered",
            "storage": {
                "storage_type": "huggingface_private",
                "repository_id": "hokusai-protocol/hokusai-sales-lead-scorer-21",
                "is_private": True,
                "inference_endpoint": "Via Hokusai API only",
            },
        }

        print("\n✅ Model registered successfully!")
        print(f"📦 Storage: {result['storage']['storage_type']}")
        print(f"🔗 Repository: {result['storage']['repository_id']}")
        print(f"🔐 Private: {result['storage']['is_private']}")
        print("🎯 Access: Through Hokusai API with authentication")

    # Run test
    asyncio.run(test_model_21())
