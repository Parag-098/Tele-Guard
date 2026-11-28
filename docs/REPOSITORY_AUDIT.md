# TeleGuard AI Repository Audit

> The opening sections are the original 2026-11-12 documentation-only audit. Subsequent dated sections preserve later checkpoints. Use the [2026-11-28 incremental release audit](#incremental-release-audit-2026-11-28) for current findings and their required fixes.

**Audit date:** 2026-11-12
**Scope:** Complete visible workspace, project specifications, feature specifications, and prompts.
**Repository state:** Documentation/starter-pack only. The workspace has no `.git` directory, so Git status/history and diff verification are unavailable.

## Executive summary

This workspace defines a substantial educational telecom-fraud simulation product, but it does not contain an application implementation. The README calls it a planning/specification baseline; inspection confirms that assessment. No frontend, backend, schema/migrations, model pipeline, tests, runtime containers, or AWS deployment artifacts were present in the full recursive file inventory. Therefore no runtime feature can be classified COMPLETE or verified as working. Requirements below are classified against implementation evidence, not against plans or illustrative architecture diagrams.

The recommended direction is to retain the documented stack and build a single deployable modular monolith: React + TypeScript UI, FastAPI/Python API and offline training commands, PostgreSQL with migrations, scikit-learn first, NetworkX for graph indicators, Docker Compose locally, and an AWS EC2 deployment using ECR, S3, IAM, CloudWatch and HTTPS. Keep MLflow private/internal and separate training from online inference. AWS is a compulsory delivery gate, not a future optional enhancement.

## Repository evidence and current state

The recursive workspace inventory contains only:

- Root guidance and planning: `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `TASKS.md`, product blueprint, execution plan, `.env.example`, `.gitignore`.
- Documentation: `docs/DATA_DICTIONARY.md` and three feature specifications (`scenario-lab.md`, `model-lifecycle.md`, `investigation-and-response.md`).
- Prompts: five reusable prompt files.
- `.github/workflows/README.md`, which explicitly labels CI as a placeholder.

No source-code directories/files, package manifests, lockfiles, schema or migration files, model artifacts, datasets, Docker configuration, CI workflow YAML, deployment templates/scripts, or tests appeared in the inventory. `git status --short` could not run because the directory is not a Git repository. This is a blocker to inspecting history, confirming tracked state, or validating a clean diff; it does not prevent inspection of the files currently present.

### Existing implementation by area

| Area | Verified state |
|---|---|
| Frontend | **MISSING.** No React app, assets, routes, or build manifest. |
| Backend/API | **MISSING.** No FastAPI app, endpoints, request/response schemas, or integrations. |
| Database/persistence | **MISSING.** No PostgreSQL models, schema, migrations, or persistence code. PostgreSQL is specified, not configured. |
| Synthetic data | **MISSING.** Requirements and examples exist in docs; no generator, CSV, or dataset found. |
| ML and features | **MISSING.** No preprocessing, feature code, training pipeline, model, inference path, metrics, or evaluation output. |
| MLOps | **MISSING.** MLflow, registry, gates, monitoring, drift, retraining, promotion, and rollback are documented aspirations only. |
| Investigation and response | **MISSING.** Feature spec only; no incidents, notes, labels, simulated actions, or audit implementation. |
| Authentication/RBAC | **MISSING.** Roles and backend authorization are specified; no auth/session code or permission tests. |
| Tests and CI/CD | **MISSING.** No test suite or workflow YAML. The workflow README defers CI until T007. |
| Docker | **MISSING.** No Dockerfile or Compose file. `.env.example` contains proposed runtime values, not a runnable service setup. |
| AWS readiness | **MISSING.** No IaC, deployment scripts, ECR/EC2/S3/IAM configuration, HTTPS setup, monitoring, backup, or public endpoint evidence. |
| Security/privacy | **PARTIAL (documentation only).** Strong simulation and privacy guardrails exist in `AGENTS.md` and product docs. No implemented controls can be verified. `.env.example` has a clearly marked local-only placeholder secret and demo DB credentials; it must never be used as production configuration. |

## Feature-by-feature status

Status means implemented and verified in this workspace. A spec, backlog item, or proposed architecture is not implementation evidence.

| Feature/capability | Status | Evidence / gap |
|---|---|---|
| Synthetic scenario lab and event simulator | **MISSING** | `docs/features/scenario-lab.md` gives requirements and acceptance criteria; no generator, API, UI, seed/replay behavior, or persistence exists. |
| Event ingestion, validation, idempotency, upload | **MISSING** | Product blueprint and data dictionary define desired behavior; no endpoint, validator, or event store. |
| Shared as-of feature engineering | **MISSING** | Feature families and leakage rules are documented; no implementation or tests demonstrate parity or temporal safety. |
| Time-aware data splits and leakage controls | **MISSING** | Required by model lifecycle spec; no dataset builder, split code, or leakage tests. |
| Supervised fraud model and evaluation | **MISSING** | Candidate algorithms/metrics are proposals; no training code, model, report, or reproducible run. |
| Anomaly detection | **MISSING** | Isolation Forest is proposed; no fitted detector or separately persisted score. |
| Entity graph intelligence | **MISSING** | NetworkX is proposed; no graph construction, signals, provenance, or visualization. |
| Versioned rules | **MISSING** | Requirements are described; no rule store/evaluator/versioning. |
| Distinct signals and unified risk policy | **MISSING** | Architecture provides an illustrative contract; no concrete API schema or scoring implementation. |
| Explainability and evidence provenance | **MISSING** | SHAP and evidence are requirements; no explanations or prediction evidence store. |
| Incident investigation workflow | **MISSING** | Feature spec lists queue, assignment, notes, labels and resolution; no code or database objects. |
| Permissioned simulated responses and audit | **MISSING** | Guardrails and desired actions documented; no authorization, action state machine, reversals, or audit log. |
| Authentication and backend RBAC | **MISSING** | Four roles described; no identity system, backend checks, or tests. |
| Analyst dashboard and explorer UI | **MISSING** | Pages listed in blueprint; no frontend. |
| Model tracking/registry/version attached to predictions | **MISSING** | MLflow is proposed; no tracking setup, artifact, registry, or inference metadata. |
| Evaluation gates and controlled promotion | **MISSING** | Acceptance criteria in feature spec; no gate implementation or promotion workflow. |
| Shadow/canary/rollback | **MISSING** | Requirements only; no routing, comparison, rollback, or evidence. |
| Drift/performance monitoring | **MISSING** | Requirements only; no reference data, monitor, delayed-label distinction, or alerts. |
| Feedback and candidate retraining | **MISSING** | Requirements only; no feedback provenance or retraining job. |
| Vishing/transcript classifier | **MISSING (P2/deferred)** | Blueprint marks this as separate and not a core blocker; no dataset/license review or module. |
| Dockerized local environment | **MISSING** | No Docker configuration. |
| Automated CI and test coverage | **MISSING** | No tests/workflow; only placeholder workflow guidance. |
| AWS public deployment and persistent storage | **MISSING** | Compulsory requirement; no deployment implementation or evidence. |

No feature is **BROKEN** based on executable evidence because there is no executable application to run. No feature is **COMPLETE**. A few documentation-level foundations are present, but these do not meet runtime acceptance criteria.

## Requirement and architecture findings

### Strengths in the existing plan

- Scope consistently frames the system as an educational simulation using synthetic identities and events; it excludes carrier connectivity, private real communications/location data, and real subscriber blocking.
- Architecture calls for a modular monolith, distinct online inference and offline training, versioned features/model/policy, temporal leakage controls, evidence storage, backend RBAC, and auditable human-approved simulated actions.
- Feature specifications cover scenario reproducibility, investigation lifecycle, and core model lifecycle acceptance points.
- AWS direction names practical building blocks and calls out HTTPS, IAM, backups, costs, and keeping internal services private.

### Most important architectural gaps/risks

1. **There is no application foundation.** Documentation names no actual module/package layout or runnable entry points; all workflows are unimplemented. Phase 2 must establish a working end-to-end vertical slice before adding breadth.
2. **The AWS database choice is unresolved.** `DECISIONS.md` leaves EC2-hosted PostgreSQL versus RDS open. Choose based on a recorded budget/backup gate before provisioning; do not let this delay the application slice. RDS is the safer default when the budget supports it; otherwise use encrypted persistent block storage, restricted access, and tested backups on EC2.
3. **Training-serving contract is conceptual.** The data dictionary calls itself a starting contract and field names differ in places across documents (`event_time` vs `event_timestamp`, `network_token` vs `ip_token`, `fraud_label` vs `label_fraud`). Phase 2 must define one versioned canonical schema and remove ambiguity before generation/inference code is written.
4. **Risk calibration and gates lack operating definitions.** No threshold, weights, tolerances, dataset volume, or acceptance values are specified. Keep component signals separate; use a documented deterministic initial policy and gates based on the synthetic validation set, with explicit caveats. Never claim real-world performance.
5. **The product scope is too broad for one undifferentiated build.** Vishing, CSV batch upload, live simulation, ten dashboard pages, graph explorer, model release controls, and public AWS deployment cannot all be treated as equal first-slice blockers. Prioritize P0 end-to-end flows and implement P1 lifecycle operations only after reliable persistence and RBAC; defer P2 features.
6. **AWS release needs operational design.** No secret delivery, TLS/DNS, database backup/restore, image versioning, health checks, rollout/rollback, logging/alarms, budget alert, or teardown path exists. Phase 3 must prove these, not just publish a URL.
7. **No repository metadata is available.** Absence of `.git` means branch history, untracked/ignored status, and diff review cannot be verified. Initialize/restore the intended Git repository before implementation and retain a secret-safe ignore policy.

## Recommended technology stack and architecture changes

Retain and make the documented baseline concrete:

- **UI:** React + TypeScript (Vite is a sensible lightweight build choice).
- **API and jobs:** Python + FastAPI; modular package, background/offline training as explicit commands or a small worker process. No separate microservices initially.
- **Persistence:** PostgreSQL, SQLAlchemy/Alembic (or an equivalent migration-backed ORM); keep raw events, predictions/signals/evidence, incidents/actions/audit, and model metadata distinct.
- **ML:** Pandas/NumPy/scikit-learn first. Start with Logistic Regression plus two justified tabular candidates. Add XGBoost/LightGBM only if available and comparison warrants it. Isolation Forest is a separate signal. NetworkX for explainable graph metrics. SHAP only for compatible models and when its explanation can be tested.
- **MLOps:** MLflow for experiments and model metadata/artifacts, with artifacts in S3 in AWS. Keep tracking UI/API private. Dataset/generator version and source revision must be recorded. Do not add DVC unless files/teams make it useful.
- **Validation/monitoring:** Pydantic at API boundaries; Pandera or equivalent for tabular dataset validation. Begin with transparent, tested drift summaries rather than adding a monitoring platform without need.
- **Local runtime/CI:** Docker Compose; GitHub Actions for backend/frontend checks, tests, image build, and later controlled deployment.
- **AWS (mandatory):** ECR + EC2 running Docker Compose for the first deployment; S3 for artifacts; least-privilege instance role; CloudWatch logs/alarms; public UI/API behind HTTPS reverse proxy or load balancer. PostgreSQL on RDS when budget allows, otherwise encrypted persistent storage with explicit backup/restore proof. Never publish DB or MLflow ports.

Architecture changes needed: turn the logical diagram into a concrete package/schema/API contract; standardize field names; add authentication bootstrap and role/permission matrix; specify incident/action states and idempotency; define model version and risk policy metadata; record deployment, secret, backup, and teardown procedures. Keep the vishing module and advanced infrastructure out of the critical path.

## Dependency/environment and verification results

- No `pyproject.toml`, `requirements*.txt`, `package.json`, lockfile, Dockerfile, Compose file, workflow YAML, tests, or runnable application command exists in the workspace. Consequently there is no application/test/lint/build command to run in this audit phase.
- `.env.example` is a template with local development values (`APP_SECRET_KEY=replace_for_local_development_only`, demo DB credentials, an MLflow URL). It is not proof that those services exist and is unsafe as a production secret source.
- `git status --short` result: failed with “not a git repository”; no diff/history check could be performed.
- No application behavior, cloud deployment, security control, or test result is claimed as verified.

## Work split and acceptance summary

The implementation roadmap is in [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md). Phase 2 establishes the complete local application core and end-to-end synthetic incident journey. Phase 3 integrates, hardens, proves the MLOps lifecycle, and deploys/verifies on AWS. The proposed sequence reduces prompt count while retaining internal dependency gates and acceptance checks.

## Follow-up re-audit (2026-11-16)

This document records the original empty-workspace audit and remains historical. The checked-out repository now contains the implemented application and MLOps lifecycle. The current Phase 3 re-audit found that SHAP, resolution provenance, investigation filters, and browser verification have since been completed locally; see [FINAL_VERIFICATION_REPORT.md](FINAL_VERIFICATION_REPORT.md). Production Compose/CI release wiring is prepared and locally validated, but AWS and hosted GitHub execution remain blocked by unavailable external access. Do not use the original “no application implementation” findings as the current repository state.

**Decision blockers:** AWS account/region and monthly budget or student credits; domain/DNS availability (HTTPS can still use an AWS-hosted hostname if no custom domain); and whether a suitable account permits RDS or whether the lowest-cost EC2 persistence option is required. The application stack and simulation boundary do not require further user decisions.

## Latest implementation state — 2026-11-19

The audit checkpoint above predates the 150,000-row versioned operational dataset, durable seed worker, data observatory, CSV path and final MLOps promotion acceptance. See [IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md](IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md) for the current code/spec comparison and live local evidence. It records a **NO-GO** recommendation for AWS until the release-image build and cloud acceptance gates are verified.

## Incremental release audit 2026-11-28

Scope: tracked repository at 1898bd984d1fd6e505e5ba26fe2160885c3684ef and existing local Docker state. The tracked application is a FastAPI/React/PostgreSQL modular monolith with Alembic revisions 0001–0008, MLflow, a single PostgreSQL-backed worker, local API, worker, PostgreSQL, MLflow and web services, with a production Caddy proxy, tests and AWS release preparation. Git was clean for tracked files before documentation edits. Two pre-existing acceptance-ID files were untracked. Neither was modified.

### Current code and acceptance evidence

| Area | Current checkout | Evidence boundary |
|---|---|---|
| Data and ingestion | event-v1 validation, individual event ingest, atomic CSV up to 5,000 rows / 25 MB, deterministic 100k–300k large-seed workflow, normalized dataset/version/job records and progress. Scenario lab endpoint creates seeded events synchronously. | The 2026-11-28 audit repeated the earlier read-only check using an isolated PostgreSQL copy with the original volume mounted read-only. It verified status ready, seed 20261119, 150,000 unique events, 150,000 predictions, 90,000 positive and 60,000 negative labels, and the HistGradientBoosting run with 150,000 input rows and a stored MLflow run reference. |
| ML and risk | features-v2 has 18 columns with v1 compatibility, Logistic Regression/Random Forest/HistGradientBoosting, chronological 70/15/15 split, Isolation Forest, NetworkX, rules and location context. SHAP uses the persisted model version. | Training and candidate metrics reported on 2026-11-19 were synthetic. The fitted candidate, model promotion, rollback and subsequent prediction were exercised historically. Parity and exact historical feature reconstruction need expansion. |
| Analyst/security | JWT and revocable sessions, five backend roles, filters/assignment, graph explorer, notes, outcome/audit history, SHAP, audited reversible simulation and delayed label API. | Existing backend tests and Playwright acceptance cover role and workflow behavior historically. Automated label reconciliation and cases spanning multiple events remain planned. |
| MLOps/operations | MLflow registered versions and artifacts, DB model pointer, shadow/canary controls, PSI against demo snapshots, delayed-label dashboards, worker leases yet to be generalized, API process stats, real DB and worker status. | Prior recorded tests include 22 backend passes and three Playwright passes. No scheduled monitoring or automatic operational training exists today. AWS log and release files are prepared. |
| Environment | Current Docker Compose inventory has API, DB, MLflow and web stopped, and a restarting worker. Worker reported a PostgreSQL hostname/connection failure in the preceding review. Production Compose static synthesis passed. | Full runtime and test suite were not re-executed for documentation. Start in a disposable environment under TG-T00 and capture actual evidence. There is no independently verified AWS-hosted release in the repo. |

Details and full prior measurements remain in the [2026-11-19 acceptance](IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md). Relevant source includes [main.py](../backend/app/main.py), [ml.py](../backend/app/ml.py), [batch_scoring.py](../backend/app/batch_scoring.py), [synthetic.py](../backend/app/synthetic.py), [dataset_jobs.py](../backend/app/dataset_jobs.py), [worker.py](../backend/app/worker.py), [tests](../backend/tests/test_core.py) and [production Compose](../docker-compose.prod.yml).

### Fix register

| ID and priority | Finding and reproduction | Phase and pass condition |
|---|---|---|
| TG-F01 high | Both scorers convert only the first four bytes of the event ID to a bucket. All tg2_ IDs land in 59 and all evt_ IDs in 55. Configured 10% yields zero traffic from either group. | TG-T01 / E-06. Stable full-subscriber hash, assignment and actual traffic evidence with fallback at each rollout stage. |
| TG-F02 high | Comparison thresholds are 0.30, fit reports and observation labels 0.50, and batch jobs hardcode risk-v2/0.35 while online policy uses settings. | TG-T01 / E-04, E-06. Persisted policy version and classifier threshold shared across entry points, documented separate incident threshold and legacy history intact. |
| TG-F03 high | Approval checks the latest comparison and candidate, but can accept stale evidence after the champion changes. In-process state can be set before commit. Initial seed path can activate a candidate based on no pre-existing predictions. | TG-T01 / E-06. Transactional current-release evidence, explicit initial bootstrap and stale/concurrent safety tests. |
| TG-F04 high | Synthetic scenarios cycle in 12-event blocks and subscriber history is typically three events. Fraud label is direct scenario membership, 60% positive in the historical sample. Prior near-perfect validation is generator-dependent. | TG-T02, TG-T03 / E-02, E-05. Long histories, difficult overlap, variable prevalence, namespace and temporal holdouts with group/leakage checks. |
| TG-F05 high | Online scoring uses a capped and partly unordered context, while batch builds a separate in-memory state. Tied/late ordering, configurable risk thresholds, and exact historical explanations are edge cases. | TG-T01, TG-T03 / E-04, E-05. Test across shared contract, all ingest paths and as-scored explanation replay. |
| TG-F06 high | Drift uses DemoDataset snapshots and fixed PSI settings on a few raw fields. Delayed-label alert statistics use two 20-label groups and little support/bias context. No served feature window, schedule or automatic triggers. | TG-T04 / E-07. Real cohort windows, support, repeated breaches and quality/label/shift distinctions. |
| TG-F07 high | Initial seed is durable; both training routes and operational comparison can run in requests, and the seed workflow materializes training rows. Worker startup requeues running jobs under a single-worker assumption. | TG-T05 / E-08. Typed jobs, lease, bounded resource use, checkpoint/retry/MLflow reconciliation and safe cancellation. |
| TG-F08 high | Prior seed generated 133,165 individual incidents; no bounded cross-event correlation. Current analyst outcomes do not form a governed dataset feedback loop. | TG-T06 / E-09, E-10. Measured paired replay, explicit label provenance and guard against unrelated merge. |
| TG-F09 medium | Status API provides mean request latency/process counts. The release script’s smoke check tests basic API/database connectivity. CloudWatch logs driver and backup script exist; no observed full release or backup/restore. | TG-T08, TG-T09 / E-12, E-13, E-15. Readiness/model/worker health, bounded CloudWatch indicators, exact-image and restore evidence. |
| TG-F10 medium | In-memory/path-dependent model loading, challenger artifacts loaded in scoring path, and timing-sensitive late labels can compromise performance or reproducibility. Seed job marks data ready before MLflow publishing finishes. | TG-T01, TG-T05, TG-T08 / E-05, E-08, E-12. Separate dataset/model readiness, verified versioned cache, source attribution and cold recovery. |
| TG-F11 medium | CI has SQLite tests, container builds and static Compose checks. Workflow does not run PostgreSQL recovery and Playwright as part of release gating. The most recent acceptance used source/bundle updates after the exact image rebuild failed. | TG-T00, TG-T08 / E-01, E-12, E-13. Clean exact-source image and production-shape CI, plus artifact and persistence evidence. |
| TG-F12 medium | Public API instance is supported by settings, but browser tokens are persisted in localStorage and rate-limit/health boundaries need validation. Deployment scripts rely on host-prepared configuration and backup only dumps the named app database. | TG-T08 / E-11–E-13. Harden sessions, input limits and redaction; restore app and MLflow metadata plus artifacts; audit roles and OIDC. |

The proposed EC2 deployment is single-node with synthetic evidence only. Exact release build, host sizing, cloud budget, account/DNS permissions and independent hosted acceptance remain open. T00 is the earliest implementation task after separate authorization.

### Resumed acceptance findings — 2026-11-28

| ID and status | Finding and reproduction | Resolution / remaining gate |
|---|---|---|
| TG-F13 high — resolved locally | The production MLflow 2.21.2 PostgreSQL backend was configured with psycopg 3. Experiment creation succeeded, but subsequent experiment/run queries could compare an integer column to a text bind and fail. The first release backup smoke stopped after this failure. | Add pinned psycopg2-binary for the MLflow backend URI only; retain psycopg 3 for the application. Rebuilt API image passed production-shaped experiment creation, artifact logging and artifact download against PostgreSQL. |
| TG-F14 medium — resolved locally | Restore manifest validation accepted the GNU `sha256sum` text marker but rejected the standard binary-mode `*filename` marker produced by Git Bash, blocking the cross-platform local restore drill. | Restrict permitted filenames while accepting both two-space and space-star checksum forms. Full isolated app/MLflow PostgreSQL restore then passed. |
| TG-F15 low — resolved for local acceptance | The production release smoke assumed `jq`, `python3`, and `flock`, which were not available in the Git Bash acceptance environment. | Use standard-library Python JSON parsing with a `python` fallback, and an atomic directory lock fallback only where `flock` is absent. Linux production retains `flock`. Full local smoke passed after these fixes. |
| TG-F16 high — resolved locally | A supported degraded one-hour performance window queued training from that window's 60 labels. Chronological 70/15/15 evaluation then rejected the worker input because its validation/test partitions did not each contain both labels; automatic retraining never produced a candidate. | Freeze all released, cohort-scoped labels available by the monitoring cutoff (newest 10,000 maximum) and queue only when all chronological partitions contain both classes. A seven-window synthetic replay now triggered the worker, registered an MLflow-backed candidate and left champion state unchanged. |

Detailed command results are in [local acceptance evidence](LOCAL_ACCEPTANCE_2026-11-28.md). These fixes close local acceptance issues but do not resolve the open E-04, E-06, remaining E-08, E-09–E-11 and E-13 matrix rows or authorize E-15 cloud execution.

### Resumed execution findings — 2026-11-28

| ID and status | Finding and reproduction | Resolution / remaining gate |
|---|---|---|
| TG-F17 high — resolved locally | Upgrading to MLflow 3 exposed safe `skops` deserialization rejecting sklearn HistGradientBoosting's internal `TreePredictor`; training endpoints fell back to `mlflow.unavailable` and lost the run ID. | Log with MLflow 3's `name` parameter and explicitly trust only the `TreePredictor` type from internally instantiated/fitted candidates. Full production-dependency test suite passed (38 passed, 1 skipped) and training audit no longer reports `mlflow.unavailable`. |
| TG-F18 medium — resolved locally | The frontend's remote Google Fonts stylesheet stayed pending in the local browser network and made Playwright `page.goto(..., waitUntil: load)` time out even though static assets returned HTTP 200. | Removed the external font import and use system/monospace stacks. Direct Chrome navigation against the rebuilt production static image returned HTTP 200 and the expected title. |
| TG-F19 medium — resolved in release smoke setup | The development Compose web image contained `http://localhost:8000/api`, so using it with production-shaped Compose left browser sign-in on the login view; the release artifact requires same-origin `/api`. | Built `teleguard-web:release` with `VITE_API_URL=/api` (the CI argument). The full production-shaped smoke then passed its browser MLOps assertion and backup/restore path. |
| TG-F20 high — investigation open | Docker Scout reports setuptools 70.3.0 at pip's embedded `pip/_vendor/bom.cdx.json` even though installed `setuptools` imports as 84.2.1 and the SBOM also lists 84.2.1. The final frontend image scan failed because the GHCR Trivy Java database download returned `unexpected EOF`. | Treat the API finding as unresolved pending a scanner/source-of-record reconciliation; do not suppress it or claim a clean image scan. Rerun exact release-image scans once the scanner database path works. The previous Alpine UI finding is historical and does not verify the replacement Debian image. E-13 remains open. |

The current exact local acceptance, including the 2026-11-28 Python 3.12 suite and production-image browser/restore rerun, is in [LOCAL_ACCEPTANCE_2026-11-28.md](LOCAL_ACCEPTANCE_2026-11-28.md#latest-secure-runtime-and-production-release-rerun-2026-11-28). Earlier rows above preserve the original audit's state and evidence; this resumed table supersedes only the current-runtime claims it explicitly addresses. E-04, E-06 concurrency, remaining E-08, E-09–E-11, E-12 cold recovery, E-13 and E-14 are still incomplete. AWS E-15 and hosted GitHub actions remain external; AWS is not authorized.

### Additional resumed finding — 2026-11-28

| ID and status | Finding and reproduction | Resolution / remaining gate |
|---|---|---|
| TG-F21 high — resolved locally; E-11 partial | The Event Explorer “Add label” callback wrote binary labels directly through the delayed-label endpoint without a reasoned adjudication, and the shared UI exposed enabled case/model mutation controls to roles that backend guards denied. | Route user-reviewed labels through `/predictions/{event_id}/adjudications` with a required rationale and make scenario, model, case and response controls reflect the existing backend role matrix. Add a browser regression that persists reviewer/outcome/reason/time and checks Fraud Analyst, Investigator, ML Engineer and Auditor boundaries. The five-test browser suite passed. Full keyboard/responsive/error/redaction and all-route role coverage remain open. |
| TG-F22 high — resolved locally; E-04 partial | Single-event and CSV ingestion treated an existing event ID with different immutable payload as a harmless retry, and there was no deterministic ID lock spanning overlapping CSV writes. A scheduled simulator conflict could abort the tick after the same collision began returning `409`. | Compare full normalized event payload on retry; preserve exact retry idempotence but return `409` for conflicting single/CSV input; lock CSV IDs in stable order on PostgreSQL; reject a CSV before any row is inserted; quarantine scheduled collisions and continue the tick. Unit tests cover 206-history tied-time parity and simulator quarantine; a live PostgreSQL API browser test covers identical/conflicting races and CSV atomicity. E-04 still needs cross-path same-manifest worker/replay and remaining corruption/late-context evidence. |
| TG-F23 medium — resolved locally; E-11 partial | Browser accessibility inspection found the responsive sidebar controls lost accessible names at the mobile breakpoint, the dashboard risk chart did not expose its saved band counts to assistive technology, and investigation rows were not keyboard-operable. | Add explicit navigation names, a count-bearing chart accessible name, and a keyboard-focusable investigation action with visible focus styling. `frontend/e2e/ux-accessibility.spec.ts` passed at 390px with no horizontal overflow, verified chart semantics, sidebar keyboard navigation and Enter-key investigation opening. This closes those observed defects only; broader E-11 error/partial-service, redaction and route/role testing remains open. |

### Re-audit of remaining release findings — 2026-11-28

| ID and status | Latest evidence | Disposition |
|---|---|---|
| TG-F20 — partially resolved / E-13 open | The exact API image is `sha256:633dcd9945f341f1aa5ea185a727caf454f3412c12abc6847f095107d6865ac9`. Docker Scout reports 0 critical, 1 high, 2 medium, 28 low; setuptools 70.3.0 points to pip's embedded CycloneDX BOM while the installed package is 84.2.1 and the pip vendor module is absent. The exact Debian web image is `sha256:28f3a7c3706aa9d1be96d87cfa74a41d77efc390c4e80e001ab38382dbe55615`; full Trivy scan is waiting on Java DB retrieval from public ECR. `npm audit --audit-level=high` is clean. | Do not suppress the discrepancy or claim the container scan is clean. Preserve exact scanner/package evidence and mark E-13 partial until scanner results and disposition are complete. |
| TG-F24 medium — resolved locally; host-size follow-up | One API worker accumulated a queue under sustained load. Production support for bounded Uvicorn workers now uses `TG_API_WORKERS` (1–8, production default 2), and each process refreshes the committed active model pointer before readiness/inference. Exact two-worker sustained test persisted 7,200/7,200 requests without errors; steady-only p95 125 ms. | Regression verifies stale process refresh after another worker promotes. Compose exposes worker setting. This is measured on a 16-logical-CPU local host; no AWS claim. Combined burst p95 was 4.657 s, so evaluate burst/headroom separately. Terraform/AWS starting RAM recommendation increased to 8 GiB after observed MLflow peak memory; region-specific budget calculation remains pending. |
| TG-F25 medium — resolved locally; scope boundary retained | Exact release smoke rerun on current API/web digests migrated a fresh PostgreSQL DB, performed authenticated inference and MLflow artifact round-trip, restarted API/worker, restored app and MLflow metadata in a network-isolated database and served an authenticated prediction from the restored champion. | Confirms local release artifact/recovery compatibility only. It does not prove S3, CloudWatch, HTTPS, or AWS restore. |

See [current local acceptance](LOCAL_ACCEPTANCE_2026-11-28.md#integrated-local-lifecycle-and-final-acceptance--2026-11-28) and [exact evidence JSON](evidence/integrated-lifecycle-2026-11-28.json).

### Final audit reconciliation — 2026-11-28

The following dispositions supersede only the older “open” status for these findings; the original finding and its historical reproduction remain preserved above.

| ID and status | Latest evidence | Disposition |
|---|---|---|
| TG-F20 high — discrepancy reconciled; scanner output retained | Exact API image Scout count remains 0 critical, 1 high, 2 medium and 28 low. The high setuptools 70.3.0 entry points to pip's embedded BOM; same-image package inspection reports pip 26.3, installed setuptools 84.2.1 and no importable `pip._vendor.setuptools`. | Source/location mismatch is reconciled as metadata, not declared a clean API image. Original unsuppressed SARIF remains; no VEX/exception/suppression was applied. Medium/low findings remain visible for dependency review. E-13 closes its local discrepancy-reconciliation criterion with those residual counts explicitly disclosed. |
| TG-F25 medium — final exact-image smoke passed locally | Final smoke used API `sha256:633dcd9945f341f1aa5ea185a727caf454f3412c12abc6847f095107d6865ac9` and web `sha256:2ab56b0236d5d108b50ef5079aa58bf80aea79d73434627fff37580d361f8ecb`; clean migration, inference, PostgreSQL MLflow artifact round-trip, restart, checksummed backup, isolated restore and restored authenticated inference succeeded. | Local production-shape compatibility and recovery only; no AWS/S3/CloudWatch/HTTPS behavior inferred. See [final smoke JSON](evidence/release-smoke-2026-11-28-final-webhardening.json). |
| TG-F26 high — resolved for final web artifact | The prior Debian runtime image had a material critical/high vulnerability report. The release now uses a digest-pinned unprivileged Alpine slim NGINX base, upgrades zlib to 1.4-r0, exposes 8080 and runs UID 101; Compose enforces read-only root, a restricted tmpfs, no capabilities and no-new-privileges. Exact final Trivy report is 0 vulnerabilities, secrets and misconfigurations. | Final-image scan and production smoke passed. The superseded Debian scan and intermediate zlib report remain archived as history, not as final release status. |
| TG-F27 low — resolved locally | AWS Deployment Guide required a region-specific calculator estimate; the public AWS Pricing Calculator was configured for `ap-south-1` with the documented `t3.large`, 64 GiB gp3, IPv4 and Route 53 assumptions. | Calculator displays $75.40/month ($904.80 for 12 months). Reproducible unrounded calculation is $75.39/month due one-cent component-rounding difference. Usage-dependent and account-specific charges are explicitly excluded; the estimate was not provisioned or attached to an account. |

Current locally achievable requirement status and final checks are recorded in [the final acceptance report](LOCAL_ACCEPTANCE_2026-11-28.md#final-local-closure-and-offline-readiness--2026-11-28) and [traceability matrix](TESTING_AND_TRACEABILITY.md#final-locally-achievable-gate-disposition--2026-11-28). E-01–E-14 have local evidence. E-15 and hosted GitHub checks remain external; no AWS actions were authorized.
