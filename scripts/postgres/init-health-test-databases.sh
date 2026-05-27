#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<'SQL'
CREATE DATABASE hokusai_db;
CREATE DATABASE mlflow_db;
SQL
