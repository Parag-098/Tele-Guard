#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

app_dir="${TELEGUARD_APP_DIR:-/opt/teleguard}"
env_file="$app_dir/.env.production"
releases="$app_dir/releases"
state="$app_dir/deploy-state"
pointer="$state/current-release"
previous_pointer="$state/previous-release"

[[ -f "$env_file" && ! -L "$env_file" && $(stat -c '%u:%a' "$env_file") == "$(id -u):600" ]] ||
  { echo "Expected a mode-600 runtime configuration owned by the deployment principal at $env_file" >&2; exit 2; }
mountpoint -q "$state" || { echo "Persistent application storage is not mounted at $state" >&2; exit 2; }
install -d -m 0750 "$releases"
exec 9>"$state/release.lock"
flock -n 9 || { echo 'Another release or backup is already running' >&2; exit 2; }

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a
: "${AWS_REGION:?}" "${ECR_REGISTRY:?}" "${TG_DOMAIN:?}"
[[ "$TG_DOMAIN" =~ ^[A-Za-z0-9.-]+$ && "$ECR_REGISTRY" =~ ^[A-Za-z0-9.-]+$ ]] ||
  { echo 'Invalid deployment domain or registry' >&2; exit 2; }

read_pointer() {
  local path="$1" value=""
  if [[ -f "$path" ]]; then
    read -r value < "$path"
    [[ "$value" =~ ^[a-f0-9]{40}-[a-f0-9]{64}$ ]] || return 2
  fi
  printf '%s' "$value"
}

publish_pointer() {
  local path="$1" value="$2" temporary
  temporary=$(mktemp "$state/.release-pointer.XXXXXX")
  printf '%s\n' "$value" > "$temporary"
  mv -fT -- "$temporary" "$path"
}

activate_config() {
  local release_id="$1" revision key value repository
  export TG_RELEASE_DIR="$releases/$release_id"
  revision="${release_id%%-*}"
  compose_file="$TG_RELEASE_DIR/docker-compose.prod.yml"
  [[ -f "$compose_file" && -f "$TG_RELEASE_DIR/release-image.env" && -f "$TG_RELEASE_DIR/deploy/Caddyfile" ]] || return 2
  unset TG_API_IMAGE TG_WEB_IMAGE TG_POSTGRES_IMAGE TG_CADDY_IMAGE
  while IFS='=' read -r key value; do
    case "$key" in
      TG_API_IMAGE) [[ ! -v TG_API_IMAGE ]] || return 2; repository="$ECR_REGISTRY/teleguard-api" ;;
      TG_WEB_IMAGE) [[ ! -v TG_WEB_IMAGE ]] || return 2; repository="$ECR_REGISTRY/teleguard-web" ;;
      TG_POSTGRES_IMAGE) [[ ! -v TG_POSTGRES_IMAGE ]] || return 2; repository=postgres; value="${value#docker.io/library/}" ;;
      TG_CADDY_IMAGE) [[ ! -v TG_CADDY_IMAGE ]] || return 2; repository=caddy; value="${value#docker.io/library/}" ;;
      RELEASE_TAG) [[ "$value" == "$revision" ]] || return 2; continue ;;
      *) return 2 ;;
    esac
    local prefix="$repository@sha256:"
    [[ "$value" == "$prefix"* && "${value#"$prefix"}" =~ ^[a-f0-9]{64}$ ]] || return 2
    export "$key=$value"
  done < "$TG_RELEASE_DIR/release-image.env"
  [[ -v TG_API_IMAGE && -v TG_WEB_IMAGE && -v TG_POSTGRES_IMAGE && -v TG_CADDY_IMAGE ]] || return 2
  export RELEASE_TAG="$revision"
}

compose() {
  docker compose --project-directory "$app_dir" --env-file "$env_file" -f "$compose_file" "$@"
}

web_ready() {
  curl --fail --silent --show-error --max-time 8 "https://$TG_DOMAIN/api/ready" >/dev/null 2>&1 &&
    curl --fail --silent --show-error --max-time 8 "https://$TG_DOMAIN/" >/dev/null 2>&1
}

start_config() {
  compose up -d --wait --wait-timeout 240 || return
  local attempt
  for attempt in $(seq 1 18); do
    web_ready && return 0
    sleep 5
  done
  return 1
}

database_revision() {
  compose exec -T db psql -U teleguard -d teleguard -AtX -v ON_ERROR_STOP=1 \
    -c 'select version_num from alembic_version order by version_num' 2>/dev/null
}

image_revision() {
  docker run --rm --network none --entrypoint alembic "$TG_API_IMAGE" heads |
    awk '$2 == "(head)" {print $1}' | sort
}

restore_previous() {
  local release_id="$1" installed expected
  activate_config "$release_id" || return
  compose pull || return
  installed=$(database_revision) || return
  expected=$(image_revision) || return
  if [[ -z "$installed" || "$expected" != "$installed" ]]; then
    echo 'Database revision differs from the rollback image. Restore the pre-release backup in isolation before recovery.' >&2
    return 2
  fi
  start_config
}

install_operations() {
  local release_dir="$1"
  install -m 0755 "$release_dir/deploy/operations-metrics.sh" /usr/local/sbin/teleguard-operations-metrics
  install -m 0755 "$release_dir/deploy/backup-postgres.sh" /usr/local/sbin/teleguard-backup-postgres
  install -m 0755 "$release_dir/deploy/restore-postgres.sh" /usr/local/sbin/teleguard-restore-postgres
  install -m 0644 "$release_dir"/deploy/teleguard-{backup,metrics}.{service,timer} /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now teleguard-metrics.timer teleguard-backup.timer
}

current=$(read_pointer "$pointer")
case "${1:-}" in
  --install)
    staging="${2:?staging directory required}"
    revision="${3:?release revision required}"
    digest="${4:?bundle checksum required}"
    [[ "$revision" =~ ^[a-f0-9]{40}$ && "$digest" =~ ^[a-f0-9]{64}$ ]] || exit 2
    target="$revision-$digest"
    [[ -f "$staging/docker-compose.prod.yml" && -f "$staging/release-image.env" && -d "$staging/deploy" ]] || exit 2
    if [[ ! -d "$releases/$target" ]]; then
      install -d -m 0750 "$releases/$target"
      cp -- "$staging/docker-compose.prod.yml" "$staging/release-image.env" "$releases/$target/"
      cp -a -- "$staging/deploy" "$releases/$target/"
    fi
    activate_config "$target"
    compose config --quiet
    aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
    compose pull
    if [[ -n "$current" && "$current" != "$target" ]]; then
      # Reuse the release lock. A pre-release snapshot has to succeed before migrations.
      TELEGUARD_BACKUP_LOCK_HELD=1 bash "$releases/$current/deploy/backup-postgres.sh" --upload
    fi
    if ! start_config; then
      compose ps || true
      if [[ -n "$current" && "$current" != "$target" ]] && restore_previous "$current"; then
        echo "Candidate failed readiness. Restored $current on the unchanged database schema." >&2
      else
        echo 'Candidate failed readiness. No verified automatic rollback is available.' >&2
      fi
      exit 1
    fi
    install_operations "$TG_RELEASE_DIR"
    if [[ -n "$current" && "$current" != "$target" ]]; then publish_pointer "$previous_pointer" "$current"; fi
    publish_pointer "$pointer" "$target"
    echo "TeleGuard release $target is healthy at https://$TG_DOMAIN"
    ;;
  --rollback)
    target="${2:-$(read_pointer "$previous_pointer")}"
    [[ "$target" =~ ^[a-f0-9]{40}-[a-f0-9]{64}$ && "$target" != "$current" ]] || exit 2
    aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
    restore_previous "$target"
    install_operations "$TG_RELEASE_DIR"
    publish_pointer "$pointer" "$target"
    if [[ -n "$current" ]]; then publish_pointer "$previous_pointer" "$current"; fi
    echo "TeleGuard rollback $target is healthy at https://$TG_DOMAIN"
    ;;
  *)
    # Existing pre-bundle hosts can still deploy a commit-tagged Compose release.
    legacy_tag="${1:?use --install, --rollback or a legacy tag}"
    [[ ! -f "$pointer" && "$legacy_tag" =~ ^[A-Za-z0-9._-]+$ ]] || exit 2
    compose_file="$app_dir/docker-compose.prod.yml"
    export RELEASE_TAG="$legacy_tag"
    unset TG_API_IMAGE TG_WEB_IMAGE
    aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
    compose pull
    start_config
    echo "TeleGuard legacy release $legacy_tag is healthy at https://$TG_DOMAIN"
    ;;
esac
