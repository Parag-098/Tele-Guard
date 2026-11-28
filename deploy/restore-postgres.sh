#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

archive="${1:?pass the downloaded backup archive}"
expected="${2:?pass the SHA256 from the backup receipt}"
[[ "$expected" =~ ^[a-f0-9]{64}$ ]] || exit 2
printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status
stage=$(mktemp -d)
container="teleguard-restore-$(basename "$stage" | tr -cd 'A-Za-z0-9-')"
api_container="${container}-api"
created=0
api_created=0
cleanup() {
  if [[ "$api_created" == 1 ]]; then docker rm -f "$api_container" >/dev/null; fi
  if [[ "$created" == 1 ]]; then docker rm -f "$container" >/dev/null; fi
  rm -rf -- "$stage"
}
trap cleanup EXIT

mapfile -t entries < <(tar -tzf "$archive")
for entry in "${entries[@]}"; do
  [[ "$entry" =~ ^(application[.]dump|mlflow[.]dump|model-cache[.]tar[.]gz|manifest[.]tsv|SHA256SUMS)$ ]] ||
    { echo 'Unexpected backup member.' >&2; exit 2; }
done
[[ $(printf '%s\n' "${entries[@]}" | sort -u | wc -l) -eq "${#entries[@]}" ]] || exit 2
tar --extract --gzip --file "$archive" --directory "$stage" --no-same-owner --no-same-permissions
for name in application.dump model-cache.tar.gz manifest.tsv SHA256SUMS; do
  [[ -f "$stage/$name" && ! -L "$stage/$name" ]] || exit 2
done
if [[ -e "$stage/mlflow.dump" ]]; then
  [[ -f "$stage/mlflow.dump" && ! -L "$stage/mlflow.dump" ]] || exit 2
fi
mkdir "$stage/model-cache"
while IFS= read -r member; do
  [[ "$member" != /* && "/$member/" != *"/../"* ]] || { echo 'Unsafe model-cache archive path.' >&2; exit 2; }
done < <(tar -tzf "$stage/model-cache.tar.gz")
tar --extract --gzip --file "$stage/model-cache.tar.gz" --directory "$stage/model-cache" \
  --no-same-owner --no-same-permissions
if find "$stage/model-cache" -type l -print -quit | grep -q .; then
  echo 'Model cache archive must not contain symbolic links.' >&2
  exit 2
fi
if grep -Ev '^[a-f0-9]{64}([ ]{2}| [*])[ ]?(application[.]dump|mlflow[.]dump|model-cache[.]tar[.]gz|manifest[.]tsv)$' "$stage/SHA256SUMS" >/dev/null; then
  echo 'Invalid checksum manifest.' >&2
  exit 2
fi
(
  cd "$stage"
  sha256sum --check --strict SHA256SUMS
)
# Rehearse recovery in a disposable server without a network, published port or production mount.
docker run -d --name "$container" --network none --label teleguard.purpose=restore-test \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_USER=teleguard -e POSTGRES_DB=teleguard \
  "${TELEGUARD_RESTORE_IMAGE:-postgres:16-alpine}" >/dev/null
created=1
ready=0
for attempt in $(seq 1 30); do
  if docker exec "$container" pg_isready -q -h localhost -U teleguard -d teleguard; then ready=1; break; fi
  sleep 2
done
[[ "$ready" == 1 ]] || { echo 'Restore test PostgreSQL did not start.' >&2; exit 1; }

docker exec -i "$container" pg_restore --exit-on-error --no-owner --no-acl -U teleguard -d teleguard < "$stage/application.dump"
mlflow_db=$(awk -F '\t' '$1 == "mlflow_database" {print $2}' "$stage/manifest.tsv")
case "$mlflow_db" in
  teleguard_mlflow)
    docker exec "$container" createdb -U teleguard teleguard_mlflow
    docker exec -i "$container" pg_restore --exit-on-error --no-owner --no-acl \
      -U teleguard -d teleguard_mlflow < "$stage/mlflow.dump"
    ;;
  teleguard) ;;
  *) exit 2 ;;
esac
model_version=$(awk -F '\t' '$1 == "champion" {print $2}' "$stage/manifest.tsv")
artifact_path=$(docker exec "$container" psql -AXt -v ON_ERROR_STOP=1 -U teleguard -d teleguard \
  -c "select artifact_path from model_runs where version = '$model_version'")
actual_model=$(docker exec "$container" psql -AXt -v ON_ERROR_STOP=1 -U teleguard -d teleguard \
  -c "select version from mlops_records where kind = 'active_model' order by id desc limit 1")
[[ "$model_version" == "$actual_model" ]] || { echo 'Restored champion does not match backup metadata.' >&2; exit 1; }
artifact_basename=${artifact_path##*/}
if [[ -z "$artifact_basename" || ! -f "$stage/model-cache/$artifact_basename" ]]; then
  printf 'Restored champion artifact path is missing from the model cache archive: %s\n' "$artifact_path" >&2
  find "$stage/model-cache" -type f -printf 'Restored model-cache file: %P\n' >&2
  exit 1
fi

docker exec "$container" psql -AXt -F ' ' -v ON_ERROR_STOP=1 -U teleguard -d teleguard \
  -c 'SELECT count(*) AS events FROM events' \
  -c 'SELECT count(*) AS predictions FROM predictions'
docker exec "$container" psql -AXt -F ' ' -v ON_ERROR_STOP=1 -U teleguard -d "$mlflow_db" \
  -c 'SELECT count(*) AS mlflow_runs FROM runs'
printf 'Verified isolated PostgreSQL restoration for champion %s\n' "$actual_model"

# Start the exact API image beside the isolated restored database, with only the
# restored model cache mounted read-only. Sharing the restore container's
# network namespace keeps PostgreSQL and the API unreachable from the host.
api_image="${TELEGUARD_API_IMAGE:-${TG_API_IMAGE:-teleguard-api:local}}"
model_cache_source="$stage/model-cache"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) model_cache_source=$(cygpath -w "$model_cache_source") ;;
esac
docker run -d --name "$api_container" --network "container:$container" \
  --label teleguard.purpose=restore-serving-smoke \
  --mount "type=bind,source=$model_cache_source,target=/app/artifacts,readonly" \
  -e TG_DATABASE_URL=postgresql+psycopg://teleguard@127.0.0.1:5432/teleguard \
  -e TG_SECRET_KEY=local-restore-smoke-secret-at-least-32-bytes \
  -e TG_MODEL_PATH=/app/artifacts/fraud-model.joblib \
  "$api_image" >/dev/null
api_created=1
api_ready=0
for attempt in $(seq 1 45); do
  if docker exec "$api_container" python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2)' \
    >/dev/null 2>&1; then api_ready=1; break; fi
  if [[ $(docker inspect -f '{{.State.Running}}' "$api_container" 2>/dev/null || true) != true ]]; then break; fi
  sleep 2
done
[[ "$api_ready" == 1 ]] || {
  docker logs --tail 60 "$api_container" >&2
  echo 'API did not start against the restored database and model cache.' >&2
  exit 1
}

if [[ -n "${TELEGUARD_RESTORE_SMOKE_ADMIN_PASSWORD:-}" ]]; then
  docker exec -i \
    -e TG_RESTORE_ADMIN_USERNAME="${TELEGUARD_RESTORE_SMOKE_ADMIN_USERNAME:-admin}" \
    -e TG_RESTORE_ADMIN_PASSWORD="$TELEGUARD_RESTORE_SMOKE_ADMIN_PASSWORD" \
    -e TG_RESTORE_EXPECTED_CHAMPION="$model_version" \
    "$api_container" python - <<'PY'
import json
import os
import urllib.request
from uuid import uuid4

def post(path, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"http://127.0.0.1:8000/api{path}",
        data=json.dumps(payload).encode(), headers=headers, method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)

session = post("/auth/login", {
    "username": os.environ["TG_RESTORE_ADMIN_USERNAME"],
    "password": os.environ["TG_RESTORE_ADMIN_PASSWORD"],
})
event_id = f"restored-api-smoke-{uuid4().hex}"
result = post("/events", {
    "event_id": event_id, "event_type": "CALL", "event_time": "2026-01-15T10:00:00Z",
    "subscriber_id": f"restored-subscriber-{uuid4().hex}", "duration_seconds": 90,
}, session["access_token"])
prediction = result["prediction"]
assert prediction["model_version"] == os.environ["TG_RESTORE_EXPECTED_CHAMPION"]
assert isinstance(prediction["risk_score"], (int, float))
print("Restored API served an authenticated prediction", event_id, prediction["model_version"])
PY
fi
