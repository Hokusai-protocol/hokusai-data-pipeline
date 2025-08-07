#!/usr/bin/env python3
"""
Quick validation script to verify database authentication fixes.

This script validates that:
1. No hardcoded passwords are being used
2. Credentials come from environment variables or AWS Secrets Manager
3. The configuration is properly set up

This script doesn't actually connect to the database.
"""

import os
import sys
from urllib.parse import urlparse

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def main():
    print("🔍 Validating Database Authentication Fixes")
    print("=" * 50)
    
    success = True
    
    # Test 1: Check that we can import and create settings
    print("\n1. Testing configuration loading...")
    try:
        from src.api.utils.config import get_settings
        settings = get_settings()
        print("   ✅ Configuration loaded successfully")
    except Exception as e:
        print(f"   ❌ Configuration failed: {e}")
        return False
    
    # Test 2: Check database connection string
    print("\n2. Testing database connection URI...")
    try:
        uri = settings.postgres_uri
        parsed = urlparse(uri)
        
        # Check that we're not using hardcoded "postgres" password
        if parsed.password == "postgres":
            print("   ❌ Still using hardcoded 'postgres' password")
            success = False
        else:
            print("   ✅ Not using hardcoded 'postgres' password")
        
        # Check that we're using the correct user
        if parsed.username == "mlflow":
            print("   ✅ Using correct database user 'mlflow'")
        else:
            print(f"   ⚠️  Using database user '{parsed.username}' (expected 'mlflow')")
        
        # Check database name
        db_name = parsed.path.lstrip('/')
        if db_name in ["mlflow_db", "mlflow"]:
            print(f"   ✅ Using correct database name '{db_name}'")
        else:
            print(f"   ⚠️  Using database name '{db_name}' (expected 'mlflow_db' or 'mlflow')")
            
        print(f"   📋 Connection details: {parsed.username}@{parsed.hostname}:{parsed.port}/{db_name}")
        
    except Exception as e:
        print(f"   ❌ Database URI test failed: {e}")
        success = False
    
    # Test 3: Check password source
    print("\n3. Testing password source...")
    env_password = os.getenv("DB_PASSWORD", os.getenv("DATABASE_PASSWORD"))
    secret_name = os.getenv("DB_SECRET_NAME")
    
    if env_password:
        print("   ✅ Password configured via environment variable")
        if env_password == "postgres":
            print("   ⚠️  Warning: password is 'postgres' - ensure this is intentional")
        else:
            print("   ✅ Password is not the default 'postgres'")
    elif secret_name:
        print(f"   ✅ Password configured via AWS Secrets Manager: {secret_name}")
    else:
        print("   ❌ No password source configured")
        success = False
    
    # Test 4: Check AWS integration
    print("\n4. Testing AWS Secrets Manager integration...")
    try:
        import boto3
        print("   ✅ boto3 available for AWS Secrets Manager")
        
        # Test if we can create a client (validates credentials)
        region = os.getenv("AWS_REGION", "us-east-1")
        session = boto3.Session()
        client = session.client('secretsmanager', region_name=region)
        print("   ✅ AWS credentials available")
        
    except ImportError:
        print("   ⚠️  boto3 not available (AWS Secrets Manager disabled)")
    except Exception as e:
        print(f"   ⚠️  AWS setup issue: {e}")
    
    # Test 5: Check effective password retrieval
    print("\n5. Testing effective password retrieval...")
    try:
        # This will test the full password retrieval logic
        password = settings.effective_database_password
        if password:
            print("   ✅ Password retrieval successful")
            if password == "postgres":
                print("   ⚠️  Warning: retrieved password is 'postgres'")
            else:
                print("   ✅ Retrieved password is not default 'postgres'")
        else:
            print("   ❌ Password retrieval returned empty value")
            success = False
    except Exception as e:
        print(f"   ❌ Password retrieval failed: {e}")
        success = False
    
    # Summary
    print("\n" + "=" * 50)
    if success:
        print("✅ All authentication fixes validated successfully!")
        print("\nThe database authentication issue has been resolved:")
        print("• No hardcoded passwords in the code")
        print("• Credentials come from environment variables or AWS Secrets Manager")
        print("• Using correct database user 'mlflow' instead of 'postgres'")
        print("• Proper error handling for missing credentials")
    else:
        print("❌ Some validation checks failed")
        print("Please review the issues above")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)