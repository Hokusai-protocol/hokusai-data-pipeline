#!/usr/bin/env python3
"""Create an API key with platform permissions for the Hokusai data pipeline."""

import sys
import os
import secrets
import uuid
from datetime import datetime, timezone
import bcrypt
import psycopg2
from psycopg2.extras import Json
import string
from pathlib import Path

# Load environment variables from .env file if it exists
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

def generate_api_key():
    """Generate a secure API key with the hk_live_ prefix."""
    # Generate random part (40 characters)
    alphabet = string.ascii_letters + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(40))
    return f"hk_live_{random_part}"

def hash_api_key(api_key: str) -> str:
    """Hash an API key using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(api_key.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def create_platform_api_key(key_name: str = "Platform API Key", user_id: str = "platform"):
    """Create an API key with platform-level permissions."""
    
    print(f"Creating API key with platform permissions...")
    print(f"Key name: {key_name}")
    print(f"User ID: {user_id}")
    print("-" * 50)
    
    try:
        # Generate key components
        key_id = str(uuid.uuid4())
        full_key = generate_api_key()
        key_hash = hash_api_key(full_key)
        key_prefix = full_key[:13] + "***"  # Show first 13 chars (hk_live_abc***)
        
        # Database connection parameters
        # Use HOKUSAI_ prefixed env vars first, then fall back to standard names
        # Default to local docker-compose credentials if not set
        db_params = {
            'host': os.getenv('HOKUSAI_DB_HOST', os.getenv('DATABASE_HOST', 'localhost')),
            'port': os.getenv('HOKUSAI_DB_PORT', os.getenv('DATABASE_PORT', '5432')),
            'database': os.getenv('HOKUSAI_DB_NAME', os.getenv('DATABASE_NAME', 'mlflow_db')),
            'user': os.getenv('HOKUSAI_DB_USER', os.getenv('DATABASE_USER', 'mlflow')),
            'password': os.getenv('HOKUSAI_DB_PASSWORD', os.getenv('DATABASE_PASSWORD', os.getenv('DB_PASSWORD', 'mlflow_password')))
        }
        
        # Connect to database and insert the API key
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        
        # Create the API keys table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id UUID PRIMARY KEY,
                key_hash VARCHAR(255) NOT NULL,
                key_prefix VARCHAR(50) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                expires_at TIMESTAMP WITH TIME ZONE,
                last_used_at TIMESTAMP WITH TIME ZONE,
                is_active BOOLEAN DEFAULT true,
                rate_limit_per_hour INTEGER DEFAULT 1000,
                allowed_ips TEXT[],
                environment VARCHAR(50) DEFAULT 'production',
                metadata JSONB
            );
        """)
        
        # Insert the new API key
        cursor.execute("""
            INSERT INTO api_keys (
                key_id, key_hash, key_prefix, user_id, name, 
                created_at, expires_at, is_active, rate_limit_per_hour,
                environment, metadata
            ) VALUES (
                %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, 
                %s, %s
            )
        """, (
            key_id,
            key_hash,
            key_prefix,
            user_id,
            key_name,
            datetime.now(timezone.utc),
            None,  # No expiration
            True,
            10000,  # High rate limit for platform
            'production',
            Json({'permissions': 'platform'})
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n✅ API Key Created Successfully!")
        print("=" * 50)
        print(f"API Key: {full_key}")
        print("=" * 50)
        print(f"\nKey ID: {key_id}")
        print(f"Name: {key_name}")
        print(f"User ID: {user_id}")
        print(f"Created At: {datetime.now(timezone.utc)}")
        print(f"Rate Limit: 10000 requests/hour")
        print(f"Expires: Never")
        
        print("\n⚠️  IMPORTANT: Save this API key securely. It will not be shown again!")
        print("\n📝 Usage examples:")
        print(f"   export HOKUSAI_API_KEY={full_key}")
        print(f"   curl -H 'Authorization: Bearer {full_key}' https://api.hokus.ai/api/v1/health")
        
        return full_key
        
    except Exception as e:
        print(f"\n❌ Error creating API key: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            print("Usage: python create_api_key.py [key_name] [user_id]")
            print("\nCreate an API key with platform permissions.")
            print("\nArguments:")
            print("  key_name  - Optional name for the API key (default: 'Platform API Key')")
            print("  user_id   - Optional user ID (default: 'platform')")
            print("\nExample:")
            print("  python create_api_key.py 'Production Service Key' 'platform-service'")
            sys.exit(0)
    
    # Get parameters from command line or use defaults
    key_name = sys.argv[1] if len(sys.argv) > 1 else "Platform API Key"
    user_id = sys.argv[2] if len(sys.argv) > 2 else "platform"
    
    create_platform_api_key(key_name, user_id)


if __name__ == "__main__":
    main()