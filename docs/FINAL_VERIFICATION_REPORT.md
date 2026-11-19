# Final Phase 2 verification report — 2026-11-15

## Status summary

| Area | Status | Evidence |
|---|---|---|
| Existing FastAPI/React/PostgreSQL/Compose foundation | Verified complete before this pass | Earlier repository evidence recorded in README and roadmap; preserved PostgreSQL/MLflow volumes were reused. |
| Session revocation and administrator user/role/status controls | Verified complete | 12 backend tests pass, including logout invalidation, user disable invalidation, role updates, RBAC and last-admin protection. |
| Persisted synthetic baseline and feature-drift lifecycle | Verified complete | Compose workflow generated 1,400 drift events, detected call-duration/network/location PSI drift, and persisted datasets/reports. |
| Real retraining and MLflow registry/artifacts | Verified complete | Compose run `3b379261f95b43ecb11de28f9e7a0b62` finished; MLflow registry was available with five versions; serialized artifact download succeeded (1,711,822 bytes). |
| Champion/challenger, approval and rollback | Verified complete | Shared holdout gates passed; administrator approved the candidate, then rollback restored the earlier approved baseline. Post-rollback inference recorded that selected baseline version. |
| MLOps frontend | Implemented; production build verified | Dedicated route, lifecycle controls, permission-aware actions, dataset/report/model/registry tables, decision and rollback controls are present. Live browser click-through was not automated. |
| SHAP prediction attributions | Not implemented | Current explanations remain signal-level evidence; no SHAP dependency/per-prediction attribution exists. |
| GitHub-hosted Actions run | Blocked by external access | `origin` exists and workflow is configured, but no authenticated `gh` CLI/session was available to dispatch or inspect hosted Actions. |
| AWS Phase 3 | Not implemented | No AWS resources were created. |

## Previously verified baseline

The pre-existing application and Compose results are documented in README and the roadmap: seeded synthetic ingestion, persisted predictions/incidents/actions/audit rows, administrator login, PostgreSQL migrations, API/PostgreSQL health, Compose MLflow tracking and artifact persistence, frontend HTTP 200, and an earlier 9-test/Ruff/frontend-build pass. This pass preserved those capabilities and the existing named volumes.

## Work completed in this pass

- Added Alembic `0003_mlops_sessions` and persistence for revocable authentication sessions, versioned demo datasets, and typed MLOps lifecycle records.
- Added administrator user role/status edits with last-active-admin protection; disabling an account revokes its sessions. Logout now revokes the current server-side session.
- Changed candidate training so it no longer replaces the active model. Added persisted baseline initialization, fixed-seed 1,400-row feature drift, PSI reports, real training on a versioned drift dataset, and MLflow run ID/error reporting.
- Added same-dataset chronological champion/challenger metrics, explicit PR-AUC/recall/FPR gates, administrator approval/rejection, persisted active-model selection, and approved-model rollback. Inference loads the selected artifact.
- Added the MLOps page, separate lifecycle controls, one-click orchestration that pauses for the administrator decision, actual MLflow registry version display, audit history, reset limited to drift-specific demo records, and administrator user management controls.
- Added backend integration coverage and updated architecture, policy, lifecycle specification, README, task/roadmap status, and college/demo guides.

## Commands run and results

- `py -3.11 -m pytest -q` — **12 passed** (12 dependency deprecation warnings).
- `py -3.11 -m ruff check app tests` — **passed**.
- `npm run build` — **passed**, with the existing Vite large-chunk warning (639.41 kB minified JS).
- `npm audit --audit-level=high` — **passed**, 0 vulnerabilities; this check is now included in `.github/workflows/ci.yml`.
- `$env:TG_DATABASE_URL='sqlite://'; py -3.11 -m alembic upgrade head; py -3.11 -m alembic current` — **passed**, all three revisions applied on a fresh in-memory SQLite database.
- `docker compose config --quiet` — **passed**.
- `docker compose build api web` — **passed**, dependency layers reused from cache.
- `docker compose up -d` — **passed** using existing named volumes; API, PostgreSQL and MLflow health checks reported healthy; frontend served HTTP 200. No volume removal/reset was run.
- API-container SQLAlchemy `SELECT 1` — **1**.

## Compose MLOps end-to-end evidence

Using the configured administrator and the real Compose API/PostgreSQL/MLflow services:

1. Initialized baseline `baseline-v1-seed-2026`.
2. Generated a seeded 1,400-row drift batch; persisted PSI reported drift in `call_duration_seconds`, `network_token`, and `location_token`.
3. Persisted a drift report with PSI threshold 0.20 and interpretation that input drift alone does not establish concept drift or performance degradation.
4. Trained candidate `synthetic-20261115132320395767` on the versioned dataset. MLflow run `3b379261f95b43ecb11de28f9e7a0b62` returned with no tracking error.
5. On the common chronological holdout at threshold 0.30: champion PR-AUC **0.8924**, challenger PR-AUC **0.9147**; champion recall **1.0000**, challenger recall **0.9918**. All three configured gates passed.
6. Administrator approval selected the candidate as active. Administrator rollback then restored `synthetic-20261112183037575079`.
7. A new post-rollback inference persisted `model_version=synthetic-20261112183037575079`, matching the selected active model.
8. MLflow run status was `FINISHED`; the joblib artifact downloaded successfully at 1,711,822 bytes. The Compose MLflow registry endpoint returned five registered versions. Audit records include the approval and rollback actions.
9. Recreated the API container without removing volumes; startup loaded the same selected model version from PostgreSQL and returned healthy. PostgreSQL and MLflow remained healthy and the frontend continued returning HTTP 200.

This result is synthetic-only. The 0.30 evaluation threshold and promotion margins are illustrative and not calibrated for real telecom deployment. The report distinguishes feature drift from concept drift and model performance degradation.

## Remaining acceptance gaps

- **Not implemented:** SHAP attributions for actual prediction features; advanced location/travel and scenario-specific evaluation; shadow/canary serving; delayed-label model performance monitoring.
- **Partially implemented:** incident assignment/status/notes/audit exist, but richer resolution provenance and advanced queue filters/search remain. User role/status API and controls now exist; broader administration/settings are not complete.
- **Implemented but not verified in a browser:** MLOps page production build passes and controls are wired to real APIs, but no Playwright/browser click-through was available in this pass.
- **Blocked by external access:** Hosted GitHub Actions execution was not observed; a Git remote exists, but the GitHub Actions CLI/session is unavailable here. After reviewing and committing the working tree, run `git push origin main`, then open the repository's **Actions → CI** page and inspect the backend, frontend, and containers jobs. Local checks above are not evidence of a hosted run.
- **Not implemented:** AWS deployment and its production controls. No AWS resources were provisioned.

## Phase 3 handover

The MLOps core demonstration and rollback acceptance path are verified. Do not represent Phase 2 as fully complete while the remaining SHAP/investigation gaps are still required. If those gaps are explicitly accepted as deferred, the next smallest Phase 3 task is deployment readiness review followed by AWS budget/IAM/topology confirmation; no AWS work was started here.

## Phase 3 completion pass — 2026-11-16 (supersedes the earlier gap statuses above)

The earlier report records the Nov 15 checkpoint. The following work was completed afterward and must be used as the current status.

### Implemented and verified in the local repository

- SHAP is pinned at `0.49.1` for Python 3.11+ compatibility in the current image matrix. Random Forest explanations use probability-output `TreeExplainer`; Logistic Regression explanations use `LinearExplainer` in the fitted scaler's feature space and report log-odds. The API loads the model version recorded on the saved prediction, checks feature schema/background version and additivity, calculates on demand, and persists the result/audit record. Investigation detail renders direction, feature, signed SHAP value and base/output values.
- Incident finalization persists outcome, reason, resolver and timestamp. Assignees must be active Fraud Analyst/Investigator accounts. Final status needs an outcome/reason; False Positive requires `legitimate`. Reopening clears current resolution fields but preserves prior audit events. Incident API filtering supports status/severity/assignee/search/limit; the frontend includes status/severity/assignee filters and search. Audit history is shown in case detail.
- Migration `0004_shap_resolution` adds prediction explanations and resolution columns; `0005_mlflow_run_reference` records MLflow run IDs. No database/MLflow volume was removed. The current PostgreSQL database is at Alembic head `0005_mlflow_run_reference`.
- Model loader can recover a missing trusted `.joblib` file through its stored MLflow run ID. Actual remote S3 recovery remains unverified because no AWS deployment exists.
- Production Compose/Caddy, private internal service networking, bind mount locations for encrypted EBS, PostgreSQL tracking backend, S3 artifact proxy, production docs disablement, CloudWatch awslogs, ECR immutable-tag build, GitHub OIDC and SSM deployment job are prepared. Production Compose config validated with only ports 80 and 443 published. This is preparation, not a live deployment.

### Browser click-through evidence

Using installed Chrome through Playwright against the rebuilt local Compose UI:

- Administrator login succeeded.
- MLOps lifecycle view rendered persisted dataset versions, model versions, registry entries, drift report, champion/challenger comparison and controls; 22 table rows were present across the page.
- An existing prediction's SHAP explanation rendered from the saved model and persisted prediction context.
- With the local UI user role changed to Auditor in the isolated browser context, `Run Complete MLOps Demo` was disabled and no approval control was rendered. No demo reset, retraining, promotion, or rollback was triggered by this browser check.
- Zero Playwright page runtime errors, failed requests, or API HTTP errors. A separate first-pass console check saw a generic resource 404; the detailed request monitor found no failed requests on the complete run.

### Commands and observed results

- `py -3.11 -m pytest tests -q` from `backend/` — **15 passed**, 17 dependency/deprecation warnings, including persisted MLflow run-ID and mocked missing-artifact retrieval coverage.
- `py -3.11 -m ruff check app tests` from `backend/` — **passed**.
- `npm run build` from `frontend/` — **passed**; the existing >500 kB JavaScript chunk warning remains.
- `docker compose build api web` — **passed**, including SHAP and boto3 installation.
- `docker compose up -d` — **passed** using pre-existing PostgreSQL, MLflow and model volumes; API, MLflow and web were recreated, DB stayed up.
- `docker compose ps` — API, PostgreSQL and MLflow healthy; web running.
- `docker compose exec -T api alembic current` — `0005_mlflow_run_reference (head)`.
- API-container request to `http://mlflow:5000/health` — HTTP 200; frontend `http://localhost:5173` — HTTP 200.
- `docker compose --env-file .env.production.example -f docker-compose.prod.yml config --quiet` — **passed**. Parsed config confirmed only Caddy has host ports 80/443; DB, MLflow, API and web publish none.
- `docker build --build-arg VITE_API_URL=/api -t teleguard-web:production-check ./frontend` — **passed**.
- `npm audit --audit-level=high` — **passed**, zero vulnerabilities after final filter UI edit.
- `docker compose build web` + `docker compose up -d web` — **passed**, retaining existing database/MLflow/model data.
- Final Playwright run against the rebuilt UI — admin login and six saved MLOps sections passed; 22 data rows rendered; all three incident filters rendered; real SHAP result rendered; Auditor controls disabled/hidden; zero page runtime errors, failed requests, or API errors.
- GitHub-hosted CI — **not run**; `gh` and authenticated GitHub access were unavailable.
- AWS deployment, HTTPS, S3 recovery, CloudWatch, backup/restore and live CI/CD — **not run**; AWS CLI/profile/credentials, resources and domain were unavailable. No cloud resources were created and no public endpoint exists.

### Current acceptance status

- Local app/MLOps lifecycle: verified, with previously recorded end-to-end training, MLflow, approval and rollback evidence.
- SHAP and investigation refinements: implemented and locally tested, including browser rendering.
- Production configuration: implemented and config-validated, not deployed.
- AWS deployment/release: blocked by external account/domain access.
- GitHub Actions hosted workflow: blocked by external repository settings/authentication; CI/CD is configured but unobserved.
- The earlier Nov 16 checkpoint below has been superseded by the final local verification section that follows. The previously listed scenario/location/travel, shadow/canary and delayed-label gaps were implemented and tested in this pass.

## Final local feature verification â€” 2026-11-16 (supersedes the outstanding-feature status above)

### Implemented

- Added synthetic coordinate fields with pair/range validation and Alembic revisions `0006_context_serving_labels` and `0007_backfill_model_observations`. Scoring compares each subscriber's prior event location using Haversine distance and elapsed time, applies administrator-configurable speed/time/risk thresholds, reports unusual new location tokens after sufficient history, and supports named event-type/location-token rules. Evidence is persisted in `Prediction.evidence`, contributes to risk score, appears in investigation detail, and explains when location is unavailable. Coordinates and scenario labels are excluded from supervised features. Existing predictions receive champion monitoring observations in the backfill.
- Bumped the recorded scoring policy to `risk-v2` because location/travel context now contributes to persisted risk scores.
- Added Administrator-only shadow/canary serving configuration stored as versioned PostgreSQL lifecycle records and audit events. A challenger must have a passing comparison against the current champion and its artifact must load/version-check before configuration. Shadow copies eligible inputs and persists its probability while champion output remains authoritative. Canary routes a deterministic event-ID share (0â€“100%) to the challenger. Per-model outputs and delayed outcomes persist in `model_observations`. Promotion, configured-candidate rejection, and rollback return serving to champion-only. Runtime challenger errors are audited and retain champion output.
- Added delayed-label ingestion for predictions with no label at prediction time. A PostgreSQL row lock and immutable-label check prevent duplicate updates; stored model observations receive the outcome once. Monitoring reports pending/received labels, precision, recall, FPR, confusion counts, Brier score and PR-AUC when both classes exist. With at least 40 labels per model, it compares the latest 20 outcomes with the prior 20 and emits an actionable alert when recall falls by 0.15 or FPR rises by 0.10. Overview and MLOps pages show this status; Event Explorer supports label entry.
- Added backend, Playwright and local Compose acceptance scripts. Updated feature specs, task status, event contract, README and this report.

### Verification evidence

- `py -3.11 -m pytest -q` â€” **19 passed** (17 dependency/deprecation warnings). Tests cover coordinate validation, impossible travel and missing location, scenario configuration bounds/RBAC, delayed-label immutability and metrics, a rolling degradation alert, admin-only serving controls, trained challenger shadow observations, 100% canary routing, safe champion retention after a simulated challenger load failure, and the existing retrain/compare/approval/rollback integration flow.
- `py -3.11 -m ruff check app tests scripts` â€” **passed**.
- `npm run lint` â€” **passed with 3 React hook dependency warnings** in existing one-line `App.tsx` effects; no lint errors.
- `npm run build` â€” **passed**; Vite reports the existing oversized JavaScript chunk warning (about 649 kB minified).
- `npm audit --audit-level=high` â€” **passed, zero vulnerabilities** after adding a patched minimatch override for the lint dependency tree.
- Fresh SQLite Alembic migration upgrade reached `0007_backfill_model_observations (head)`. A seeded pre-monitoring prediction was backfilled as a champion observation in SQLite. The revisions add nullable columns/table/indexes and seed monitoring rows; no existing records were deleted.
- `docker compose build api web` and `docker compose up -d api web` â€” **passed** with existing named volumes preserved. PostgreSQL stayed healthy; API and MLflow were recreated with the updated API image and web was rebuilt. `docker compose exec -T api alembic current` returned `0007_backfill_model_observations (head)`. PostgreSQL backfilled all 16 existing local predictions with a per-model observation; the missing-observation query returned zero.
- `py -3.11 scripts/local_feature_acceptance.py` against Compose API/PostgreSQL/MLflow â€” **passed**: impossible-travel evidence persisted; shadow retained champion `synthetic-20261112183037575079` while observing challenger `synthetic-20261115132320395767`; canary at 100% served the challenger; a delayed label was evaluated; duplicate labeling returned HTTP 409; serving was set back to champion-only.
- `docker compose restart api`, followed by `py -3.11 scripts/verify_feature_persistence.py` â€” **passed**: generated event and its `risk-v2` policy version, label/model observations, scenario threshold (`800 km/h`) and champion-only serving configuration remained in PostgreSQL after restart.
- `npm run test:e2e` against the rebuilt Compose UI with installed Chrome â€” **2 passed**: admin sees overview label health, MLOps monitoring/serving controls and location/travel configuration; Event Explorer exposes delayed-label entry. Backend tests verify non-admin authorization.
- No database volume, application data, MLflow experiment, registered model, or model artifact volume was reset. No AWS/cloud resource was created.

### Remaining boundaries

- The three previously outstanding features and local application flows are now verified. This does not mean every item in the full product blueprint is complete: transcript-based vishing is a deferred P2 module; hosted GitHub Actions was not observed; AWS deployment was explicitly not performed. This build uses synthetic coordinates/events and illustrative speed, traffic, label-window and degradation thresholds. It has no external geocoding or source-confidence data, and performance alerts require labels rather than proving fraud.

## Superseding 2026-11-19 acceptance

The later full pass expanded and verified the normalized 150,000-row operational dataset, worker-backed generation/training, three-candidate MLflow lifecycle, same-holdout comparison/approval/rollback, CSV ingestion, Data observatory and Live monitoring. Exact database counts, benchmark metrics, test results, synthetic-risk caveats and the current AWS NO-GO decision are in [IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md](IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md). Historical counts and omissions above should not be read as the current local state. AWS deployment remains unperformed.
