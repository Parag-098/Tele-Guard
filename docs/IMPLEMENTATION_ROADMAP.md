# TeleGuard AI Implementation Roadmap

This roadmap consolidates the remaining build into the requested two major coding prompts after the completed repository audit. Each prompt should direct the implementation agent to inspect the actual repository, implement the full bounded phase, and report exact verification evidence. Work within each phase can proceed in dependency order without creating a long series of user prompts.

## Starting point

The audited workspace contains specifications and planning documents only. There is no working frontend/backend, database, ML code, tests, container runtime, CI, or AWS deployment. Phase 2 therefore starts from the documentation baseline and must create the smallest complete application that supports a demonstrable end-to-end synthetic event-to-investigation flow. Phase 3 makes that application releasable and demonstrates the full MLOps and AWS requirements.

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
| 2 | Backend starts | Partial | FastAPI started as a host process; API Docker image and container health check are not verified. |
| 3 | PostgreSQL persistence | Verified | Host API connected to Docker PostgreSQL and database queries confirmed persisted event, prediction, incident, note, response-action and audit rows. |
| 4 | Clean database migrations | Verified | Alembic upgraded a fresh PostgreSQL 16 volume to `0002_response_actions`; `alembic check` reported no pending operations. |
| 5 | Synthetic generation and ingestion | Verified | A seeded request created 140 synthetic events and predictions in PostgreSQL; repeating it was idempotent. |
| 6 | Train and save a real ML model | Verified by tests | Existing training test passed, including model comparison and persisted run metadata/artifact workflow; container training remains unverified. |
| 7 | Inference API persists predictions | Verified | PostgreSQL-backed API generated one prediction per event; SQL confirmed 140 predictions. |
| 8 | Risk score has traceable evidence | Verified | SQL confirmed evidence on all 140 persisted predictions; API response showed supervised, anomaly and shared-entity evidence. |
| 9 | Incident can be investigated | Verified | PostgreSQL workflow updated incident status/assignment and added analyst notes. |
| 10 | Authorized simulated response | Verified | Administrator action persisted; SQL confirmed action records and matching audit events. |
| 11 | Backend rejects unauthorized operations | Verified | PostgreSQL-backed Auditor received HTTP 403 on incident updates and response actions; automated RBAC tests also pass. |
| 12 | Database-backed dashboard | Verified | Dashboard endpoint reported database event/incident counts from the populated PostgreSQL store. |
| 13 | MLflow records training experiments | Verified in local test suite; Compose unverified | Existing MLflow tracking test passed with the local tracking store. Tracking through the Compose HTTP service and artifact proxy has not run. |
| 14 | Automated tests pass | Verified | `py -3.11 -m pytest -q`: 9 passed. Ruff and frontend production build also passed. |
| 15 | Docker Compose starts required services | **Unverified / incomplete** | PostgreSQL and frontend containers started. The API image did not finish building because package downloads from `files.pythonhosted.org` were about 50–80 KB/s; MLflow/API health and all-service startup remain unverified. |
| 16 | CI workflow configured and executable | Partial | Workflow YAML parses and local equivalents ran. No Git remote or `gh` CLI is available to dispatch/observe GitHub Actions; the new CI container-build job is not verified remotely. |

The Docker build bottleneck was package-index/CDN transfer speed, not dependency resolution alone: a 28.2 MB MLflow wheel transferred at about 77 KB/s, with similarly slow large wheels. A host-side probe of a non-cached 15.3 MB package also stalled. The API Dockerfile now separates dependency installation from source copies and uses a persistent BuildKit pip cache; Compose supports `PIP_INDEX_URL` for a reachable PyPI-compatible mirror. Those changes have not yet completed an image build in this environment. A faster configured package mirror or network path is required to verify criterion 15 without repeating long, low-throughput downloads.

Compose's MLflow configuration also changed during this verification: it now reuses the API image/version, persists tracking metadata and artifacts in separate named volumes, proxies artifacts through MLflow, and gates API startup on MLflow health. The configuration validates, but runtime behavior remains unverified. Phase 3 must not start until criteria 15 and 16 have executable verification evidence and any remaining Phase 2 functional gaps are resolved.

### Explicit Phase 2 deferrals

Do not make transcript/vishing NLP, CSV bulk import, a production-scale streaming bus, LLM-generated explanations, Kafka, Kubernetes, Airflow, Redis, graph databases, GNNs, or ECS a prerequisite. Add only if a concrete requirement and decision justify them. Phase 2 includes local MLflow experiment logging and model registration; Phase 3 hardens version provenance and moves durable artifacts to S3.

## Phase 3 — Integration, testing, security, MLOps verification and AWS deployment

**Prompt outcome:** A repeatably deployable public HTTPS AWS instance with persistent data, secure operational boundaries, and evidence that candidate evaluation, controlled release, monitoring, retraining preparation and rollback behave as specified.

### Build sequence and scope

1. **Integration and release hardening**
   - Review Phase 2 end-to-end against the specs and close integration defects across frontend, API, migrations, model artifacts and authorization.
   - Run clean environment setup, full test suite, frontend/backend lint/type/build checks, dependency/security checks available in CI, migration upgrade checks, and container build checks. Record exact commands/results; fix failures instead of suppressing or skipping them.
   - Verify all roles and negative authorization cases, input bounds, audit coverage, error behavior, secret handling, CORS/CSRF/session configuration as applicable, and that internal services have no public listener.

2. **MLOps lifecycle completion**
   - Harden the initial MLflow integration for reproducible experiments and model metadata/artifact tracking; record source revision, generator/dataset version, schema/features, parameters, metrics and artifacts. Store cloud artifacts in S3.
   - Implement model candidate registration and explicit configurable evaluation gates, with candidate rejection evidence and approval-controlled promotion.
   - Record approved model/version used per prediction. Add shadow comparison where challenger outputs cannot trigger actions; add simulation-only canary routing and tested rollback to a prior approved version.
   - Implement feature/prediction drift summaries and monitoring persistence/alerts. Separate distribution drift from measured performance decline when labels are delayed.
   - Capture analyst feedback with provenance and provide a repeatable candidate retraining command/job. Retraining must never auto-promote; require gates and authorized approval.
   - Keep MLflow private; do not publish registry/tracking ports. Do not misrepresent small synthetic tests as real-world model performance.

3. **AWS infrastructure and delivery**
   - Decide and record AWS region, account/budget constraints and PostgreSQL hosting based on available credits and cost. Preferred topology: ECR images, EC2 Docker Compose, RDS PostgreSQL when affordable; otherwise encrypted persistent EC2 storage with restricted database access and tested backups. S3 for model/data artifacts, IAM instance role with least privilege, CloudWatch logs/alarms.
   - Provision using reviewable scripts/IaC appropriate to the repository scale. Configure HTTPS through a reverse proxy/load balancer and DNS/host name; expose only necessary web ports. Use managed secret storage or protected instance configuration, never repository or image secrets.
   - Add CI/CD to test and build versioned images, publish to ECR, and deploy through a restricted workflow/role with health verification and rollback instructions.
   - Configure database migration and persistence, backups, restoration procedure, CloudWatch health/error alarms, cost/billing alert guidance, and teardown instructions. Keep training work off the always-on demo path where practical.

4. **Production-like acceptance and handoff**
   - Deploy from a clean build and verify public HTTPS URL, login/RBAC, seeded synthetic demo, event-to-incident flow, persistence after application restart, artifact retrieval, and internal-port isolation.
   - Perform backup/restore validation and release rollback test. Verify AWS logs/alarms and deployment recovery path.
   - Capture the exact deployed revision, architecture, model metrics and dataset caveats; provide concise demo steps and known limitations. Do not claim deployment is complete without a reachable endpoint and observed acceptance run.

### Phase 3 exit gate

- Public HTTPS application works on AWS with persistent PostgreSQL and S3 artifacts; a restart does not erase accepted data.
- IAM is least privilege; secrets are not in source/images; database and MLflow are not publicly exposed; HTTPS and health monitoring are active.
- Repeatable CI/CD deploys a versioned image and has a documented/verified rollback path.
- MLflow run is reproducible from recorded versions; quality gate can reject a candidate; promotion is authorized; shadow/canary behavior and rollback are verified; drift is reported distinctly from model performance.
- Backend RBAC, audit, backup/restore, cost alert, and teardown evidence are documented.

## Decisions and dependencies required before AWS provisioning

The implementation stack and synthetic-only scope are sufficiently specified. Before creating billable infrastructure, the owner must provide or confirm an AWS account/role, acceptable monthly budget or available student credits, preferred region, and domain/DNS availability. The engineering team should select RDS versus encrypted EC2 persistence against that budget and document the choice; this does not block Phase 2. If no domain exists, use an HTTPS-capable AWS hostname/load-balancer endpoint for acceptance.

## Recommended next action

Use one Phase 2 implementation prompt that points to this roadmap and the relevant existing specs. After Phase 2 has passed its exit gate, use one Phase 3 integration/release prompt. The audit is complete; do not mark application backlog items complete until their executable acceptance evidence exists.
