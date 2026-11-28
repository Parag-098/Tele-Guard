#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
SELECT 'CREATE DATABASE teleguard_mlflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'teleguard_mlflow') \gexec
SQL
