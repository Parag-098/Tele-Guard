#!/usr/bin/env bash
# Run only inside the approved GitHub production environment after the exact images passed CI.
set -Eeuo pipefail
umask 077
: "${ECR_REGISTRY:?}" "${RELEASE_BUCKET:?}" "${DEPLOY_INSTANCE_ID:?}" "${DEPLOY_DOCUMENT:?}" "${RELEASE_SHA:?}"
[[ "$RELEASE_SHA" =~ ^[a-f0-9]{40}$ ]] || exit 2
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT

ecr_digest() {
  local service="$1" repository="teleguard-$1" local_image="teleguard-$1:release"
  local result digest remote_config expected_config
  expected_config=$(docker image inspect --format '{{.Id}}' "$local_image")
  result=$(aws ecr batch-get-image --repository-name "$repository" --image-ids "imageTag=$RELEASE_SHA")
  digest=$(jq -r '.images[0].imageId.imageDigest // empty' <<< "$result")
  if [[ -z "$digest" ]]; then
    docker tag "$local_image" "$ECR_REGISTRY/$repository:$RELEASE_SHA"
    docker push "$ECR_REGISTRY/$repository:$RELEASE_SHA" >&2
    result=$(aws ecr batch-get-image --repository-name "$repository" --image-ids "imageTag=$RELEASE_SHA")
    digest=$(jq -er '.images[0].imageId.imageDigest' <<< "$result")
  fi
  remote_config=$(jq -er '.images[0].imageManifest | fromjson | .config.digest' <<< "$result")
  if [[ "$remote_config" != "$expected_config" || ! "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]; then
    echo "Registry image for $service differs from the tested image" >&2
    return 2
  fi
  printf '%s/%s@%s\n' "$ECR_REGISTRY" "$repository" "$digest"
}

api_image=$(ecr_digest api)
web_image=$(ecr_digest web)
[[ "$TG_POSTGRES_IMAGE" =~ ^(docker.io/library/)?postgres@sha256:[a-f0-9]{64}$ ]] || exit 2
[[ "$TG_CADDY_IMAGE" =~ ^(docker.io/library/)?caddy@sha256:[a-f0-9]{64}$ ]] || exit 2

install -d "$stage/bundle/deploy"
cp docker-compose.prod.yml "$stage/bundle/"
cp deploy/{Caddyfile,init-mlflow-db.sh,deploy-release.sh,backup-postgres.sh,restore-postgres.sh,operations-metrics.sh,teleguard-backup.service,teleguard-backup.timer,teleguard-metrics.service,teleguard-metrics.timer} "$stage/bundle/deploy/"
chmod +x "$stage/bundle/deploy/init-mlflow-db.sh"
printf 'RELEASE_TAG=%s\nTG_API_IMAGE=%s\nTG_WEB_IMAGE=%s\nTG_POSTGRES_IMAGE=%s\nTG_CADDY_IMAGE=%s\n' \
  "$RELEASE_SHA" "$api_image" "$web_image" "$TG_POSTGRES_IMAGE" "$TG_CADDY_IMAGE" > "$stage/bundle/release-image.env"
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -C "$stage/bundle" \
  -czf "$stage/release.tar.gz" docker-compose.prod.yml release-image.env deploy
checksum=$(sha256sum "$stage/release.tar.gz" | cut -d' ' -f1)
key="bundles/$RELEASE_SHA-$checksum.tar.gz"
if ! aws s3api put-object --bucket "$RELEASE_BUCKET" --key "$key" --body "$stage/release.tar.gz" \
    --server-side-encryption AES256 --if-none-match '*' >"$stage/publish.json" 2>"$stage/publish.err"; then
  grep -q '(PreconditionFailed)' "$stage/publish.err" || { cat "$stage/publish.err" >&2; exit 1; }
fi

parameters=$(jq -nc --arg revision "$RELEASE_SHA" --arg checksum "$checksum" '{revision:[$revision],checksum:[$checksum]}')
command=$(aws ssm send-command --instance-ids "$DEPLOY_INSTANCE_ID" --document-name "$DEPLOY_DOCUMENT" \
  --comment "TeleGuard release $RELEASE_SHA" --parameters "$parameters" --query Command.CommandId --output text)
printf 'Release %s, bundle SHA256 %s, SSM command %s\n' "$RELEASE_SHA" "$checksum" "$command"
for attempt in $(seq 1 90); do
  status=$(aws ssm get-command-invocation --command-id "$command" --instance-id "$DEPLOY_INSTANCE_ID" \
    --query Status --output text 2>/dev/null || true)
  case "$status" in
    Success|Failed|Cancelled|TimedOut|Cancelling)
      aws ssm get-command-invocation --command-id "$command" --instance-id "$DEPLOY_INSTANCE_ID" \
        --query '[Status,StandardOutputContent,StandardErrorContent]' --output text
      [[ "$status" == Success ]]
      exit
      ;;
  esac
  sleep 10
done
echo 'SSM deployment did not finish within 15 minutes.' >&2
exit 1
