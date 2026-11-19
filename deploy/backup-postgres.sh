#!/usr/bin/env bash
set -euo pipefail

app_dir="/opt/teleguard"
env_file="$app_dir/.env.production"
compose_file="$app_dir/docker-compose.prod.yml"

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a
: "${BACKUP_BUCKET:?Set BACKUP_BUCKET in the protected runtime environment}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
uri="s3://${BACKUP_BUCKET}/postgres/teleguard-${stamp}.dump"

docker compose --project-directory "$app_dir" --env-file "$env_file" -f "$compose_file" \
  exec -T db pg_dump -U teleguard -d teleguard -Fc |
  aws s3 cp - "$uri" --sse AES256
echo "PostgreSQL backup uploaded to $uri"
