# Production Operations

These commands target the prepared EC2 deployment. They have not been run against AWS in this session. Run from `/opt/teleguard` on the host; never use `down -v`.

```bash
cd /opt/teleguard
dc=(docker compose --env-file .env.production -f docker-compose.prod.yml)
"${dc[@]}" ps
"${dc[@]}" logs --tail=200 api db mlflow web proxy
curl --fail https://YOUR_DOMAIN/api/health
```

## Start, stop and deploy

```bash
"${dc[@]}" up -d
"${dc[@]}" stop                 # stop containers, retain all volumes
sudo systemctl stop docker      # optional host shutdown preparation
sudo systemctl start docker
```

Deploy an immutable image release through SSM or manually:

```bash
sudo /opt/teleguard/deploy-release.sh GIT_COMMIT_SHA
```

Application rollback uses the previous immutable ECR image tag and retains current PostgreSQL data/model selection. Set `RELEASE_TAG` to the prior tested SHA and run the deploy script. Database schema migrations are forward-only in normal operation; do not roll back schema by restoring an old application image unless compatibility is confirmed. Restore data only into an isolated destination first.

## Health and logs

```bash
"${dc[@]}" ps
"${dc[@]}" logs --tail=200 api mlflow db proxy
curl --fail https://YOUR_DOMAIN/api/health
aws logs tail /teleguard/production --since 1h --follow --region ap-south-1
df -h
free -h
docker stats --no-stream
```

MLflow has no public port. From inside the Compose network, check `http://mlflow:5000/health` or execute `python -c "import urllib.request; print(urllib.request.urlopen('http://mlflow:5000/health').status)"` in the API container. Database access is internal only; `pg_isready` runs in its health check.

## PostgreSQL backup and isolated restore

```bash
stamp=$(date -u +%Y%m%dT%H%M%SZ)
"${dc[@]}" exec -T db pg_dump -U teleguard -d teleguard -Fc > "/var/backups/teleguard-$stamp.dump"
aws s3 cp "/var/backups/teleguard-$stamp.dump" \
  "s3://YOUR_PRIVATE_BACKUP_BUCKET/postgres/teleguard-$stamp.dump" --sse AES256
```

Restore only into an isolated validation database:

```bash
"${dc[@]}" exec -T db createdb -U teleguard teleguard_restore_test
aws s3 cp s3://YOUR_PRIVATE_BACKUP_BUCKET/postgres/CHOSEN.dump - | \
  "${dc[@]}" exec -T db pg_restore -U teleguard -d teleguard_restore_test --no-owner
"${dc[@]}" exec -T db psql -U teleguard -d teleguard_restore_test -c 'SELECT count(*) FROM events;'
```

Compare expected row counts and sample synthetic-only records, then drop only the validation database after confirming no further restore testing is needed. A restore to production must be a separate reviewed maintenance action after a fresh backup.

## Verify an MLflow artifact

From an API container, use the stored run reference and an artifact path:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec api python -c \
"from mlflow import MlflowClient; c=MlflowClient(); print(c.get_run('RUN_ID').info.status); print(c.download_artifacts('RUN_ID','fraud-model-VERSION.joblib'))"
```

Confirm the downloaded joblib artifact embeds the version in the associated `model_runs` row. If the local model cache is missing, API model loading downloads that recorded `.joblib` artifact via MLflow; request-supplied paths are never used.

## Rotate secrets

1. Generate a replacement database password, update the PostgreSQL role password through an authenticated host session, and update both encoded database URLs in the protected runtime environment.
2. Change `TG_SECRET_KEY`; this invalidates existing bearer tokens and users must sign in again.
3. Remove the one-time admin bootstrap password after initial bootstrap. Use the administrator user-management UI to rotate/disable application users.
4. Recreate API and MLflow services as appropriate. Confirm database health and MLflow access before closing the session.
5. Review IAM role policies and CloudTrail for unusual access. Do not put replacement secrets in GitHub Actions logs or command histories.

Prefer SSM Parameter Store SecureString or Secrets Manager retrieval through the instance role for steady-state operations. The current prepared compose file supports a mode-600 host env file as a smaller single-host setup.

## Disk, memory and service issues

- Disk: `df -h`, `docker system df`, inspect PostgreSQL, Docker, and backup usage. Never prune named volumes. Remove only known disposable image layers or expired local backup files after confirming S3 copies.
- Memory: `free -h`, `docker stats --no-stream`, `dmesg -T | grep -i -E 'oom|killed process'`. Retraining temporarily consumes additional memory; schedule it away from presentation hours or upgrade the instance if measured memory pressure recurs.
- Restart loop: `docker compose ... logs --tail=200 SERVICE`, check `.env.production` permissions/values, database URL encoding, ECR pull permissions and migration error output.
- TLS: verify DNS A/AAAA values and security-group ports 80/443, then inspect `proxy` logs. Do not claim HTTPS until a public TLS check succeeds.
- MLflow/S3: check `MLFLOW_ARTIFACT_BUCKET`, instance-role permissions and CloudWatch `mlflow` logs. Keep the bucket private.

## Incremental operational drills TG-12 and TG-13

- Before release record tested image digests, Alembic head, active model and policy, prior release configuration, backup ID and known-compatible rollback path. Only authenticated readiness shows model/worker and partial dependency health; liveness stays minimal. If readiness degrades, capture details and stop rollout. Do not roll an incompatible application version over changed schema.
- Back up both application and MLflow metadata, plus model manifest/checksum and private object version references. Scope restore into a separate disposable PostgreSQL database/instance and artifact cache. Verify migrations, counts, sessions and role access as appropriate for the restored environment, active model and model prediction on a fixed fixture. Report measured recovery time and recoverable event age.
- Verify simulator and job restart at safe checkpoints, retry/cancellation audit, inference with MLflow unavailable when a good cache is present, cold artifact retrieval when it returns, and a rollback using the approved previous model. Monitor job lag and keep paused/stopping states recoverable across crashes.
- Store redacted CloudWatch alarms and support actions for memory/disk, queue growth, schedule delay, MLflow outage, model errors, canary discrepancy and drift. Use the [AWS readiness plan](AWS_DEPLOYMENT_GUIDE.md#incremental-aws-readiness-and-verification-tg-13) before operations that incur cost. Link outcomes to E-12, E-13 or E-15 in the [matrix](TESTING_AND_TRACEABILITY.md#requirement-to-test-matrix).

### Offline scale and worker behavior — 2026-11-28

The API supports `TG_API_WORKERS` from 1–8; production Compose defaults to 2 workers. Each process refreshes its active-model pointer from the committed database state before readiness/inference so a promotion in another worker is visible. Keep the value within database-connection and host-memory budgets, and re-run load acceptance after changing it. On the 16-logical-CPU local test host, two workers sustained 10 scored synthetic events/s for 10 minutes with zero request errors, 7,200/7,200 persisted events and predictions, and no queued/running work after drain. Steady-only p95 was 125 ms. The bounded 2x burst had an aggregate p95 of 4.657 s and p95 scheduling lag of 30.778 s, so the steady target is met while burst latency is a known capacity limit. These numbers are local observations, not an AWS SLO or cloud sizing claim. See [load evidence](evidence/load-replay-2026-11-28-steady.json) and [sustained replay](evidence/load-replay-2026-11-28-scaled-sustained.json).
