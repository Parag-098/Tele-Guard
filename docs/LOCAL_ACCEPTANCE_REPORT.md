# TeleGuard AI Local Acceptance Report

**Date:** 2026-11-16  
**Environment:** Windows host, Python 3.11 tests, React/Vite production build, Docker Compose, PostgreSQL 16, MLflow, installed Chrome/Playwright.  
**Scope:** Original local product requirements and the three outstanding features called out in `FINAL_VERIFICATION_REPORT.md`. This report records observed outcomes; AWS deployment and hosted CI were not attempted.

## Acceptance results

| Requirement | Result | Evidence |
|---|---|---|
| Scenario, location and travel evaluation | **Pass** | Two synthetic coordinate events for one subscriber, about 1,150 km apart and 60 minutes apart, produced a persisted `impossible_travel` finding. It contributed to the saved risk assessment. Missing coordinates/location safely skip geographic analysis with evidence. |
| Scoring policy version | **Pass** | Location-aware results are recorded as policy `risk-v2`; the same version was read from the persisted prediction after an API restart. |
| Configurable scenario thresholds/rules | **Pass** | Administrator API configured a speed threshold of 800 km/h; validation rejected an out-of-range value. Persisted configuration was still 800 km/h after an API restart. Rules can match configured synthetic event types or location tokens. |
| Investigation explanation | **Pass** | Incident evidence UI renders the location/travel summary and individual findings. Playwright verified the location/travel panel and existing investigation evidence path remains in the backend suite. |
| Shadow serving | **Pass** | A persisted candidate received copied inputs and stored separate probabilities while the champion version remained on the actual prediction. Shadow and champion observation counts were visible to monitoring. |
| Canary serving | **Pass** | With configured traffic at 100%, the candidate version served the event prediction and its observation was persisted. Configuration at 0â€“100% is administrator-only and event-ID assignment is deterministic. |
| Candidate failure safety | **Pass** | Backend integration test forces a configured challenger load failure; response remains tagged with the champion and an audit record says the champion was retained. Invalid/unloadable challengers are rejected when configuring serving. |
| Deployment decisions and rollback | **Pass** | Candidate serving requires a passing comparison against the current champion. Existing MLOps integration test trains, compares, approves/rejects and rolls back; promotion/rollback return serving configuration to champion-only. |
| Delayed-label ingestion | **Pass** | New predictions begin unlabeled. A label updates all per-model observations, duplicate submission returns HTTP 409, invalid labels return HTTP 422, and pending/received counts update. |
| Delayed-label metrics and alerting | **Pass** | Precision, recall, FPR, confusion counts, Brier score and PR-AUC (when both classes exist) are computed from labeled observations only. A backend test creates 40 sequential synthetic labels with a 1.0-to-0.0 recall decline and verifies an actionable rolling degradation alert. |
| Dashboard integration | **Pass** | Overview shows pending/received labels and alert state; MLOps displays per-version metrics, rolling alert guidance and serving mode; Event Explorer exposes label entry. Two Playwright tests passed against the rebuilt Compose UI. |
| PostgreSQL migration and restart persistence | **Pass** | Alembic revisions through `0007_backfill_model_observations` applied to the existing PostgreSQL database. The backfill populated all 16 pre-existing local predictions (zero missing observations). After restarting the API container, a synthetic event, its `risk-v2` policy version, label metrics, serving mode and scenario threshold were read back successfully. |
| No destructive data action | **Pass** | No database, model, or MLflow volume reset/removal occurred. No cloud resource was provisioned. |

## Commands and results

- `py -3.11 -m pytest -q` from `backend/` â€” **19 passed**, 17 dependency/deprecation warnings.
- `py -3.11 -m ruff check app tests scripts` from `backend/` â€” **passed**.
- `npm run lint` from `frontend/` â€” **passed, 0 errors and 3 React hook dependency warnings**.
- `npm run build` from `frontend/` â€” **passed**; Vite's existing large-chunk warning remains (about 649 kB minified JS).
- `npm audit --audit-level=high` from `frontend/` â€” **passed, zero vulnerabilities**.
- Fresh SQLite migration: `$env:TG_DATABASE_URL='sqlite:///./migration_fresh_check.db'; py -3.11 -m alembic upgrade head; py -3.11 -m alembic current` â€” **head `0007_backfill_model_observations`**. A separate migration acceptance seeded a prediction at revision 0006 and verified revision 0007 backfilled its model probability/outcome record.
- `docker compose build api web` and `docker compose up -d api web` â€” **passed**; PostgreSQL data and named volumes retained.
- `docker compose exec -T api alembic current` â€” **`0007_backfill_model_observations (head)`**; PostgreSQL verification found 16 predictions, 16 distinct prediction observations and zero missing observations.
- `py -3.11 scripts/local_feature_acceptance.py` from `backend/` â€” **passed** against Compose. Output reported impossible-travel, shadow champion/challenger versions, 100% canary, delayed label receipt and duplicate-label HTTP 409.
- `docker compose restart api` followed by `py -3.11 scripts/verify_feature_persistence.py` â€” **passed**, including the prediction's `risk-v2` policy version.
- `npm run test:e2e` from `frontend/` against the rebuilt Compose UI â€” **2 passed**.

## Broader original-spec acceptance boundaries

The local app's previously verified login/RBAC, synthetic event ingestion, hybrid risk scoring, graph evidence, incident workflow, SHAP explanation, MLflow training/registry, champion/challenger quality gates and rollback remain covered by the existing backend tests and prior evidence in `FINAL_VERIFICATION_REPORT.md`.

This report does not claim full product-blueprint completion. Transcript-based vishing is deferred; AWS public deployment, HTTPS, S3 recovery, CloudWatch and hosted GitHub Actions were not run (AWS work was explicitly prohibited for this task). The new travel heuristics and monitoring thresholds are demonstrative synthetic-data settings, not calibrated real-world fraud policy. Location coordinates are synthetic and no geocoder or source confidence is integrated.

## Latest acceptance run — 2026-11-19

This file records the earlier smaller acceptance checkpoint. The later full implementation and local acceptance report at [IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md](IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md) supersedes its row counts and feature gaps: it includes the real 150,000-row PostgreSQL dataset, its trained candidate/MLflow record, the `0008` migration, expanded tests, API performance fixes and browser checks. AWS remains unprovisioned.
