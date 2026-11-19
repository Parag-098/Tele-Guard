# TeleGuard AI Implementation Roadmap

This roadmap consolidates the remaining build into the requested two major coding prompts after the completed repository audit. Each prompt should direct the implementation agent to inspect the actual repository, implement the full bounded phase, and report exact verification evidence. Work within each phase can proceed in dependency order without creating a long series of user prompts.

## Starting point

Historical audit finding (2026-11-12): the first checked-out workspace contained only specifications. The application source was subsequently restored/implemented and its current status is recorded in the 2026-11-15 checkpoint below.

## Phase 2 — Complete application and core functionality

**Prompt outcome:** A locally runnable, tested modular-monolith web application that can generate or submit synthetic events, persist and score them using a real trained model plus supporting signals, and let an authorized analyst investigate and resolve a simulated incident.

### Build sequence and scope

1. **Repository foundation and contract**
   - Restore/initialize usable Git metadata if this workspace is the intended repository; preserve existing docs.
   - Establish a coherent layout for React/TypeScript UI, FastAPI backend, Python ML package/commands, migrations, tests, and docs.
   - Define a canonical, versioned event schema that resolves the current field-name inconsistencies. Use synthetic tokens only; scenario and fraud labels remain training/provenance metadata and are excluded from inference inputs.
   - Provide reproducible local setup with Docker Compose for app and PostgreSQL. Add API/UI health checks and sample non-secret environment configuration.

2. **Synthetic data and offline baseline ML**
   - Create deterministic seedable benign, fraud, and benign-lookalike scenarios (at minimum SIM swap/account takeover, burst activity, Wangiri-style campaign, coordinated sharing/ring, and legitimate shared-device/network contexts).
   - Validate schema, ranges, timestamps and label/provenance separation. Record generator/dataset version and seed.
   - Build as-of-time feature generation shared by training and online scoring; add explicit tests against future/label/scenario leakage. Use time-aware train/validation/test splits and train-only preprocessing.
   - Train and compare an interpretable baseline and at least two justified supervised candidates. Report PR-AUC, precision, recall, F1 at stated threshold, false-positive rate, calibration, confusion matrix, per-scenario performance where supported, and synthetic-data caveat. Do not commit generated datasets or model binaries.

3. **Persisted inference vertical slice**
   - Implement migration-backed PostgreSQL persistence for users/roles, events, predictions, component signals/evidence, incidents, notes/labels, response actions, model metadata and audit history as needed by the implemented flow.
   - Implement validated/idempotent event ingestion, prediction retrieval and health endpoints. Load an actual approved trained artifact; missing/unavailable model must return an explicit failure or partial result, never a fabricated demo score.
   - Keep supervised probability, anomaly score, graph indicators, rule firings, data-quality state and final policy risk distinct. Version model, feature schema and scoring policy on every prediction; explain score contributions with traceable evidence.
   - Add Isolation Forest, simple versioned rules and NetworkX graph indicators as distinct supporting signals; shared entities alone never imply fraud. Keep the risk policy documented, deterministic, and honest about unavailable signals.

4. **Authentication, investigation and operator-facing UI**
   - Implement secure login/session handling and backend-enforced Administrator, Fraud Analyst, Operator, and Viewer permissions. Add safe initial-user bootstrap; never ship a default production password.
   - Build focused pages for overview/live synthetic feed, prediction/event explorer, incident queue/detail and model/evaluation summary. A polished implementation of every aspirational dashboard page is not required in this phase.
   - Support incident assignment, notes, resolution labels and reason; implement approval-controlled, reversible simulated actions with authorization and audit records. Clearly label synthetic simulation and ensure no real-world blocking/integration path exists.
   - Provide a seeded demo journey from scenario generation through prediction and analyst review.

5. **Core quality and documentation**
   - Add backend unit/integration tests for validation, deduplication, persistence, inference, leakage, normal/invalid/boundary inputs, RBAC and action audit. Add frontend build/type checks and key flow tests where practical.
   - Add actual GitHub Actions CI after commands are established; no skipped-success placeholders.
   - Update API/data contracts and local setup instructions.

### Phase 2 exit gate

- A clean checkout starts locally using documented commands; migration and seeded demo succeed.
- Synthetic event → schema validation → idempotent storage → real model/features/signals → persisted explainable assessment → incident → authorized audited simulated resolution works end-to-end.
- API rejects invalid data and unauthorized actions; permission checks are tested at the backend.
- Time-based splits and leakage controls are tested; metrics are generated from actual synthetic evaluation runs and labeled synthetic.
- CI runs real tests, lint/type checks and build checks.

### Phase 2 verification status — 2026-11-12

Phase 2 is **not complete**. Verification evidence and remaining gaps for the requested 16 acceptance criteria:

| # | Criterion | Status | Evidence / remaining verification |
|---:|---|---|---|
| 1 | Frontend starts | Verified | Docker frontend image served HTTP 200 on port 5173; API CORS preflight allowed the configured origin. |
| 2 | Backend starts | Verified | API container is healthy; internal /api/health reports database connected. |
| 3 | PostgreSQL persistence | Verified | Host API connected to Docker PostgreSQL and database queries confirmed persisted event, prediction, incident, note, response-action and audit rows. |
| 4 | Clean database migrations | Verified | Baseline PostgreSQL was at `0002_response_actions`; this pass applied `0003_mlops_sessions` to the preserved PostgreSQL volume. A clean SQLite Alembic upgrade also passed. |
| 5 | Synthetic generation and ingestion | Verified | A seeded request created 140 synthetic events and predictions in PostgreSQL; repeating it was idempotent. |
| 6 | Train and save a real ML model | Verified | Compose API training request trained and persisted a model; synthetic metrics and version were returned. |
| 7 | Inference API persists predictions | Verified | PostgreSQL-backed API generated one prediction per event; SQL confirmed 140 predictions. |
| 8 | Risk score has traceable evidence | Verified | SQL confirmed evidence on all 140 persisted predictions; API response showed supervised, anomaly and shared-entity evidence. |
| 9 | Incident can be investigated | Verified | PostgreSQL workflow updated incident status/assignment and added analyst notes. |
| 10 | Authorized simulated response | Verified | Administrator action persisted; SQL confirmed action records and matching audit events. |
| 11 | Backend rejects unauthorized operations | Verified | PostgreSQL-backed Auditor received HTTP 403 on incident updates and response actions; automated RBAC tests also pass. |
| 12 | Database-backed dashboard | Verified | Dashboard endpoint reported database event/incident counts from the populated PostgreSQL store. |
| 13 | MLflow records training experiments | Verified | Compose API training recorded the run, metrics, joblib/model artifacts, and registry version 1. After MLflow container recreation, tracking metadata remained queryable, all six artifact files remained on the named volume, and the API client downloaded the joblib artifact. |
| 14 | Automated tests pass | Verified | py -3.11 -m pytest -q: 12 passed; py -3.11 -m ruff check app tests passed; npm run build passed with the existing chunk-size warning. |
| 15 | Docker Compose starts required services | Verified | API and web images built; PostgreSQL, MLflow, and API health checks passed; API-to-PostgreSQL SELECT 1 returned 1; frontend returned HTTP 200. |
| 16 | CI workflow configured and executable | Partial | Workflow configuration and local equivalents were validated. No hosted GitHub Actions run was observed or dispatched, so the GitHub-hosted runner remains unverified. |

### Docker and MLOps verification (2026-11-13)

The reported sqlalchemy==2.0.39 (from versions: none) failure was not reproduced as a version/platform/install-logic issue. Host Python 3.11 and a fresh Linux/amd64 Python 3.12 container both downloaded that exact pin from public PyPI. The full uncached API Docker build then resolved and installed it and the complete dependency set. Docker Engine reported its HTTP and HTTPS proxies as http.docker.internal:3128; Windows WinHTTP reported direct access. Large wheels transferred at 50–200 KB/s and dependency installation took 1,919 seconds. This identifies Docker Desktop's outbound package path as the observed bottleneck. Because the original failing HTTP response was not captured, the precise transient condition behind the first versions: none message is unknown; evidence rules out an invalid pin. The dependency layer is source-independent, uses BuildKit and pip caches, and still accepts PIP_INDEX_URL. A trusted reachable mirror or corrected Docker Desktop proxy is the reproducible network remedy if that path remains slow. No dependency pins were changed or packages removed.

Verified commands included docker compose --progress plain build --no-cache api, followed by docker compose up -d --build; the second API build reused the dependency layer. docker buildx build --check ./backend reported no warnings. Fresh Compose PostgreSQL migrations ran; PostgreSQL and MLflow health checks passed; API /api/health reported database connectivity; an API-container SQLAlchemy SELECT 1 returned 1; and the frontend returned HTTP 200. An API-triggered synthetic model training run reached the Compose MLflow tracking URI and registered version 1. After docker compose up -d --force-recreate mlflow, the run and registry remained queryable, the tracking SQLite file and six artifacts (4,224,903 bytes) remained on named volumes, and an API MLflow client downloaded the persisted joblib artifact.

The requested infrastructure acceptance criteria 1–15 have verification evidence in this workspace. Criterion 16 is partial: workflow configuration and local equivalents were checked, but no GitHub-hosted Actions run was dispatched or observed. Functional gaps listed in Phase 2 tasks also remain; therefore this does not declare Phase 2 complete or authorize beginning AWS deployment.
### Current implementation checkpoint (2026-11-15)

The current working tree extends the baseline above. The new MLOps and session migration applied to the existing PostgreSQL volume without volume removal. The end-to-end Compose flow was executed with a configured administrator: baseline initialization, seeded 1,400-row feature-shift dataset, persisted PSI report, actual retraining, MLflow run/artifacts, common chronological holdout comparison, administrator approval, and rollback to the prior approved model. The observed run ID was `e5d28a10779b43c391b92805f0af933d`; MLflow reported `FINISHED` and exposed the classifier and serialized joblib artifact. At threshold 0.30, the comparison passed all three gates (PR-AUC 0.892 vs 0.915; recall 1.000 vs 0.992; FPR gate passed). Approval and rollback both returned the baseline as the final active model. The frontend returned HTTP 200 and API/PostgreSQL/MLflow passed health checks.

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| Persistent baseline/drift datasets and PSI report | Verified complete | Compose workflow stored seeded datasets and a report; detected call-duration and location-token drift. |
| Actual retraining and MLflow evidence | Verified complete | Compose run finished with a real run ID, metrics, model registry version and accessible artifacts. |
| Same-holdout gates, approval/rejection and rollback | Verified complete | Challenger passed gates, admin approval updated active selection, and rollback restored the earlier approved baseline; covered by an integration test. |
| Server-side logout/session revocation and user role/status administration | Verified complete | Unit tests cover logout revocation, role updates, disabled-user invalidation, and last-admin protection. |
| SHAP feature contributions | Not implemented | Existing evidence is signal-level; no SHAP dependency or per-prediction SHAP values are present. |
| Full assignment/resolution provenance and advanced investigation search | Partially implemented | Basic assignment, status and notes persist; richer resolution reason/history/search remain. |
| GitHub-hosted Actions execution | Blocked by external access | Workflow is present and local equivalents pass; no authenticated GitHub Actions CLI/session was available. |
| AWS deployment | Not implemented | Phase 3 work only; no cloud resource was provisioned. |

Phase 2 is not declared complete because SHAP and investigation/admin refinements remain acceptance gaps. The MLOps end-to-end acceptance path is verified. Do not start AWS provisioning until the remaining Phase 2 criteria are either implemented or explicitly accepted as deferred.

### Explicit Phase 2 deferrals

Do not make transcript/vishing NLP, CSV bulk import, a production-scale streaming bus, LLM-generated explanations, Kafka, Kubernetes, Airflow, Redis, graph databases, GNNs, or ECS a prerequisite. Add only if a concrete requirement and decision justify them. Local MLflow experiment tracking and the approval-controlled lifecycle are implemented; Phase 3 focuses on deploying them safely and moving durable artifacts to S3.

## Phase 3 — Final completion, AWS deployment and operational hardening

### Re-audit and implementation checkpoint (2026-11-16)

- On-demand SHAP for the exact prediction model and feature schema is implemented, displayed in investigation detail, persisted, and covered by additivity/shape/mapping/schema-mismatch testing.
- Incident resolution now persists outcome, reason, resolver and timestamp. Assignment validates active analyst/investigator accounts. Incident filtering and audit history are available through the API and case detail. Auditor modification/action restrictions remain backend enforced and were also checked in the rendered MLOps role controls.
- Playwright browser click-through passed for admin login, saved MLOps datasets/models/registry/drift/comparison views, actual prediction SHAP rendering, and Auditor disabled controls. No training/reset action was triggered during this UI verification.
- Local Compose was rebuilt and recreated without removing existing volumes; Alembic head is `0005_mlflow_run_reference`. API/PostgreSQL/MLflow health and frontend HTTP 200 passed.
- Prepared `docker-compose.prod.yml`, Caddy routing, PostgreSQL-backed production MLflow, S3 artifact proxy, IAM-based logs/artifacts, EBS bind mounts, immutable ECR tags, GitHub OIDC + SSM release automation and operations guides. Production Compose validation confirms only HTTP/HTTPS publish to host.
- AWS deployment and GitHub-hosted CI/CD are not complete: account/CLI/role, DNS and GitHub settings were unavailable. No billable AWS resources were created. See [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md) for the exact setup and constraints.
- Remaining scope in this Nov 16 checkpoint: advanced blueprint items such as transcript-based vishing and AWS deployment remain outside the completed local implementation. Location/travel scoring, shadow/canary serving and delayed-label monitoring are implemented and verified locally; see `LOCAL_ACCEPTANCE_REPORT.md`.

### Phase 3 release gate status

| Requirement | Status |
|---|---|
| Local regression, SHAP, investigations and MLOps UI | Verified complete locally |
| Production configuration and private-port validation | Implemented and locally config-validated |
| AWS EC2/ECR/S3/CloudWatch deployment | Blocked by external access |
| Public domain and HTTPS verification | Blocked by domain/account access |
| GitHub-hosted Actions and OIDC deployment | Blocked by GitHub settings/auth; workflow prepared |
| Deployed PostgreSQL persistence, model retrieval, backup and isolated restore | Not verified until AWS deployment |

## Phase 3 - AWS deployment and operational hardening

Begin AWS provisioning only after the remaining Phase 2 gaps are explicitly closed or accepted as deferred. The local MLOps lifecycle described in the checkpoint is already implemented and verified; Phase 3 must deploy that behavior safely rather than rebuild a second lifecycle.

### Build sequence and scope

1. **Close Phase 2 acceptance gaps**
   - Implement or explicitly defer SHAP feature attributions, richer scenario evaluation, and remaining investigation provenance/search.
   - Verify the MLOps UI interactively in a browser and observe the authenticated GitHub-hosted Actions run when access is available.
2. **AWS topology and budget**
   - Decide and record region, account/budget constraints and PostgreSQL hosting. Prefer EC2 Docker Compose, ECR, private PostgreSQL (RDS if affordable), S3 model artifacts, least-privilege IAM, and CloudWatch.
   - Keep MLflow and PostgreSQL private. Use protected runtime secrets, HTTPS, backups, tested restore, billing alerts, and teardown instructions.
3. **Deployment and operations**
   - Build/publish versioned images; deploy through a restricted CI/CD role; run migrations and health checks; document rollback.
   - Verify public HTTPS login/RBAC, synthetic event-to-incident flow, MLOps drift/retraining/approval/rollback, persistence after restart, artifact retrieval, logs/alerts and internal-port isolation.
4. **Handoff**
   - Record exact revision, architecture, synthetic metrics and limitations. Do not claim deployment without a reachable endpoint and observed acceptance run.

### Phase 3 exit gate

- Public HTTPS application works on AWS with persistent PostgreSQL and S3 artifacts; a restart does not erase accepted data.
- IAM is least privilege; secrets are not in source/images; database and MLflow are not publicly exposed; HTTPS and health monitoring are active.
- Repeatable CI/CD deploys a versioned image and has a documented/verified rollback path.
- MLflow run is reproducible from recorded versions; quality gate can reject a candidate; promotion is authorized; shadow/canary behavior and rollback are verified; drift is reported distinctly from model performance.
- Backend RBAC, audit, backup/restore, cost alert, and teardown evidence are documented.

## Decisions and dependencies required before AWS provisioning

The implementation stack and synthetic-only scope are sufficiently specified. Before creating billable infrastructure, the owner must provide or confirm an AWS account/role, acceptable monthly budget or available student credits, preferred region, and domain/DNS availability. The engineering team should select RDS versus encrypted EC2 persistence against that budget and document the choice; this does not block Phase 2. If no domain exists, use an HTTPS-capable AWS hostname/load-balancer endpoint for acceptance.

## Recommended next action

Use one Phase 2 implementation prompt that points to this roadmap and the relevant existing specs. After the remaining Phase 2 gaps are closed or accepted, use one Phase 3 AWS deployment/readiness prompt. The audit is complete; do not mark application backlog items complete until their executable acceptance evidence exists.

## 2026-11-19 completion pass superseding the checkpoint above

The earlier checkpoints in this file are historical and their statements that SHAP, CSV, location/travel, shadow/canary and delayed-label features were missing are stale. See [IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md](IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md) for the complete feature-by-feature result and actual test evidence. The current pass added the normalized, versioned 150,000-row operational dataset, batched ingestion, durable worker/health and data observatory views; it also corrected the historical initial Alembic migration so clean installs reach `0008`. The preserved local PostgreSQL volume is at `0008` and contains the generated dataset, predictions and candidate model run. Local acceptance is complete after the final post-fix browser rerun. AWS deployment remains explicitly unperformed; recommendation is **NO-GO** until the listed AWS and release gates pass.
