"""Database operations for token and model management.
"""
import json
import logging
from datetime import datetime
from typing import Any, Optional, List, Dict, Tuple

from .connection import DatabaseConnection
from .models import ModelStatus, TokenModel, APIKeyModel

logger = logging.getLogger(__name__)


class DatabaseOperations:
    """Unified database operations for API keys and other data."""
    
    def __init__(self, connection: DatabaseConnection = None):
        """Initialize database operations."""
        self.connection = connection or DatabaseConnection()
    
    def save_api_key(self, api_key: APIKeyModel) -> None:
        """Save an API key to the database."""
        query = """
            INSERT INTO api_keys (
                key_id, key_hash, key_prefix, user_id, name,
                created_at, expires_at, is_active, rate_limit_per_hour,
                allowed_ips, environment
            ) VALUES (
                :key_id, :key_hash, :key_prefix, :user_id, :name,
                :created_at, :expires_at, :is_active, :rate_limit_per_hour,
                :allowed_ips, :environment
            )
        """
        
        params = {
            "key_id": api_key.key_id,
            "key_hash": api_key.key_hash,
            "key_prefix": api_key.key_prefix,
            "user_id": api_key.user_id,
            "name": api_key.name,
            "created_at": api_key.created_at.isoformat(),
            "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
            "is_active": 1 if api_key.is_active else 0,
            "rate_limit_per_hour": api_key.rate_limit_per_hour,
            "allowed_ips": json.dumps(api_key.allowed_ips) if api_key.allowed_ips else None,
            "environment": api_key.environment
        }
        
        self.connection.execute_update(query, params)
    
    def get_api_key(self, key_id: str) -> Optional[Dict[str, Any]]:
        """Get an API key by ID."""
        query = """
            SELECT * FROM api_keys
            WHERE key_id = :key_id
        """
        results = self.connection.execute_query(query, {"key_id": key_id})
        return results[0] if results else None
    
    def get_all_api_keys(self) -> List[Dict[str, Any]]:
        """Get all API keys."""
        query = "SELECT * FROM api_keys"
        return self.connection.execute_query(query, {})
    
    def get_api_keys_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all API keys for a user."""
        query = """
            SELECT * FROM api_keys
            WHERE user_id = :user_id
            ORDER BY created_at DESC
        """
        return self.connection.execute_query(query, {"user_id": user_id})
    
    def update_api_key(self, key_id: str, updates: Dict[str, Any]) -> None:
        """Update an API key."""
        allowed_fields = {"is_active", "last_used_at", "expires_at", "rate_limit_per_hour", "allowed_ips"}
        update_fields = []
        params = {"key_id": key_id}
        
        for field, value in updates.items():
            if field in allowed_fields:
                update_fields.append(f"{field} = :{field}")
                if field == "last_used_at" and isinstance(value, datetime):
                    params[field] = value.isoformat()
                elif field == "allowed_ips" and isinstance(value, list):
                    params[field] = json.dumps(value)
                else:
                    params[field] = value
        
        if update_fields:
            query = f"""
                UPDATE api_keys
                SET {', '.join(update_fields)}
                WHERE key_id = :key_id
            """
            self.connection.execute_update(query, params)


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


class APIKeyDatabaseOperations:
    """Handles database operations for API keys."""
    
    def __init__(self, db: DatabaseConnection):
        """Initialize API key database operations."""
        self.db = db
    
    def save_api_key(self, api_key_model: APIKeyModel) -> None:
        """Save an API key to the database."""
        try:
            query = """
                INSERT INTO api_keys (
                    key_id, key_hash, key_prefix, user_id, name,
                    created_at, expires_at, last_used_at, is_active,
                    rate_limit_per_hour, allowed_ips, environment
                ) VALUES (
                    :key_id, :key_hash, :key_prefix, :user_id, :name,
                    :created_at, :expires_at, :last_used_at, :is_active,
                    :rate_limit_per_hour, :allowed_ips, :environment
                )
            """
            
            params = api_key_model.to_dict()
            # Convert allowed_ips list to JSON string for storage
            if params.get("allowed_ips"):
                params["allowed_ips"] = json.dumps(params["allowed_ips"])
            
            self.db.execute_update(query, params)
            logger.info(f"Saved API key {api_key_model.key_id}")
            
        except Exception as e:
            logger.error(f"Error saving API key: {str(e)}")
            raise
    
    def get_api_key_by_hash(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """Get API key by hash."""
        try:
            query = """
                SELECT * FROM api_keys
                WHERE key_hash = :key_hash
            """
            
            results = self.db.execute_query(query, {"key_hash": key_hash})
            
            if results and len(results) > 0:
                result = results[0]
                # Parse JSON fields
                if result.get("allowed_ips"):
                    result["allowed_ips"] = json.loads(result["allowed_ips"])
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting API key by hash: {str(e)}")
            raise
    
    def get_all_api_key_hashes(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Get all API key hashes for verification."""
        try:
            query = """
                SELECT * FROM api_keys
                WHERE is_active = true
            """
            
            results = self.db.execute_query(query, {})
            
            hashes = []
            for result in results:
                # Parse JSON fields
                if result.get("allowed_ips"):
                    result["allowed_ips"] = json.loads(result["allowed_ips"])
                hashes.append((result["key_hash"], result))
            
            return hashes
            
        except Exception as e:
            logger.error(f"Error getting all API key hashes: {str(e)}")
            raise
    
    def get_api_key(self, key_id: str) -> Optional[Dict[str, Any]]:
        """Get API key by ID."""
        try:
            query = """
                SELECT * FROM api_keys
                WHERE key_id = :key_id
            """
            
            results = self.db.execute_query(query, {"key_id": key_id})
            
            if results and len(results) > 0:
                result = results[0]
                # Parse JSON fields
                if result.get("allowed_ips"):
                    result["allowed_ips"] = json.loads(result["allowed_ips"])
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting API key: {str(e)}")
            raise
    
    def get_api_keys_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all API keys for a user."""
        try:
            query = """
                SELECT * FROM api_keys
                WHERE user_id = :user_id
                ORDER BY created_at DESC
            """
            
            results = self.db.execute_query(query, {"user_id": user_id})
            
            keys = []
            for result in results:
                # Parse JSON fields
                if result.get("allowed_ips"):
                    result["allowed_ips"] = json.loads(result["allowed_ips"])
                keys.append(result)
            
            return keys
            
        except Exception as e:
            logger.error(f"Error getting API keys by user: {str(e)}")
            raise
    
    def update_api_key(self, key_id: str, updates: Dict[str, Any]) -> None:
        """Update an API key."""
        try:
            # Build dynamic update query
            set_clauses = []
            params = {"key_id": key_id}
            
            for field, value in updates.items():
                set_clauses.append(f"{field} = :{field}")
                if field == "allowed_ips" and isinstance(value, list):
                    params[field] = json.dumps(value)
                else:
                    params[field] = value
            
            query = f"""
                UPDATE api_keys
                SET {', '.join(set_clauses)}
                WHERE key_id = :key_id
            """
            
            affected = self.db.execute_update(query, params)
            
            if affected > 0:
                logger.info(f"Updated API key {key_id}")
            else:
                logger.warning(f"No rows updated for API key {key_id}")
                
        except Exception as e:
            logger.error(f"Error updating API key: {str(e)}")
            raise
    
    def delete_api_key(self, key_id: str) -> None:
        """Delete an API key."""
        try:
            query = """
                DELETE FROM api_keys
                WHERE key_id = :key_id
            """
            
            affected = self.db.execute_update(query, {"key_id": key_id})
            
            if affected > 0:
                logger.info(f"Deleted API key {key_id}")
            else:
                logger.warning(f"No API key found with ID {key_id}")
                
        except Exception as e:
            logger.error(f"Error deleting API key: {str(e)}")
            raise
    
    def log_api_key_usage(self, usage_data: Dict[str, Any]) -> None:
        """Log API key usage."""
        try:
            query = """
                INSERT INTO api_key_usage (
                    api_key_id, endpoint, timestamp,
                    response_time_ms, status_code
                ) VALUES (
                    :api_key_id, :endpoint, :timestamp,
                    :response_time_ms, :status_code
                )
            """
            
            self.db.execute_update(query, usage_data)
            
        except Exception as e:
            # Don't raise - we don't want to fail requests due to logging errors
            logger.error(f"Error logging API key usage: {str(e)}")
    
    def get_usage_stats(self, key_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get usage statistics for an API key."""
        try:
            query = """
                SELECT 
                    COUNT(*) as total_requests,
                    AVG(response_time_ms) as avg_response_time,
                    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as error_count
                FROM api_key_usage
                WHERE api_key_id = :key_id
                AND timestamp > datetime('now', '-' || :hours || ' hours')
            """
            
            results = self.db.execute_query(query, {"key_id": key_id, "hours": hours})
            
            if results and len(results) > 0:
                stats = results[0]
                stats["error_rate"] = (
                    stats["error_count"] / stats["total_requests"]
                    if stats["total_requests"] > 0
                    else 0
                )
                return stats
            
            return {
                "total_requests": 0,
                "avg_response_time": 0,
                "error_count": 0,
                "error_rate": 0
            }
            
        except Exception as e:
            logger.error(f"Error getting usage stats: {str(e)}")
            raise
    
    def cleanup_expired_keys(self) -> int:
        """Mark expired keys as inactive."""
        try:
            query = """
                UPDATE api_keys
                SET is_active = false
                WHERE expires_at < datetime('now')
                AND is_active = true
            """
            
            affected = self.db.execute_update(query, {})
            
            if affected > 0:
                logger.info(f"Marked {affected} expired keys as inactive")
            
            return affected
            
        except Exception as e:
            logger.error(f"Error cleaning up expired keys: {str(e)}")
            raise
    
    def transaction(self):
        """Context manager for database transactions."""
        class TransactionContext:
            def __init__(self, db):
                self.db = db
            
            def __enter__(self):
                self.db.begin_transaction()
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type:
                    self.db.rollback_transaction()
                else:
                    self.db.commit_transaction()
                return False
        
        return TransactionContext(self.db)


class DatabaseOperations:
    """Unified database operations."""
    
    def __init__(self, connection: DatabaseConnection):
        """Initialize database operations."""
        self.connection = connection
        self.tokens = TokenOperations(connection)
        self.api_keys = APIKeyDatabaseOperations(connection)
