#!/usr/bin/env python3
"""Create API keys directly in the ECS container database"""

import subprocess
import json

def run_in_ecs(command):
    """Execute command in ECS container"""
    # Get task ARN
    task_arn_cmd = [
        "aws", "ecs", "list-tasks",
        "--cluster", "hokusai-development",
        "--service-name", "hokusai-auth-development",
        "--query", "taskArns[0]",
        "--output", "text"
    ]
    
    task_arn = subprocess.check_output(task_arn_cmd).decode().strip()
    
    if not task_arn or task_arn == "None":
        print("❌ No running auth service tasks found")
        return None
    
    print(f"Using task: {task_arn[-12:]}")
    
    # Execute command in container
    exec_cmd = [
        "aws", "ecs", "execute-command",
        "--cluster", "hokusai-development",
        "--task", task_arn,
        "--container", "auth-service",
        "--command", command,
        "--interactive"
    ]
    
    result = subprocess.run(exec_cmd, capture_output=True, text=True)
    return result

def main():
    print("Creating Platform API Key in ECS...")
    print("=" * 60)
    
    # Python command to run in container
    python_cmd = """python -c '
import os
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from src.models.api_key import APIKey
from src.services.api_key_service import APIKeyService

# Get database URL
db_url = os.environ.get("DATABASE_URL")
db_pass = os.environ.get("DATABASE_PASSWORD")

if db_pass and "@" in db_url and ":@" in db_url:
    parts = db_url.split("@")
    user_part = parts[0].split("://")[-1]
    protocol = parts[0].split("://")[0]
    host_and_db = parts[1]
    db_url = f"{protocol}://{user_part}:{db_pass}@{host_and_db}"

print("Connecting to database...")

try:
    engine = create_engine(db_url)
    session = sessionmaker(bind=engine)()
    api_key_service = APIKeyService(session)
    
    # Check if table exists
    inspector = inspect(engine)
    if "api_keys" not in inspector.get_table_names():
        print("Creating api_keys table...")
        os.system("cd /app && alembic upgrade head")
    
    # Create platform key
    key_cfg = {
        "user_id": "system",
        "service_id": "platform", 
        "key_name": "Platform MLflow Test Key",
        "scopes": ["read", "write"],
        "environment": "production",
        "rate_limit_per_hour": 10000,
        "billing_plan": "pro"
    }
    
    print("Creating API key...")
    print("Service:", key_cfg["service_id"])
    print("Name:", key_cfg["key_name"])
    
    # Check if exists
    existing = session.query(APIKey).filter(
        APIKey.service_id == "platform",
        APIKey.user_id == "system",
        APIKey.key_name == key_cfg["key_name"],
        APIKey.is_active == True
    ).first()
    
    if existing:
        print("Key already exists with ID:", existing.key_id)
        # Generate a new one anyway
        key_cfg["key_name"] = key_cfg["key_name"] + " v2"
    
    api_key, info = api_key_service.generate_api_key(**key_cfg)
    print("")
    print("=" * 60)
    print("SUCCESS! New API Key Created:")
    print("=" * 60)
    print("API Key:", api_key)
    print("Key ID:", info["key_id"])
    print("Service:", info["service_id"])
    print("=" * 60)
    print("SAVE THIS KEY - It cannot be retrieved later!")
    
    session.commit()
    session.close()
    
except Exception as e:
    print("ERROR:", str(e))
    import traceback
    traceback.print_exc()
'"""
    
    result = run_in_ecs(python_cmd)
    
    if result and result.returncode == 0:
        print("\n✅ Check the output above for your new API key")
    else:
        print("\n❌ Failed to create API key")
        if result:
            print("Error:", result.stderr)

if __name__ == "__main__":
    main()