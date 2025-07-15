"""Database operations for token and model management.
"""
import json
import logging
from datetime import datetime
from typing import Any, Optional, List

from .connection import DatabaseConnection
from .models import ModelStatus, TokenModel

logger = logging.getLogger(__name__)


class TokenOperations:
    """Handles database operations for tokens and models."""

    def __init__(self, connection: DatabaseConnection) -> None:
        self.connection = connection

    def get_token(self, token_id: str) -> Optional[TokenModel]:
        """Retrieve a token by ID."""
        try:
            query = """
                SELECT token_id, model_status, mlflow_run_id, metric_name,
                       metric_value, baseline_value, created_at, updated_at, metadata
                FROM tokens
                WHERE token_id = :token_id
            """

            results = self.connection.execute_query(query, {"token_id": token_id})

            if results:
                # In a real implementation, we would parse the result
                # For now, return a mock token in DRAFT status
                return TokenModel(
                    token_id=token_id,
                    model_status=ModelStatus.DRAFT,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

            return None

        except Exception as e:
            logger.error(f"Error retrieving token {token_id}: {str(e)}")
            raise

    def validate_token_status(self, token_id: str) -> bool:
        """Validate if a token exists and is in DRAFT status."""
        token = self.get_token(token_id)

        if not token:
            raise ValueError(f"Token {token_id} not found")

        if not token.can_register():
            raise ValueError(
                f"Token {token_id} is in {token.model_status.value} status. "
                f"Only tokens in DRAFT or FAILED status can be registered."
            )

        return True

    def update_model_status(
        self, token_id: str, status: ModelStatus, mlflow_run_id: Optional[str] = None
    ) -> bool:
        """Update the model status for a token."""
        try:
            self.connection.begin_transaction()

            query = """
                UPDATE tokens
                SET model_status = :status,
                    mlflow_run_id = :mlflow_run_id,
                    updated_at = :updated_at
                WHERE token_id = :token_id
            """

            params = {
                "token_id": token_id,
                "status": status.value,
                "mlflow_run_id": mlflow_run_id,
                "updated_at": datetime.now().isoformat(),
            }

            affected_rows = self.connection.execute_update(query, params)

            if affected_rows > 0:
                self.connection.commit_transaction()
                logger.info(f"Updated token {token_id} status to {status.value}")
                return True
            else:
                self.connection.rollback_transaction()
                logger.warning(f"No rows updated for token {token_id}")
                return False

        except Exception as e:
            self.connection.rollback_transaction()
            logger.error(f"Error updating token status: {str(e)}")
            raise

    def save_mlflow_run_id(
        self,
        token_id: str,
        mlflow_run_id: str,
        metric_name: str,
        metric_value: float,
        baseline_value: float,
    ) -> bool:
        """Save MLflow run ID and metrics for a token."""
        try:
            self.connection.begin_transaction()

            query = """
                UPDATE tokens
                SET mlflow_run_id = :mlflow_run_id,
                    metric_name = :metric_name,
                    metric_value = :metric_value,
                    baseline_value = :baseline_value,
                    model_status = :status,
                    updated_at = :updated_at
                WHERE token_id = :token_id
            """

            params = {
                "token_id": token_id,
                "mlflow_run_id": mlflow_run_id,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "baseline_value": baseline_value,
                "status": ModelStatus.REGISTERED.value,
                "updated_at": datetime.now().isoformat(),
            }

            affected_rows = self.connection.execute_update(query, params)

            if affected_rows > 0:
                self.connection.commit_transaction()
                logger.info(f"Saved MLflow run ID {mlflow_run_id} for token {token_id}")
                return True
            else:
                self.connection.rollback_transaction()
                logger.warning(f"Failed to save MLflow run ID for token {token_id}")
                return False

        except Exception as e:
            self.connection.rollback_transaction()
            logger.error(f"Error saving MLflow run ID: {str(e)}")
            raise

    def list_tokens_by_status(self, status: ModelStatus) -> list[TokenModel]:
        """List all tokens with a specific status."""
        try:
            query = """
                SELECT token_id, model_status, mlflow_run_id, metric_name,
                       metric_value, baseline_value, created_at, updated_at, metadata
                FROM tokens
                WHERE model_status = :status
                ORDER BY updated_at DESC
            """

            self.connection.execute_query(query, {"status": status.value})

            # In a real implementation, we would parse the results
            # For now, return an empty list
            return []

        except Exception as e:
            logger.error(f"Error listing tokens by status: {str(e)}")
            raise

    def create_token(self, token_id: str, metadata: Optional[dict[str, Any]] = None) -> bool:
        """Create a new token in DRAFT status."""
        try:
            self.connection.begin_transaction()

            query = """
                INSERT INTO tokens (token_id, model_status, created_at, updated_at, metadata)
                VALUES (:token_id, :status, :created_at, :updated_at, :metadata)
            """

            now = datetime.now().isoformat()
            params = {
                "token_id": token_id,
                "status": ModelStatus.DRAFT.value,
                "created_at": now,
                "updated_at": now,
                "metadata": metadata,
            }

            self.connection.execute_update(query, params)
            self.connection.commit_transaction()

            logger.info(f"Created new token {token_id} in DRAFT status")
            return True

        except Exception as e:
            self.connection.rollback_transaction()
            logger.error(f"Error creating token: {str(e)}")
            raise




class DatabaseOperations:
    """Unified database operations."""
    
    def __init__(self, connection: DatabaseConnection):
        """Initialize database operations."""
        self.connection = connection
        self.tokens = TokenOperations(connection)
