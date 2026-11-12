# TeleGuard AI Task Status

Use the two implementation phases in [docs/IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md). `[x]` means verified complete; `[~]` means implementation exists but acceptance evidence or scope remains; `[ ]` means not implemented. A passing subset does not mean Phase 2 is complete.

## Audit and architecture

- [x] T001 Inspect repository and document implementation evidence and gaps (`docs/REPOSITORY_AUDIT.md`).
- [x] T002 Confirm stack and architectural direction; record audit decisions in `DECISIONS.md`.

## Phase 2 — Complete local application

- [x] P2-01 Initialize new Git metadata on `main` (workspace had no `.git` or history) and create application layout. No commit was made.
- [x] P2-02 Define canonical `event-v1` contract with validation; use `event_time` and `network_token` consistently; reject malformed/naive-time/phone-like IDs.
- [~] P2-03 Compose configuration validates; PostgreSQL 16 and frontend containers were started, with HTTP 200 from the UI. `docker compose build web` passes; `docker buildx build --check ./backend` reports no Dockerfile warnings. The API image has not completed: Docker's PyPI downloads were measured at roughly 50–80 KB/s. Its Dockerfile now installs pinned dependencies in a source-independent BuildKit-cached layer, retains pip's cache, supports a configured PyPI-compatible mirror, and copies application code afterward. Full-stack startup and API container health remain unverified.
- [x] P2-04 Deterministic seedable synthetic generator for benign, SIM-swap, call-burst, SIM-farm, coordinated-ring, impossible-travel and Wangiri-like events; repeated-seed behavior tested.
- [~] P2-05 Temporal split and train-only preprocessing; compare Logistic Regression and Random Forest and report PR-AUC, ROC-AUC, precision, recall, F1, FPR, Brier score and confusion matrix. Synthetic-only methodology is documented; deeper scenario-specific and latency analysis remains.
- [~] P2-06 Idempotent ingestion and persisted inference with separate anomaly/graph/rule signals, version metadata and evidence. On 2026-11-12, migrations ran against a clean PostgreSQL 16 volume and the host API connected to that PostgreSQL instance; 140 synthetic events, 140 predictions with evidence, 121 incidents, notes, simulated actions and matching audit rows persisted. API container connectivity remains unverified because its image did not finish building.
- [~] P2-07 Versioned weighted risk policy, evidence and NetworkX relationship graph implemented. Rule catalog/version persistence and SHAP explanations remain incomplete.
- [~] P2-08 Argon2 password hashing, JWT auth, role dependencies and tested negative authorization exist. Administrator bootstrap and login were verified against the PostgreSQL-backed host API. Logout is client-side token removal; session revocation and UI user-management forms remain.
- [~] P2-09 Incidents, assignment/status changes, notes and an authorized simulated action were exercised on PostgreSQL; an Auditor was denied updates and actions (403), and SQL confirmed action audit records. Approval workflow and comprehensive resolution provenance remain.
- [~] P2-10 Connected dashboard, event explorer, incident queue, graph, model and scenario views exist. Subscriber profile and full administration/settings pages remain incomplete.
- [~] `py -3.11 -m pytest -q` passed (9 tests), Ruff passed, `npm ci` passed with 0 vulnerabilities, and `npm run build` passed with the existing large-bundle warning. PostgreSQL Alembic upgrade/current/check, Compose config validation, frontend image build, and Dockerfile static check passed. CI has not run remotely; frontend component tests and API container build/start remain unverified.
- [~] P2-12 MLflow Compose configuration now reuses the pinned API image, waits on its `/health` endpoint, keeps its SQLite backend and proxied artifacts on separate named volumes, and remains internal-only. Compose syntax validates; an MLflow-backed Compose training run is unverified because the API image did not finish building.
- [~] P2-13 GitHub Actions YAML and Compose configuration parse locally; the workflow now covers backend tests/lint, frontend build, and container image builds. No Git remote or `gh` CLI is available here, so the workflow could not be dispatched or observed on GitHub.

## Phase 3 — Integration, MLOps verification and AWS (not started)

- [ ] P3-01 Cross-layer release/security review, full regression and clean deploy verification.
- [ ] P3-02 Harden MLflow registration/artifact provenance and move AWS artifacts to S3.
- [ ] P3-03 Evaluation gates, candidate approval, champion/challenger, shadow/canary, rollback and prediction-version evidence.
- [ ] P3-04 Drift/performance monitoring, analyst feedback provenance and approval-controlled retraining.
- [ ] P3-05 Provision AWS ECR/EC2, least-privilege IAM, S3, PostgreSQL, CloudWatch and public HTTPS app.
- [ ] P3-06 CI/CD release, health checks, tested backup/restore/rollback, cost alerts and teardown documentation.
- [ ] P3-07 Verify public demo, persistence after restart, RBAC, internal-port isolation and AWS operational controls.

## Deferred

- [ ] Vishing/transcript NLP pending suitable dataset/license review.
- [ ] Kafka/Kubernetes/Airflow/Redis/graph DB/GNN/ECS and LLM summaries remain out of scope unless a documented need is accepted.
