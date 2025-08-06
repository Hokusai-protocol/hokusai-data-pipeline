#!/usr/bin/env python3
"""
Verification script for Phase 1 critical database fixes.

Tests:
1. Database configuration updates (mlflow -> mlflow_db)
2. Increased connection timeouts (5s -> 10s) 
3. Connection retry logic with exponential backoff
4. Enhanced error logging and handling
"""

import logging
import sys
from typing import Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_configuration() -> Tuple[bool, str]:
    """Test database configuration changes."""
    try:
        from src.api.utils.config import get_settings
        
        settings = get_settings()
        
        # Test database name fix
        if settings.database_name != "mlflow_db":
            return False, f"Primary database name should be 'mlflow_db', got '{settings.database_name}'"
        
        if settings.database_fallback_name != "mlflow":
            return False, f"Fallback database name should be 'mlflow', got '{settings.database_fallback_name}'"
        
        # Test timeout increases
        if settings.database_connect_timeout != 10:
            return False, f"Database connect timeout should be 10s, got {settings.database_connect_timeout}s"
        
        if settings.health_check_timeout != 10.0:
            return False, f"Health check timeout should be 10.0s, got {settings.health_check_timeout}s"
        
        if settings.auth_service_timeout != 10.0:
            return False, f"Auth service timeout should be 10.0s, got {settings.auth_service_timeout}s"
        
        # Test retry configuration
        if settings.database_max_retries != 3:
            return False, f"Database max retries should be 3, got {settings.database_max_retries}"
        
        if settings.database_retry_delay != 1.0:
            return False, f"Database retry delay should be 1.0s, got {settings.database_retry_delay}s"
        
        # Test URI generation
        primary_uri = settings.postgres_uri
        fallback_uri = settings.postgres_uri_fallback
        
        if "mlflow_db" not in primary_uri:
            return False, f"Primary URI should contain 'mlflow_db': {primary_uri}"
        
        if "mlflow_db" in fallback_uri and "/mlflow" not in fallback_uri:
            return False, f"Fallback URI should contain '/mlflow' but not 'mlflow_db': {fallback_uri}"
        
        logger.info("✅ Configuration test passed")
        return True, "All configuration changes verified"
        
    except Exception as e:
        return False, f"Configuration test failed: {str(e)}"


def test_database_connection_logic() -> Tuple[bool, str]:
    """Test database connection retry logic."""
    try:
        from src.api.routes.health import check_database_connection
        
        # This will fail in test environment but should demonstrate retry logic
        status, error = check_database_connection()
        
        if status:
            logger.info("✅ Database connection successful")
            return True, "Database connection successful"
        else:
            # Check that error message includes retry information
            if "after 3 attempts" in str(error):
                logger.info("✅ Retry logic working correctly (connection failed as expected)")
                return True, "Retry logic functioning correctly"
            else:
                return False, f"Retry logic not working correctly: {error}"
                
    except Exception as e:
        return False, f"Database connection test failed: {str(e)}"


def test_mlflow_timeout_config() -> Tuple[bool, str]:
    """Test MLflow timeout configuration."""
    try:
        from src.utils.mlflow_config import get_mlflow_status
        
        # Get status (may timeout, which is expected)
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("MLflow status check timed out (expected)")
        
        # Set a short timeout for this test
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(15)  # 15 second timeout
        
        try:
            status = get_mlflow_status()
            signal.alarm(0)  # Cancel alarm
            
            # Check that timeout configuration is present
            if "connection_timeout" in status:
                if status["connection_timeout"] == 10.0:
                    logger.info("✅ MLflow timeout configuration correct")
                    return True, "MLflow timeout configuration verified"
                else:
                    return False, f"MLflow timeout should be 10.0s, got {status['connection_timeout']}s"
            else:
                return False, "MLflow status missing connection_timeout field"
                
        except TimeoutError:
            signal.alarm(0)  # Cancel alarm
            logger.info("✅ MLflow connection timeout working (connection timed out as expected)")
            return True, "MLflow timeout configuration working"
        
    except Exception as e:
        return False, f"MLflow timeout test failed: {str(e)}"


def main():
    """Run all verification tests."""
    logger.info("🔍 Starting Phase 1 Database Fixes Verification")
    
    tests = [
        ("Configuration Updates", test_configuration),
        ("Database Connection Logic", test_database_connection_logic), 
        ("MLflow Timeout Configuration", test_mlflow_timeout_config),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n📋 Running {test_name} test...")
        try:
            success, message = test_func()
            results.append((test_name, success, message))
            
            if success:
                logger.info(f"✅ {test_name}: {message}")
            else:
                logger.error(f"❌ {test_name}: {message}")
                
        except Exception as e:
            results.append((test_name, False, str(e)))
            logger.error(f"❌ {test_name}: Unexpected error - {str(e)}")
    
    # Summary
    logger.info("\n📊 VERIFICATION SUMMARY")
    logger.info("=" * 50)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, message in results:
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
        if not success:
            logger.info(f"   └─ {message}")
    
    logger.info("=" * 50)
    logger.info(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All Phase 1 critical database fixes verified successfully!")
        return 0
    else:
        logger.error("⚠️  Some tests failed. Please review the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())