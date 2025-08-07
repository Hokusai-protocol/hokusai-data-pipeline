"""
Startup validation utilities for the Hokusai API service.

This module provides validation functions that should be called during
application startup to ensure all required credentials and configurations
are properly set up before the service starts handling requests.
"""

import logging
import os
import sys
from typing import List, Tuple

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, continue without it
    pass

logger = logging.getLogger(__name__)

def validate_database_credentials() -> Tuple[bool, List[str]]:
    """
    Validate that database credentials are available and accessible.
    
    Returns:
        Tuple of (success: bool, errors: List[str])
    """
    errors = []
    
    try:
        from src.api.utils.config import get_settings
        settings = get_settings()
        
        # Test that we can retrieve the database password
        try:
            password = settings.effective_database_password
            if not password:
                errors.append("Database password is empty")
            else:
                logger.info("Database password validation successful")
                
        except ValueError as e:
            errors.append(f"Database password retrieval failed: {e}")
        except Exception as e:
            errors.append(f"Unexpected error validating database password: {e}")
            
        # Test other database configuration
        try:
            host = settings.effective_database_host
            if not host:
                errors.append("Database host is empty")
                
            port = settings.effective_database_port
            if not port or port <= 0:
                errors.append(f"Invalid database port: {port}")
                
            user = settings.effective_database_user
            if not user:
                errors.append("Database user is empty")
                
            db_name = settings.effective_database_name
            if not db_name:
                errors.append("Database name is empty")
                
        except Exception as e:
            errors.append(f"Database configuration validation failed: {e}")
            
    except Exception as e:
        errors.append(f"Failed to load application settings: {e}")
    
    return len(errors) == 0, errors

def validate_aws_configuration() -> Tuple[bool, List[str]]:
    """
    Validate AWS configuration for services that depend on it.
    
    Returns:
        Tuple of (success: bool, errors: List[str])
    """
    errors = []
    warnings = []
    
    # Check AWS region
    aws_region = os.getenv("AWS_REGION")
    if not aws_region:
        warnings.append("AWS_REGION not set - will use default region")
    else:
        logger.info(f"AWS region configured: {aws_region}")
    
    # Check if we're running in AWS environment
    environment = os.getenv("ENVIRONMENT", "").lower()
    if environment in ["production", "staging", "development"]:
        # Check for AWS credentials if in cloud environment
        try:
            import boto3
            import botocore.exceptions
            
            # Test if we can create a session (this validates credentials)
            session = boto3.Session()
            # Try to get caller identity to validate credentials
            sts = session.client('sts', region_name=aws_region or 'us-east-1')
            identity = sts.get_caller_identity()
            logger.info(f"AWS credentials validated for account: {identity.get('Account')}")
            
        except ImportError:
            errors.append("boto3 not available but running in cloud environment")
        except botocore.exceptions.NoCredentialsError:
            if environment == "production":
                errors.append("No AWS credentials found in production environment")
            else:
                warnings.append("No AWS credentials found - some features may be unavailable")
        except botocore.exceptions.ClientError as e:
            errors.append(f"AWS credentials validation failed: {e}")
        except Exception as e:
            warnings.append(f"AWS configuration check failed: {e}")
    else:
        logger.info("Not running in cloud environment, skipping AWS credential validation")
    
    # Log warnings but don't fail validation
    for warning in warnings:
        logger.warning(warning)
    
    return len(errors) == 0, errors

def validate_required_environment_variables() -> Tuple[bool, List[str]]:
    """
    Validate that required environment variables are set.
    
    Returns:
        Tuple of (success: bool, errors: List[str])
    """
    errors = []
    
    # Critical environment variables
    required_vars = {
        "ENVIRONMENT": "Application environment (development, staging, production)"
    }
    
    # Optional but recommended variables
    recommended_vars = {
        "AWS_REGION": "AWS region for service integrations",
        "API_SECRET_KEY": "Secret key for API authentication"
    }
    
    # Check required variables
    for var_name, description in required_vars.items():
        value = os.getenv(var_name)
        if not value:
            errors.append(f"Required environment variable {var_name} not set ({description})")
        else:
            logger.info(f"✓ {var_name} configured")
    
    # Check recommended variables
    for var_name, description in recommended_vars.items():
        value = os.getenv(var_name)
        if not value:
            logger.warning(f"Recommended environment variable {var_name} not set ({description})")
        else:
            logger.info(f"✓ {var_name} configured")
    
    # Check database password variables (at least one should be set)
    db_password = os.getenv("DB_PASSWORD", os.getenv("DATABASE_PASSWORD"))
    secret_name = os.getenv("DB_SECRET_NAME")
    
    if not db_password and not secret_name:
        errors.append(
            "Database password not configured. Set DB_PASSWORD, DATABASE_PASSWORD, "
            "or configure DB_SECRET_NAME for AWS Secrets Manager"
        )
    elif db_password:
        logger.info("✓ Database password configured via environment variable")
    elif secret_name:
        logger.info(f"✓ Database password configured via AWS Secrets Manager: {secret_name}")
    
    return len(errors) == 0, errors

def run_startup_validation(exit_on_failure: bool = True) -> bool:
    """
    Run all startup validations.
    
    Args:
        exit_on_failure: If True, exit the process on validation failure
        
    Returns:
        bool: True if all validations passed, False otherwise
    """
    logger.info("Running startup validation checks...")
    
    all_passed = True
    all_errors = []
    
    # Run all validation checks
    checks = [
        ("Environment Variables", validate_required_environment_variables),
        ("AWS Configuration", validate_aws_configuration),
        ("Database Credentials", validate_database_credentials),
    ]
    
    for check_name, check_function in checks:
        logger.info(f"Validating {check_name}...")
        try:
            passed, errors = check_function()
            if passed:
                logger.info(f"✓ {check_name} validation passed")
            else:
                logger.error(f"✗ {check_name} validation failed:")
                for error in errors:
                    logger.error(f"  - {error}")
                all_passed = False
                all_errors.extend(errors)
        except Exception as e:
            logger.error(f"✗ {check_name} validation encountered an error: {e}")
            all_passed = False
            all_errors.append(f"{check_name}: {e}")
    
    # Summary
    if all_passed:
        logger.info("✓ All startup validation checks passed")
    else:
        logger.error("✗ Startup validation failed with the following errors:")
        for error in all_errors:
            logger.error(f"  - {error}")
        
        if exit_on_failure:
            logger.error("Exiting due to startup validation failures")
            sys.exit(1)
    
    return all_passed

if __name__ == "__main__":
    # Allow running this module directly for testing
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    run_startup_validation(exit_on_failure=True)