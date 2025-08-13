#!/usr/bin/env python3
# Revert script to restore service discovery URLs
import os

FILES = ['src/api/routes/mlflow_proxy_improved.py', 'src/services/model_registry.py', 'src/utils/mlflow_config.py', 'src/api/utils/config.py', 'src/api/routes/health_mlflow.py']
OLD_URL = "http://10.0.1.88:5000"
NEW_URL = "http://mlflow.hokusai-development.local:5000"

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
