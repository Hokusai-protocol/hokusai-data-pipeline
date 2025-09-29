"""API key generation and validation service."""

import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import bcrypt

from src.database.operations import DatabaseOperations


# Custom exceptions
class APIKeyError(Exception):
    """Base exception for API key operations."""

    pass


class APIKeyCreationError(APIKeyError):
    """Error creating API key."""

    pass


class APIKeyNotFoundError(APIKeyError):
    """API key not found."""

    pass


class APIKeyValidationError(APIKeyError):
    """API key validation failed."""

    pass


@dataclass
class APIKey:
    """API key with full key value (only returned on creation)."""

    key: str
    key_id: str
    user_id: str
    name: str
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime] = None
    rate_limit_per_hour: int = 1000
    allowed_ips: Optional[List[str]] = None


@dataclass
class APIKeyInfo:
    """API key information without the actual key value."""

    key_id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool
    expires_at: Optional[datetime] = None


@dataclass
class ValidationResult:
    """Result of API key validation."""

    is_valid: bool
    key_id: Optional[str] = None
    user_id: Optional[str] = None
    rate_limit_per_hour: Optional[int] = None
    error: Optional[str] = None


class APIKeyService:
    """Service for managing API keys."""

    def __init__(self, db: DatabaseOperations):
        """Initialize API key service."""
        self.db = db
        self._key_length = 40  # Length of random part

    def generate_api_key(
        self,
        user_id: str,
        key_name: str,
        environment: str = "production",
        expires_at: Optional[datetime] = None,
        rate_limit_per_hour: int = 1000,
        allowed_ips: Optional[List[str]] = None,
    ) -> APIKey:
        """Generate a new API key."""
        try:
            # Generate key components
            key_id = str(uuid.uuid4())
            prefix = self._get_key_prefix(environment)
            random_part = self._generate_random_key()
            full_key = f"{prefix}_{random_part}"

            # Hash the key for storage
            key_hash = self._hash_api_key(full_key)

            # Create model - APIKeyModel not yet implemented
            # api_key_model = APIKeyModel(
            #     key_id=key_id,
            #     key_hash=key_hash,
            #     key_prefix=f"{prefix}_{random_part[:3]}",
            #     user_id=user_id,
            #     name=key_name,
            #     created_at=datetime.now(timezone.utc),
            #     expires_at=expires_at,
            #     is_active=True,
            #     rate_limit_per_hour=rate_limit_per_hour,
            #     allowed_ips=allowed_ips,
            #     environment=environment,
            # )

            # Save to database - not yet implemented
            # self.db.save_api_key(api_key_model)

            # For now, just create the return value
            created_at = datetime.now(timezone.utc)

            # Return the full key (only time it's available)
            return APIKey(
                key=full_key,
                key_id=key_id,
                user_id=user_id,
                name=key_name,
                is_active=True,
                created_at=created_at,
                expires_at=expires_at,
                rate_limit_per_hour=rate_limit_per_hour,
                allowed_ips=allowed_ips,
            )

        except Exception as e:
            raise APIKeyCreationError(f"Failed to create API key: {str(e)}")

    def validate_api_key(self, api_key: str, client_ip: Optional[str] = None) -> ValidationResult:
        """Validate an API key."""
        try:
            # Look up all API keys and verify against hashes
            # (bcrypt hashes are not deterministic, so we can't hash and lookup)
            all_keys = self.db.get_all_api_keys()

            api_key_data = None
            for key_data in all_keys:
                if self._verify_api_key(api_key, key_data.get("key_hash", "")):
                    api_key_data = key_data
                    break

            if not api_key_data:
                return ValidationResult(is_valid=False, error="API key not found")

            # Check if active
            if not api_key_data.get("is_active", False):
                return ValidationResult(is_valid=False, error="API key is inactive")

            # Check expiration
            if api_key_data.get("expires_at"):
                expires_at = datetime.fromisoformat(api_key_data["expires_at"])
                if expires_at < datetime.now(timezone.utc):
                    return ValidationResult(is_valid=False, error="API key has expired")

            # Check IP restrictions
            allowed_ips = api_key_data.get("allowed_ips")
            if allowed_ips and client_ip:
                if client_ip not in allowed_ips:
                    return ValidationResult(is_valid=False, error="IP address not allowed")

            # Valid key
            return ValidationResult(
                is_valid=True,
                key_id=api_key_data.get("key_id"),
                user_id=api_key_data.get("user_id"),
                rate_limit_per_hour=api_key_data.get("rate_limit_per_hour", 1000),
            )

        except Exception as e:
            return ValidationResult(is_valid=False, error=f"Validation error: {str(e)}")

    def list_api_keys(self, user_id: str, active_only: bool = False) -> List[APIKeyInfo]:
        """List API keys for a user."""
        try:
            keys_data = self.db.get_api_keys_by_user(user_id)

            keys = []
            for key_data in keys_data:
                # APIKeyModel.from_dict not yet implemented
                # model = APIKeyModel.from_dict(key_data)

                # Filter if needed
                if active_only and not key_data.get("is_active", False):
                    continue

                keys.append(
                    APIKeyInfo(
                        key_id=key_data.get("key_id"),
                        name=key_data.get("name"),
                        key_prefix=key_data.get("key_prefix"),
                        created_at=datetime.fromisoformat(key_data.get("created_at"))
                        if key_data.get("created_at")
                        else datetime.now(timezone.utc),
                        last_used_at=datetime.fromisoformat(key_data.get("last_used_at"))
                        if key_data.get("last_used_at")
                        else None,
                        is_active=key_data.get("is_active", False),
                        expires_at=datetime.fromisoformat(key_data.get("expires_at"))
                        if key_data.get("expires_at")
                        else None,
                    )
                )

            return keys

        except Exception as e:
            raise APIKeyError(f"Failed to list API keys: {str(e)}")

    def revoke_api_key(self, user_id: str, key_id: str) -> bool:
        """Revoke an API key."""
        try:
            # Get the key
            key_data = self.db.get_api_key(key_id)
            if not key_data:
                raise APIKeyNotFoundError(f"API key {key_id} not found")

            # Verify ownership
            if key_data["user_id"] != user_id:
                raise APIKeyValidationError("Not authorized to revoke this key")

            # Update to inactive
            self.db.update_api_key(key_id, {"is_active": False})

            return True

        except APIKeyError:
            raise
        except Exception as e:
            raise APIKeyError(f"Failed to revoke API key: {str(e)}")

    def rotate_api_key(self, user_id: str, key_id: str) -> APIKey:
        """Rotate an API key (revoke old, create new with same settings)."""
        try:
            # Get existing key
            key_data = self.db.get_api_key(key_id)
            if not key_data:
                raise APIKeyNotFoundError(f"API key {key_id} not found")

            # Verify ownership
            if key_data["user_id"] != user_id:
                raise APIKeyValidationError("Not authorized to rotate this key")

            # Revoke old key
            self.revoke_api_key(user_id, key_id)

            # Create new key with same settings
            return self.generate_api_key(
                user_id=user_id,
                key_name=key_data["name"],
                environment=key_data.get("environment", "production"),
                expires_at=datetime.fromisoformat(key_data["expires_at"])
                if key_data.get("expires_at")
                else None,
                rate_limit_per_hour=key_data.get("rate_limit_per_hour", 1000),
                allowed_ips=key_data.get("allowed_ips"),
            )

        except APIKeyError:
            raise
        except Exception as e:
            raise APIKeyError(f"Failed to rotate API key: {str(e)}")

    def update_last_used(self, key_id: str) -> None:
        """Update the last used timestamp for a key."""
        try:
            self.db.update_api_key(key_id, {"last_used_at": datetime.now(timezone.utc)})
        except Exception:
            # Don't fail the request if we can't update last used
            pass

    def _get_key_prefix(self, environment: str) -> str:
        """Get the prefix for an API key based on environment."""
        prefixes = {"production": "hk_live", "test": "hk_test", "development": "hk_dev"}
        return prefixes.get(environment, "hk_live")

    def _generate_random_key(self) -> str:
        """Generate a cryptographically secure random key."""
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(self._key_length))

    def _hash_api_key(self, api_key: str) -> str:
        """Hash an API key using bcrypt."""
        # bcrypt requires bytes
        key_bytes = api_key.encode("utf-8")
        # Generate salt and hash
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(key_bytes, salt).decode("utf-8")

    def _verify_api_key(self, api_key: str, hashed: str) -> bool:
        """Verify an API key against a hash."""
        try:
            key_bytes = api_key.encode("utf-8")
            hash_bytes = hashed.encode("utf-8")
            return bcrypt.checkpw(key_bytes, hash_bytes)
        except Exception:
            return False
