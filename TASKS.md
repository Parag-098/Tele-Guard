# TeleGuard AI Task Status

`[x]` means verified in the local environment; `[~]` means implemented but not verified against its target system or complete scope; `[ ]` means not implemented. AWS resources and hosted workflows are not assumed from configuration alone.

## Phase 2 — Local application and MLOps

- [x] Synthetic event contract, generation/ingestion, inference evidence, anomaly/graph/rule signals and risk scoring persisted in PostgreSQL.
- [x] Authentication, backend RBAC, session revocation, user role/status administration, audit logs and simulated reversible actions have backend tests.
- [x] Seeded MLOps baseline/drift dataset, persisted PSI reports, real retraining/MLflow runs, same-holdout evaluation, administrator promotion/rejection, rollback and active-model inference were previously exercised end to end in Compose.
- [x] Per-prediction SHAP added for the recorded Random Forest or Logistic Regression classifier. Contributions are on-demand, version/schema checked, and additivity checked; test covers output shape, feature names and mismatch failure.
- [x] Incident resolution outcome/reason/actor/time, valid-assignee checks, query/status/severity/assignee filters, investigation history and audit traceability added and tested. Auditors remain unable to modify incidents or run actions.
- [x] Browser click-through verified admin login, MLOps datasets/models/registry, existing drift and challenger reports, lifecycle controls, prediction SHAP rendering, and Auditor-disabled training/no promotion controls. No lifecycle retraining or reset was invoked during browser check.
- [x] Context-aware location/travel scoring, persisted evidence, administrator-configurable scenario rules, shadow/canary serving, delayed-label metrics/alerts and monitoring UI verified locally 2026-11-16.
- [~] GitHub-hosted CI has not run in this session because GitHub authentication/CLI is unavailable. Local equivalents are reported separately.

## Phase 3 — AWS deployment and release

- [x] Added production Compose, private-network topology, Caddy reverse proxy, same-origin API target, health checks, restart policies, EBS bind-mount locations, PostgreSQL-backed MLflow metadata, S3 artifact proxy configuration, CloudWatch log driver, and disabled API docs setting.
- [x] Model rows now retain MLflow run IDs; API can recover a missing recorded joblib artifact through MLflow's artifact API.
- [x] Added a commit-SHA ECR build/deploy job using GitHub OIDC and SSM, gated behind CI and a protected `production` GitHub environment.
- [x] Added AWS deployment, operations, cost and release-checklist documentation; production Compose config verified that only Caddy exposes host ports 80/443.
- [ ] Live AWS provisioning/deployment, DNS/HTTPS, ECR, S3 artifact recovery, CloudWatch, persistence restart and isolated restore — blocked by unavailable AWS account/CLI/role and domain access.
- [ ] Hosted GitHub CI/CD run — blocked by unavailable authenticated GitHub Actions access and repository settings.

## Local verification (2026-11-16)

- [x] `py -3.11 -m pytest tests -q` — 15 passed (17 upstream/deprecation warnings).
- [x] `py -3.11 -m ruff check app tests` — passed.
- [x] `npm run build` — passed; Vite reports the existing large JavaScript chunk warning.
- [~] `npm audit --audit-level=high` — zero vulnerabilities was observed in the previous verification; rerun after this final UI pass before release.
- [x] `docker compose build api web` — passed with SHAP and boto3 dependencies.
- [x] `docker compose up -d` — recreated API, MLflow and web against existing PostgreSQL/MLflow/model volumes; health checks passed.
- [x] `docker compose exec -T api alembic current` — `0005_mlflow_run_reference (head)`.
- [x] API container successfully fetched MLflow health; frontend returned HTTP 200.
- [x] Production Compose config validated; only Caddy ports 80/443 publish to host.

## Deferred/out of scope

- Real carrier/subscriber integrations, real subscriber blocking, surveillance or personal communications data.
- Vishing transcript NLP pending licensed, appropriate datasets.
- Kafka, Kubernetes, Airflow, Redis, graph DB, GNNs, ECS, and LLM case decisions without a concrete requirement.

## 2026-11-19 implementation and acceptance update

- [x] Versioned, deterministic 150,000-row initial synthetic dataset persisted in normalized PostgreSQL event rows with operational predictions, model observations and incidents; dataset version, seed, counts and model/run provenance are retained.
- [x] Batched, resumable worker job with progress and pause/resume/stop controls; PostgreSQL heartbeat displayed in Live monitoring.
- [x] CSV batch ingestion with schema/range checks, 25 MB / 5,000-row bounds, all-row validation before commit, and idempotent event IDs.
- [x] Three supervised candidates evaluated with chronological train/validation/test splits, per-scenario reporting, MLflow run and model registry tracking.
- [x] Operational dashboard counts, data quality view and service health are sourced from persisted records; event and incident list serialization uses batched queries.
- [x] Expanded API tests and browser acceptance; clean SQLite migration through `0008` and preserved live PostgreSQL upgrade verified.
- [ ] AWS public HTTPS release acceptance, S3 artifact recovery, CloudWatch, isolated restore and GitHub-hosted OIDC workflow remain unverified; see [implementation report](docs/IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md).
