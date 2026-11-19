#!/usr/bin/env bash
set -euo pipefail

release_tag="${1:?release tag or commit SHA required}"
app_dir="/opt/teleguard"
compose_file="$app_dir/docker-compose.prod.yml"
env_file="$app_dir/.env.production"

if [[ ! -f "$env_file" || ! -f "$compose_file" ]]; then
  echo "TeleGuard deployment files are missing under $app_dir" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a
export RELEASE_TAG="$release_tag"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker compose --project-directory "$app_dir" --env-file "$env_file" -f "$compose_file" pull
docker compose --project-directory "$app_dir" --env-file "$env_file" -f "$compose_file" up -d --remove-orphans

for attempt in $(seq 1 36); do
  if curl --fail --silent --show-error "https://${TG_DOMAIN}/api/health" >/dev/null; then
    echo "TeleGuard release $release_tag is healthy at https://${TG_DOMAIN}"
    exit 0
  fi
  sleep 10
done

docker compose --project-directory "$app_dir" --env-file "$env_file" -f "$compose_file" ps
docker compose --project-directory "$app_dir" --env-file "$env_file" -f "$compose_file" logs --tail=100 api mlflow proxy
echo "Health check failed for release $release_tag" >&2
exit 1
