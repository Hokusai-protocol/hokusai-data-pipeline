#!/usr/bin/env python3
"""Test database connection with current configuration."""

import os
import sys
import logging
import psycopg2

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_connection():
    """Test database connection with environment variables."""
    
    # Check environment variables
    logger.info("=== Environment Variables ===")
    env_vars = {
        "DB_USER": os.getenv("DB_USER", "NOT SET"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD", "NOT SET"),
        "DB_HOST": os.getenv("DB_HOST", "NOT SET"),
        "DB_PORT": os.getenv("DB_PORT", "NOT SET"),
        "DB_NAME": os.getenv("DB_NAME", "NOT SET"),
        "DATABASE_USER": os.getenv("DATABASE_USER", "NOT SET"),
        "DATABASE_PASSWORD": os.getenv("DATABASE_PASSWORD", "NOT SET"),
        "DATABASE_HOST": os.getenv("DATABASE_HOST", "NOT SET"),
        "DATABASE_PORT": os.getenv("DATABASE_PORT", "NOT SET"),
        "DATABASE_NAME": os.getenv("DATABASE_NAME", "NOT SET"),
    }
    
    for key, value in env_vars.items():
        if "PASSWORD" in key:
            # Mask password for security
            if value != "NOT SET":
                logger.info(f"{key}: ***MASKED*** (length: {len(value)})")
            else:
                logger.info(f"{key}: NOT SET")
        else:
            logger.info(f"{key}: {value}")
    
    # Import and test configuration
    logger.info("\n=== Testing Configuration ===")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from src.api.utils.config import get_settings
        
        settings = get_settings()
        
        logger.info(f"Database Host: {settings.effective_database_host}")
        logger.info(f"Database Port: {settings.effective_database_port}")
        logger.info(f"Database User: {settings.effective_database_user}")
        logger.info(f"Database Name: {settings.effective_database_name}")
        logger.info(f"Database Password: ***MASKED*** (length: {len(settings.effective_database_password)})")
        
        # Build connection string
        conn_str = settings.postgres_uri
        # Mask password in connection string
        import re
        masked_conn_str = re.sub(r':([^@]+)@', ':***MASKED***@', conn_str)
        logger.info(f"Connection String: {masked_conn_str}")
        
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return False
    
    # Test actual connection
    logger.info("\n=== Testing Database Connection ===")
    try:
        logger.info(f"Attempting to connect to database...")
        conn = psycopg2.connect(settings.postgres_uri, connect_timeout=5)
        
        # Test query
        cursor = conn.cursor()
        cursor.execute("SELECT current_user, current_database(), version();")
        result = cursor.fetchone()
        
        logger.info(f"✓ Connection successful!")
        logger.info(f"  Current User: {result[0]}")
        logger.info(f"  Current Database: {result[1]}")
        logger.info(f"  PostgreSQL Version: {result[2][:50]}...")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.OperationalError as e:
        logger.error(f"✗ Connection failed: {e}")
        # Parse error for more details
        error_str = str(e)
        if "password authentication failed" in error_str:
            import re
            user_match = re.search(r'user "([^"]+)"', error_str)
            if user_match:
                logger.error(f"  → Tried to authenticate as user: {user_match.group(1)}")
                logger.error(f"  → Expected user: mlflow")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    # Test with local environment
    logger.info("=== Testing with Current Environment ===\n")
    success = test_connection()
    
    if not success:
        logger.info("\n=== Troubleshooting Tips ===")
        logger.info("1. Check if DB_PASSWORD environment variable is set")
        logger.info("2. Verify the password in AWS Secrets Manager matches the RDS password")
        logger.info("3. Ensure DB_USER is set to 'mlflow' (not 'postgres')")
        logger.info("4. Check that the database name is 'mlflow_db'")
        sys.exit(1)
    else:
        logger.info("\n✅ Database connection test successful!")
        sys.exit(0)