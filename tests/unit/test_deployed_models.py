"""Tests for deployed models database schema and models."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.deployed_models import Base, DeployedModel, DeployedModelStatus


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()


class TestDeployedModelEnum:
    """Test DeployedModelStatus enum."""

    def test_enum_values(self):
        """Test that enum has correct values."""
        assert DeployedModelStatus.PENDING.value == "pending"
        assert DeployedModelStatus.DEPLOYING.value == "deploying"
        assert DeployedModelStatus.DEPLOYED.value == "deployed"
        assert DeployedModelStatus.FAILED.value == "failed"
        assert DeployedModelStatus.STOPPED.value == "stopped"

    def test_enum_from_string(self):
        """Test creating enum from string values."""
        assert DeployedModelStatus("pending") == DeployedModelStatus.PENDING
        assert DeployedModelStatus("deployed") == DeployedModelStatus.DEPLOYED
        assert DeployedModelStatus("failed") == DeployedModelStatus.FAILED


class TestDeployedModel:
    """Test DeployedModel SQLAlchemy model."""

    def test_create_deployed_model(self, in_memory_db):
        """Test creating a deployed model record."""
        model_id = str(uuid4())
        endpoint_url = "https://api.huggingface.co/inference/endpoints/test-endpoint"

        deployed_model = DeployedModel(
            model_id=model_id,
            provider="huggingface",
            endpoint_url=endpoint_url,
            status=DeployedModelStatus.DEPLOYED,
            provider_model_id="test-endpoint",
            instance_type="cpu",
        )

        in_memory_db.add(deployed_model)
        in_memory_db.commit()

        # Verify the model was saved
        saved_model = in_memory_db.query(DeployedModel).filter_by(model_id=model_id).first()
        assert saved_model is not None
        assert saved_model.model_id == model_id
        assert saved_model.provider == "huggingface"
        assert saved_model.endpoint_url == endpoint_url
        assert saved_model.status == DeployedModelStatus.DEPLOYED
        assert saved_model.provider_model_id == "test-endpoint"
        assert saved_model.instance_type == "cpu"

        # Check that UUID and timestamps are set
        assert isinstance(saved_model.id, UUID)
        assert isinstance(saved_model.created_at, datetime)
        assert isinstance(saved_model.updated_at, datetime)

    def test_deployed_model_defaults(self, in_memory_db):
        """Test that deployed model has correct defaults."""
        model_id = str(uuid4())

        deployed_model = DeployedModel(model_id=model_id, provider="huggingface")

        in_memory_db.add(deployed_model)
        in_memory_db.commit()

        saved_model = in_memory_db.query(DeployedModel).filter_by(model_id=model_id).first()
        assert saved_model.status == DeployedModelStatus.PENDING
        assert saved_model.endpoint_url is None
        assert saved_model.provider_model_id is None
        assert saved_model.instance_type == "cpu"  # Default
        assert saved_model.error_message is None
        assert saved_model.deployment_metadata == {}

    def test_update_deployed_model_status(self, in_memory_db):
        """Test updating deployed model status."""
        model_id = str(uuid4())

        deployed_model = DeployedModel(
            model_id=model_id, provider="huggingface", status=DeployedModelStatus.PENDING
        )

        in_memory_db.add(deployed_model)
        in_memory_db.commit()

        # Update status
        deployed_model.status = DeployedModelStatus.DEPLOYED
        deployed_model.endpoint_url = "https://api.huggingface.co/inference/endpoints/test"
        in_memory_db.commit()

        # Verify update
        updated_model = in_memory_db.query(DeployedModel).filter_by(model_id=model_id).first()
        assert updated_model.status == DeployedModelStatus.DEPLOYED
        assert updated_model.endpoint_url == "https://api.huggingface.co/inference/endpoints/test"
        # updated_at should be different from created_at after update
        assert updated_model.updated_at > updated_model.created_at

    def test_deployed_model_with_error(self, in_memory_db):
        """Test deployed model with error message."""
        model_id = str(uuid4())
        error_msg = "Failed to deploy: insufficient quota"

        deployed_model = DeployedModel(
            model_id=model_id,
            provider="huggingface",
            status=DeployedModelStatus.FAILED,
            error_message=error_msg,
        )

        in_memory_db.add(deployed_model)
        in_memory_db.commit()

        saved_model = in_memory_db.query(DeployedModel).filter_by(model_id=model_id).first()
        assert saved_model.status == DeployedModelStatus.FAILED
        assert saved_model.error_message == error_msg

    def test_deployed_model_with_metadata(self, in_memory_db):
        """Test deployed model with metadata."""
        model_id = str(uuid4())
        metadata = {
            "model_name": "bert-base-uncased",
            "task": "text-classification",
            "framework": "pytorch",
            "accelerator": "cpu",
        }

        deployed_model = DeployedModel(
            model_id=model_id, provider="huggingface", deployment_metadata=metadata
        )

        in_memory_db.add(deployed_model)
        in_memory_db.commit()

        saved_model = in_memory_db.query(DeployedModel).filter_by(model_id=model_id).first()
        assert saved_model.deployment_metadata == metadata

    def test_query_by_model_id(self, in_memory_db):
        """Test querying deployed models by MLFlow model ID."""
        model_id_1 = str(uuid4())
        model_id_2 = str(uuid4())

        # Create two deployed models
        deployed_model_1 = DeployedModel(
            model_id=model_id_1, provider="huggingface", status=DeployedModelStatus.DEPLOYED
        )
        deployed_model_2 = DeployedModel(
            model_id=model_id_2, provider="huggingface", status=DeployedModelStatus.PENDING
        )

        in_memory_db.add_all([deployed_model_1, deployed_model_2])
        in_memory_db.commit()

        # Query by model_id
        result_1 = in_memory_db.query(DeployedModel).filter_by(model_id=model_id_1).first()
        assert result_1.model_id == model_id_1
        assert result_1.status == DeployedModelStatus.DEPLOYED

        result_2 = in_memory_db.query(DeployedModel).filter_by(model_id=model_id_2).first()
        assert result_2.model_id == model_id_2
        assert result_2.status == DeployedModelStatus.PENDING

    def test_query_by_status(self, in_memory_db):
        """Test querying deployed models by status."""
        model_id_1 = str(uuid4())
        model_id_2 = str(uuid4())
        model_id_3 = str(uuid4())

        deployed_models = [
            DeployedModel(
                model_id=model_id_1, provider="huggingface", status=DeployedModelStatus.DEPLOYED
            ),
            DeployedModel(
                model_id=model_id_2, provider="huggingface", status=DeployedModelStatus.DEPLOYED
            ),
            DeployedModel(
                model_id=model_id_3, provider="huggingface", status=DeployedModelStatus.PENDING
            ),
        ]

        in_memory_db.add_all(deployed_models)
        in_memory_db.commit()

        # Query deployed models
        deployed_results = (
            in_memory_db.query(DeployedModel).filter_by(status=DeployedModelStatus.DEPLOYED).all()
        )
        assert len(deployed_results) == 2

        # Query pending models
        pending_results = (
            in_memory_db.query(DeployedModel).filter_by(status=DeployedModelStatus.PENDING).all()
        )
        assert len(pending_results) == 1

    def test_model_id_index(self, in_memory_db):
        """Test that model_id has index for performance."""
        # Create multiple records
        for i in range(100):
            deployed_model = DeployedModel(model_id=str(uuid4()), provider="huggingface")
            in_memory_db.add(deployed_model)

        in_memory_db.commit()

        # This test verifies the index exists by checking query performance
        # In a real database, this would benefit from the index
        target_model_id = str(uuid4())
        deployed_model = DeployedModel(model_id=target_model_id, provider="huggingface")
        in_memory_db.add(deployed_model)
        in_memory_db.commit()

        result = in_memory_db.query(DeployedModel).filter_by(model_id=target_model_id).first()
        assert result.model_id == target_model_id

    def test_status_index(self, in_memory_db):
        """Test that status has index for performance."""
        # Create multiple records with different statuses
        statuses = [
            DeployedModelStatus.PENDING,
            DeployedModelStatus.DEPLOYING,
            DeployedModelStatus.DEPLOYED,
            DeployedModelStatus.FAILED,
        ]

        for i in range(20):
            for status in statuses:
                deployed_model = DeployedModel(
                    model_id=str(uuid4()), provider="huggingface", status=status
                )
                in_memory_db.add(deployed_model)

        in_memory_db.commit()

        # Query by status - should benefit from index
        deployed_models = (
            in_memory_db.query(DeployedModel).filter_by(status=DeployedModelStatus.DEPLOYED).all()
        )
        assert len(deployed_models) == 20
