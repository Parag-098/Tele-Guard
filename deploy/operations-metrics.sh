#!/usr/bin/env bash
set -Eeuo pipefail
app_dir="${TELEGUARD_APP_DIR:-/opt/teleguard}"
state="$app_dir/deploy-state"
env_file="$app_dir/.env.production"
[[ -f "$env_file" && ! -L "$env_file" && $(stat -c '%u:%a' "$env_file") == "$(id -u):600" ]] || exit 2
mountpoint -q "$state"
read -r release < "$state/current-release"
[[ "$release" =~ ^[a-f0-9]{40}-[a-f0-9]{64}$ ]] || exit 2
export TG_RELEASE_DIR="$app_dir/releases/$release"
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

token=$(curl --fail --silent --show-error --max-time 2 -X PUT \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' http://169.254.169.254/latest/api/token)
instance_id=$(curl --fail --silent --show-error --max-time 2 -H "X-aws-ec2-metadata-token: $token" \
  http://169.254.169.254/latest/meta-data/instance-id)
[[ "$instance_id" =~ ^i-[a-f0-9]+$ ]] || exit 2

readiness=0
worker=0
queue_minutes=null
if curl --fail --silent --show-error --max-time 8 "https://${TG_DOMAIN:?}/api/ready" >/dev/null 2>&1; then readiness=1; fi
compose=(docker compose --project-directory "$app_dir" --env-file "$env_file" -f "$TG_RELEASE_DIR/docker-compose.prod.yml")
if result=$("${compose[@]}" exec -T db psql -U teleguard -d teleguard -AXt -F ' ' -v ON_ERROR_STOP=1 \
    -c "SELECT CASE WHEN EXISTS (SELECT 1 FROM service_heartbeats WHERE service='worker' AND status='healthy' AND updated_at > now() - interval '90 seconds') THEN 1 ELSE 0 END, COALESCE((EXTRACT(EPOCH FROM (now() - min(created_at)))/60)::int, 0) FROM mlops_jobs WHERE status='queued'" 2>/dev/null); then
  read -r worker queue_minutes <<< "$result"
fi
drift=null
fallback=null
monitor_lag=null
if result=$("${compose[@]}" exec -T db psql -U teleguard -d teleguard -AXt -F ' ' -v ON_ERROR_STOP=1 \
    -c "SELECT COALESCE(MAX(CASE WHEN (result::jsonb->>'new_drift_alert')='true' THEN 1 ELSE 0 END) FILTER (WHERE end_at > now() - interval '1 hour'),0), COALESCE(GREATEST(EXTRACT(EPOCH FROM (now()-max(end_at)))::int/60,0)::text,'null') FROM monitor_windows" \
    -c "SELECT COALESCE(ROUND(100.0 * count(*) FILTER (WHERE actual_role <> 'canary')/NULLIF(count(*),0),2)::text,'null') FROM served_snapshots WHERE assigned_role='canary' AND observed_at > now() - interval '15 minutes'" 2>/dev/null); then
  {
    read -r drift monitor_lag
    read -r fallback
  } <<< "$result"
fi
disk=$(df -P "$state" | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
memory=$(awk '/^MemTotal/ {total=$2} /^MemAvailable/ {available=$2} END {printf "%.2f",100*(1-available/total)}' /proc/meminfo)
metrics=$(jq -n --arg id "$instance_id" --argjson readiness "$readiness" --argjson worker "$worker" \
  --argjson queue "$queue_minutes" --argjson disk "$disk" --argjson memory "$memory" \
  --argjson drift "$drift" --argjson fallback "$fallback" --argjson monitor_lag "$monitor_lag" '
  def metric($name; $value): {MetricName: $name, Value: $value, Dimensions: [{Name:"InstanceId",Value:$id}]};
  [metric("PublicReadiness";$readiness), metric("WorkerReady";$worker), metric("DiskUsedPercent";$disk),
   metric("MemoryUsedPercent";$memory), metric("OldestQueuedMinutes";$queue), metric("DriftAlert";$drift),
   metric("CanaryFallbackPercent";$fallback), metric("MonitorLagMinutes";$monitor_lag)]
  | map(select(.Value != null))')
aws cloudwatch put-metric-data --region "${AWS_REGION:?}" --namespace TeleGuard/Operations --metric-data "$metrics"
