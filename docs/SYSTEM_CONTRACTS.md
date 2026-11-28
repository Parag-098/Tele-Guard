# Incremental system contracts, frontend and security

This is planned design. The current contract remains [event-v1](../backend/app/schemas/event-contract.json), implemented by [schemas](../backend/app/schemas.py) and [models](../backend/app/models.py). Existing endpoint names and return semantics are kept where possible. Names below describe contract groups. Choose concrete new paths and publish their schemas during implementation, with stable pagination, actionable errors and integrated tests.

## API and persistence

| Workflow | Existing surface | Incremental contract |
|---|---|---|
| Authentication and roles | /api/auth/login, /me, /logout, /users under /api/auth | Keep current roles, server-side session revocation and audit. Enforce every write on the backend. Apply bounded login/ingestion rates and protect state-changing cookie requests if moving browser sessions to cookies. |
| INGEST / explore / explain | /api/events, /api/events/upload-csv, /api/events/{event_id}/explanation | Preserve event-v1 and CSV atomicity. New large import workflow returns a 202 job with stable idempotency key and progress. Query by stable cursor across event-time ties, with legacy offset support. Explain the saved prediction using recorded provenance and availability state. |
| Dataset and jobs | /api/data/observatory, /api/datasets/seed, /api/jobs/{job_id} and job control | Dataset list/detail shows manifest, actual split/label counts, readiness, run and checksum. Jobs expose start/end, stale heartbeat, lease/retry/cancel state, stage totals and a redacted failure code. Scripts and API converge on the same worker pipeline. |
| Simulator / lab | /api/scenarios/generate and location rule configuration | Add persisted run creation and command/status resources, presets, bounded replay, queue lag/quarantine summaries and run-scoped window/report links. Leave existing seeded generation as a compatibility mode with an appropriate synchronous bound. |
| Investigations and labels | /api/incidents, notes/actions/reversal, entity graph, /api/predictions/{event_id}/label | Multiple prediction links per case, primary legacy prediction retained, case timeline, merge/reopen eligibility, deterministic priorities, feedback history and low-risk review sampling. Add conflict responses for stale edits and a write idempotency mechanism. |
| Model control | /api/models and /api/mlops routes | Add async retraining and stage queries. Trigger records link to immutable job id, dataset and monitor report. Keep legacy demo paths with explicit scope. Comparison/approval resources reference champion epoch, candidate, dataset split and policy versions with immutable outcome. |
| Monitoring and system | /api/health, /api/system/health, /api/system/metrics, /api/mlops/monitoring, audit | Add distinct liveness, inference readiness and dependency/job health; expose monitoring windows, data quality, labeled support, pending alerts and assigned/served/fallback counters, gated log summaries and server-side pagination. |

Use validation errors for malformed inputs, explicit authorization failures for protected operations, conflict responses for changed state, and bounded resource-limit responses with retry guidance. Avoid returning infrastructure errors, paths, internal tracking URLs and secrets. Preserve existing endpoint status for legacy callers unless a qualified change is needed. Store OpenAPI examples and a tested API/UI contract for each new operation.

| Persistence boundary | Planned constraints and provenance |
|---|---|
| Events, predictions and model observations | Globally unique event IDs with source namespace, timestamps and payload identity. Preserve original prediction and policy/schema; new evaluations and replays append linked records. Track experiment, segment, assignment, actual model, fallback, observed policy and scoring time. |
| Datasets, simulator and jobs | Relate dataset manifest to parts and split digests, simulator run to durable checkpoints/outcome sidecar, job to typed payload and immutable dependency versions. Unique active job key or equivalent lock, transactional claim, lease and timestamp checks. |
| Monitoring and releases | Unique window identity by model/schema/source/cohort and logical window. Append reports and incident alerts with dedup key/trigger record. Use a single authoritative durable active release pointer with revision and promotion audit. |
| Investigation and feedback | Unique case-event or case-prediction linkage with scored evidence, original incident provenance and reversible association changes. Store versioned label adjudication with actor, timestamp, evidence, decision precedence, correction link and source. |
| Upgrade safety | Add Alembic migrations with tested preconditions, foreign keys and indexes. Test fresh database and a historical snapshot upgrade. Prefer additive contracts and data backfill with counts, checkpoints and compatibility. Keep production schema changes under migration control. Review query plans for bounded time/cohort windows and migration locks. |

## Frontend and UX acceptance

Extend [App.tsx](../frontend/src/App.tsx) and [OperationalViews.tsx](../frontend/src/OperationalViews.tsx). Break up components only when necessary to keep integrated flows maintainable. Reuse navigation, filters and existing theme. Each view supplies actionable loading, empty, partial-failure, unauthorized and retry states, accessible labels, keyboard/focus behavior and responsive table/charts, with downloadable or textual views of key figures.

| View | Required decisions and real state |
|---|---|
| Overview / impact | Event and alert volumes by cohort, workload and lag, current champion, recent health, trend/denominator definitions and simulated exposure assumptions. Link to real filtered evidence. |
| Live / Simulator / Drift Lab | Run controls, artificial traffic mode, pace, caps and output, stream lag, scenario schedules, quality/label windows and real job/report links. Distinguish paused, stopped, underpowered and failed states. |
| Explorer / Graph / SHAP | Discover events by time and risk, share filters, inspect entity links and attribution with model/schema and evidence timing. Handle unsupported or unavailable historical artifacts explicitly. Avoid implying that graph linkage establishes fraud. |
| Investigation | Assignment/status, evidence/timeline, correlated links, note/adjudication provenance, controlled merges/reopening and reversible authorized simulated actions. |
| Dataset management | Version, exact counts, split and label support, checksums, storage and job status. Retain seed/import and legacy dataset access. |
| MLOps control center | Champion/candidate and policy/artefact lineage, registry, stage progress, comparisons with support counts, quality, drift and delayed labels, triggers, shadow, configured/observed canary percentages and fallback, approvals, suspension, rollback, health and sanitized logs. |
| Admin / Audit / Health | Role and user management, immutable actor/decision history, deployment health, worker and job heartbeat/alerts. Hide unavailable controls and support deep-link authorization errors. Existing views continue to work as these additions land. |

## Security and reliability

- Map existing roles to their current permissions before changes. Administrators control users, configuration and production promotion. ML Engineers can inspect MLOps, request training and compare candidates. Fraud Analysts and Investigators use authorized case flows and adjudication. Auditors keep read-only access. Map the original Operator/Viewer personas to explicit scoped permissions compatible with existing Investigator/Auditor behavior. Neither copied role claims nor frontend button visibility can grant access.
- Use the current password hashing unless an evidenced upgrade is needed. Require unique bootstrap secrets, controlled account changes and session revocation. Review browser token persistence, CSP and production CORS; prefer HttpOnly same-origin cookies with CSRF controls if adopted and preserve transitional bearer compatibility as documented. Audit login, denial and role changes without logging passwords or tokens.
- Check payload constraints, quotas, pagination and bulk import sizes. Map permissions by resource and action. Test malicious or mistaken label/case edits, cross-role job access, invalid transitions and concurrent policy changes with defensive integration tests. Keep raw customer data, real communications and real identifiers out of the system.
- Treat joblib and all loadable artifacts as trusted internal build outputs only. Verify version, feature schema, dependency compatibility, durable URI and checksum before loading, refreshing cache or selecting a release. Reject user-supplied artifact paths. Keep serving a verified last-known-good artifact when safe and report readiness/degraded state explicitly.
- Gate infrastructure privileges, secret rotations and log redaction. Keep PostgreSQL and MLflow private. Use migrations, atomic commit boundaries, explicit reversal records, graceful bounded shutdown, leases with recovery, backup/restore drills and a tested runbook. Follow [operations](PRODUCTION_OPERATIONS.md) and [security/recovery acceptance](TESTING_AND_TRACEABILITY.md#requirement-to-test-matrix).
