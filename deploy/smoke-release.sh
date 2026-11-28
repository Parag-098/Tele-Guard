#!/usr/bin/env bash
# Test existing local images with a production-shaped Compose project and no cloud calls.
set -Eeuo pipefail
umask 077
repo=$(cd "$(dirname "$0")/.." && pwd)
json_python=python3
if ! "$json_python" --version >/dev/null 2>&1; then json_python=python; fi
stage=$(mktemp -d)
project="teleguard-smoke-$(basename "$stage" | tr -cd 'a-z0-9')"
mkdir -p "$stage/deploy" "$stage/deploy-state/models"
cp "$repo/docker-compose.prod.yml" "$stage/"
cp "$repo/deploy/"{Caddyfile,Caddyfile.smoke,compose.smoke.yml,init-mlflow-db.sh} "$stage/deploy/"
chmod +x "$stage/deploy/init-mlflow-db.sh"
cp "$repo/.env.production.example" "$stage/.env.production"
chmod 0600 "$stage/.env.production"
export TG_API_IMAGE="${TG_API_IMAGE:-teleguard-api:release}"
export TG_WEB_IMAGE="${TG_WEB_IMAGE:-teleguard-web:release}"

compose() {
  docker compose -p "$project" --project-directory "$stage" --env-file "$stage/.env.production" \
    -f "$stage/docker-compose.prod.yml" -f "$stage/deploy/compose.smoke.yml" "$@"
}
cleanup() {
  local code=$?
  if (( code != 0 )); then compose ps; compose logs --tail 35; fi
  compose down --timeout 20 || true
  rm -rf -- "$stage"
}
trap cleanup EXIT
compose config --quiet
compose up -d --pull never --wait --wait-timeout 240
compose exec -T api python -m app.bootstrap
endpoint="http://$(compose port proxy 80)"
curl --fail --silent --show-error "$endpoint/" >/dev/null
curl --fail --silent --show-error "$endpoint/api/ready"
printf '\n'

api_token=$(curl --fail --silent --show-error "$endpoint/api/auth/login" \
  -H 'Content-Type: application/json' \
  --data '{"username":"admin","password":"one-time-bootstrap-password-at-least-12-characters"}' |
  "$json_python" -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
authorization="Authorization: Bearer $api_token"
curl --fail --silent --show-error "$endpoint/api/events" -H "$authorization" -H 'Content-Type: application/json' \
  --data '{"event_id":"release-smoke-001","event_type":"CALL","event_time":"2026-01-15T10:00:00Z","subscriber_id":"sub_smoke", "duration_seconds":120}' |
  "$json_python" -c 'import json,sys; value=json.load(sys.stdin)["prediction"]["risk_score"]; assert isinstance(value,(int,float)); print(value)'
curl --fail --silent --show-error "$endpoint/api/system/health" -H "$authorization" |
  "$json_python" -c 'import json,sys; assert json.load(sys.stdin).get("status") == "ok"'
compose exec -T api python - <<'PY'
import json
from pathlib import Path

import mlflow

mlflow.set_experiment("release-backup-smoke")
with mlflow.start_run() as run:
    mlflow.log_dict({"proof": "release-smoke"}, "fixture.json")
path = Path(mlflow.tracking.MlflowClient().download_artifacts(run.info.run_id, "fixture.json"))
assert json.loads(path.read_text()) == {"proof": "release-smoke"}
print("Verified local MLflow artifact round trip", run.info.run_id)
PY
compose restart api worker
compose up -d --pull never --wait --wait-timeout 240
curl --fail --silent --show-error "$endpoint/api/ready"
printf '\n'
compose exec -T db psql -U teleguard -d teleguard -At -v ON_ERROR_STOP=1 \
  -c "SELECT count(*) FROM predictions WHERE event_id='release-smoke-001'" | grep -qx 1
compose exec -T api python -c 'from pathlib import Path; print("Container model cache:", sorted(p.name for p in Path("/app/artifacts").iterdir()))'
find "$stage/deploy-state/models" -maxdepth 2 -type f -printf 'Host model cache: %P\n'

if [[ "${RUN_BROWSER_SMOKE:-0}" == 1 ]]; then
  (
    cd "$repo/frontend"
    TEST_ADMIN_USERNAME=admin TEST_ADMIN_PASSWORD=one-time-bootstrap-password-at-least-12-characters \
      PLAYWRIGHT_BASE_URL="$endpoint" npx playwright test --grep 'administrator can inspect delayed labels and controlled model serving'
  )
fi

# The Docker Compose project name is explicit even when the backup CLI invokes it separately.
export COMPOSE_PROJECT_NAME="$project"
TELEGUARD_APP_DIR="$stage" TELEGUARD_BACKUP_COMPOSE_OVERRIDE="$stage/deploy/compose.smoke.yml" \
  bash "$repo/deploy/backup-postgres.sh" --local "$stage/backup.tar.gz"
echo 'Backup archive members:'
tar -tzf "$stage/backup.tar.gz"
echo 'Model cache archive members:'
tar -xOf "$stage/backup.tar.gz" model-cache.tar.gz | tar -tzf -
checksum=$(sha256sum "$stage/backup.tar.gz" | cut -d' ' -f1)
TELEGUARD_API_IMAGE="$TG_API_IMAGE" \
TELEGUARD_RESTORE_IMAGE="${TG_POSTGRES_IMAGE:-postgres:16-alpine}" \
TELEGUARD_RESTORE_SMOKE_ADMIN_USERNAME=admin \
TELEGUARD_RESTORE_SMOKE_ADMIN_PASSWORD=one-time-bootstrap-password-at-least-12-characters \
  bash "$repo/deploy/restore-postgres.sh" "$stage/backup.tar.gz" "$checksum"
