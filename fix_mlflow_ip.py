#!/usr/bin/env python3
"""
Quick fix to replace MLflow service discovery URL with direct IP.
This is a temporary workaround until service discovery is properly configured.
"""

import os
import re
import sys

# Files to update
FILES_TO_UPDATE = [
    "src/api/routes/mlflow_proxy_improved.py",
    "src/services/model_registry.py", 
    "src/utils/mlflow_config.py",
    "src/api/utils/config.py",
    "src/api/routes/health_mlflow.py"
]

# Pattern to replace
OLD_URL = "http://mlflow.hokusai-development.local:5000"
NEW_URL = "http://10.0.1.88:5000"  # Direct IP from infrastructure team

def update_file(filepath):
    """Update MLflow URL in a file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        if OLD_URL in content:
            updated_content = content.replace(OLD_URL, NEW_URL)
            
            # Add comment if not already present
            if "TEMPORARY: Direct IP" not in updated_content:
                # Add comment before the first occurrence
                updated_content = updated_content.replace(
                    f'"{NEW_URL}"',
                    f'"{NEW_URL}"  # TEMPORARY: Direct IP until service discovery fixed',
                    1
                )
            
            with open(filepath, 'w') as f:
                f.write(updated_content)
            
            print(f"✅ Updated: {filepath}")
            return True
        else:
            print(f"⏭️  Skipped: {filepath} (no changes needed)")
            return False
    except Exception as e:
        print(f"❌ Error updating {filepath}: {e}")
        return False

def main():
    """Apply the MLflow IP fix."""
    print("🔧 Applying MLflow Direct IP Fix")
    print(f"   Old URL: {OLD_URL}")
    print(f"   New URL: {NEW_URL}")
    print("-" * 50)
    
    updated_count = 0
    for filepath in FILES_TO_UPDATE:
        if update_file(filepath):
            updated_count += 1
    
    print("-" * 50)
    print(f"✅ Updated {updated_count} files")
    print("\n📝 Next Steps:")
    print("1. Commit these changes")
    print("2. Deploy to ECS")
    print("3. Once service discovery is fixed, revert these changes")
    print("\n⚠️  Remember: This is a TEMPORARY fix!")
    
    # Create a revert script
    revert_script = """#!/usr/bin/env python3
# Revert script to restore service discovery URLs
import os

FILES = %s
OLD_URL = "%s"
NEW_URL = "%s"

for filepath in FILES:
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        content = content.replace(OLD_URL, NEW_URL)
        # Remove temporary comments
        content = content.replace('  # TEMPORARY: Direct IP until service discovery fixed', '')
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"✅ Reverted: {filepath}")
    except Exception as e:
        print(f"❌ Error: {e}")
""" % (FILES_TO_UPDATE, NEW_URL, OLD_URL)
    
    with open("revert_mlflow_ip.py", "w") as f:
        f.write(revert_script)
    
    print("\n✅ Created revert_mlflow_ip.py for later use")

if __name__ == "__main__":
    main()