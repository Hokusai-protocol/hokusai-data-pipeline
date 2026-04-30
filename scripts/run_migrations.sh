#!/bin/bash
# Apply all pending Hokusai database migrations using alembic.
# DATABASE_URL must be set (read by migrations/env.py).
set -euo pipefail

cd /app
exec alembic upgrade head
