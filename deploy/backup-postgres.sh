#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

app_dir="${TELEGUARD_APP_DIR:-/opt/teleguard}"
state="$app_dir/deploy-state"
env_file="$app_dir/.env.production"
mode="${1:---upload}"

[[ "$mode" == --upload || "$mode" == --local ]] || { echo 'Use --upload or --local OUTPUT.tar.gz' >&2; exit 2; }
[[ -f "$env_file" && ! -L "$env_file" && $(stat -c '%u:%a' "$env_file") == "$(id -u):600" ]] ||
  { echo 'Backup requires a protected runtime configuration.' >&2; exit 2; }
if [[ "$mode" == --upload ]]; then
  mountpoint -q "$state" || { echo 'Persistent data mount is missing.' >&2; exit 2; }
fi
lock_dir=""
if [[ "${TELEGUARD_BACKUP_LOCK_HELD:-}" != 1 ]]; then
  if command -v flock >/dev/null 2>&1; then
    exec 9>"$state/release.lock"
    flock -n 9 || { echo 'A release or backup is already running.' >&2; exit 2; }
  else
    # Git Bash lacks flock. Keep the local acceptance path mutually exclusive
    # with an atomic directory lock; Linux deployments use the shared flock.
    lock_dir="$state/release.lock.d"
    mkdir -m 0700 -- "$lock_dir" 2>/dev/null || {
      echo 'A release or backup is already running.' >&2
      exit 2
    }
    trap 'rmdir -- "$lock_dir" 2>/dev/null || true' EXIT
  fi
fi

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a
: "${MLFLOW_BACKEND_STORE_URI:?}"
mlflow_db="${MLFLOW_BACKEND_STORE_URI##*/}"
[[ "$mlflow_db" == teleguard || "$mlflow_db" == teleguard_mlflow ]] ||
  { echo 'Unsupported MLflow database name for the backup procedure.' >&2; exit 2; }

compose_files=(-f "$app_dir/docker-compose.prod.yml")
release='legacy'
if [[ -f "$state/current-release" ]]; then
  read -r release < "$state/current-release"
  [[ "$release" =~ ^[a-f0-9]{40}-[a-f0-9]{64}$ ]] || exit 2
  export TG_RELEASE_DIR="$app_dir/releases/$release"
  compose_files=(-f "$TG_RELEASE_DIR/docker-compose.prod.yml")
fi
# The backup drill may supply a production-shaped Compose override without cloud logging.
if [[ "$mode" == --local && -n "${TELEGUARD_BACKUP_COMPOSE_OVERRIDE:-}" ]]; then
  compose_files+=(-f "$TELEGUARD_BACKUP_COMPOSE_OVERRIDE")
fi
compose() {
  docker compose --project-directory "$app_dir" --env-file "$env_file" "${compose_files[@]}" "$@"
}

stage=$(mktemp -d "$state/.backup.XXXXXX")
cleanup() {
  rm -rf -- "$stage"
  if [[ -n "${lock_dir:-}" ]]; then rmdir -- "$lock_dir" 2>/dev/null || true; fi
}
trap cleanup EXIT
stamp=$(date -u +%Y%m%dT%H%M%SZ)
members=(application.dump model-cache.tar.gz manifest.tsv)
compose exec -T db pg_dump -U teleguard -d teleguard --no-owner --no-acl -Fc > "$stage/application.dump"
if [[ "$mlflow_db" != teleguard ]]; then
  compose exec -T db pg_dump -U teleguard -d "$mlflow_db" --no-owner --no-acl -Fc > "$stage/mlflow.dump"
  members+=(mlflow.dump)
fi
if [[ -d "$state/models" ]]; then
  tar -czf "$stage/model-cache.tar.gz" -C "$state/models" .
else
  tar -czf "$stage/model-cache.tar.gz" --files-from /dev/null
fi
printf 'created_utc\t%s\nrelease\t%s\nmlflow_database\t%s\n' "$stamp" "$release" "$mlflow_db" > "$stage/manifest.tsv"
compose exec -T db psql -U teleguard -d teleguard -AXt -F $'\t' -v ON_ERROR_STOP=1 \
  -c "select 'schema', version_num from alembic_version order by version_num" >> "$stage/manifest.tsv"
compose exec -T db psql -U teleguard -d teleguard -AXt -F $'\t' -v ON_ERROR_STOP=1 \
  -c "select 'champion', version from mlops_records where kind = 'active_model' order by id desc limit 1" \
  >> "$stage/manifest.tsv"

(
  cd "$stage"
  sha256sum "${members[@]}" > SHA256SUMS
  tar -czf backup.tar.gz "${members[@]}" SHA256SUMS
)
checksum=$(sha256sum "$stage/backup.tar.gz" | cut -d' ' -f1)

if [[ "$mode" == --upload ]]; then
  : "${BACKUP_BUCKET:?}" "${AWS_REGION:?}"
  uri="s3://$BACKUP_BUCKET/postgres/teleguard-$stamp-$checksum.tar.gz"
  aws s3 cp --region "$AWS_REGION" --only-show-errors --sse AES256 "$stage/backup.tar.gz" "$uri"
  printf 'Backup URI %s SHA256 %s\n' "$uri" "$checksum"
else
  output="${2:?output archive required}"
  [[ ! -e "$output" ]] || { echo 'Backup destination already exists.' >&2; exit 2; }
  cp --no-clobber -- "$stage/backup.tar.gz" "$output"
  printf 'Backup path %s SHA256 %s\n' "$output" "$checksum"
fi
