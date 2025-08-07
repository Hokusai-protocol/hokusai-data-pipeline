#!/usr/bin/env python3
"""
Database Configuration Validation Script

This script validates the database configuration and provides recommendations
for fixing authentication issues. It can be run in production environments
to diagnose configuration problems.
"""

import os
import sys
import logging
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

def main():
    """Main validation function."""
    
    print("=" * 70)
    print("Hokusai Database Configuration Validation")
    print("=" * 70)
    
    # Run startup validation
    try:
        from src.api.utils.startup_validation import run_startup_validation
        
        success = run_startup_validation(exit_on_failure=False)
        
        if success:
            print("\n✓ All validations passed - database configuration looks good!")
            
            # Run connection test
            print("\nRunning connection test...")
            from test_database_connection import main as test_connection
            if test_connection():
                print("\n🎉 Database configuration is fully working!")
                return 0
            else:
                print("\n❌ Configuration is valid but connection test failed")
                return 1
        else:
            print("\n❌ Configuration validation failed")
            print("\nTo fix database authentication issues:")
            print("1. Set DATABASE_PASSWORD environment variable with correct password")
            print("2. Or configure AWS Secrets Manager with 'hokusai/database/credentials' secret")
            print("3. Ensure the database user 'mlflow' exists and has proper permissions")
            print("4. Verify database host and port are correct")
            
            return 1
            
    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.error("Make sure you're running from the project root directory")
        return 1
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)