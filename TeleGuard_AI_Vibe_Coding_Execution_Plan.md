# TeleGuard AI --- Vibe-Coding Project Execution Plan

> **Authoritative execution plan, 2026-11-28.** Sections 1–15 preserve the original plan. Section 16 supersedes the earlier task-by-task prompting and rollout sequence for this incremental release. It becomes executable only when the owner issues the separate master implementation instruction. The [master specification](TeleGuard_AI_Product_Scope_and_Feature_Blueprint.md) defines the scope.

**Project:** TeleGuard AI --- Intelligent Telecom Fraud Detection,
Investigation & Prevention Platform\
**Approach:** AI-assisted development ("vibe coding") with strict
specifications, small tasks, independent verification, and continuous
integration.\
**Deployment requirement:** Publicly accessible AWS deployment is
mandatory.\
**Status:** Planning baseline --- update decisions as the project
evolves.

------------------------------------------------------------------------

## 1. How we will build this project

This plan is designed for a team using coding agents such as Claude
Code, Codex, GitHub Copilot, or similar tools. The goal is not to ask an
agent to "build the whole project." The goal is to give it a bounded
task, enough repository context, explicit acceptance criteria, and a way
to prove that the change works.

### Core working principles

1.  **Spec before implementation.** Every substantial feature gets a
    short specification before code is written.
2.  **One task per agent session.** Keep prompts narrow: one feature,
    one bug, one integration, or one review.
3.  **Read before changing.** The agent must inspect the relevant code,
    tests, and project instructions before editing.
4.  **Plan, implement, verify.** Ask the agent to outline its approach,
    implement only the approved scope, run checks, and report evidence.
5.  **Small vertical slices.** Prefer a complete path through database →
    API → UI over creating many disconnected modules.
6.  **No fake completion.** A feature is complete only when its
    acceptance criteria pass and the evidence is recorded.
7.  **Human approval for consequential actions.** Fraud predictions may
    recommend action; blocking must be reversible and require an
    authorized policy/approval path in the demo.
8.  **Keep the system runnable.** The main branch should remain
    installable and testable.
9.  **Avoid architecture theatre.** Do not add Kafka, Airflow,
    Kubernetes, microservices, or an LLM merely to list technologies.
    Add them only when a working requirement justifies them.
10. **Deploy early.** Get a minimal version running on AWS before
    advanced features are added.

### Recommended agent workflow

For each task:

1.  Start a fresh agent session in the repository.
2.  Ask it to read `AGENTS.md`, `PROJECT_SPECIFICATION.md`,
    `ARCHITECTURE.md`, the relevant feature spec, and the task ticket.
3.  Ask for a brief implementation plan and files it expects to touch.
4.  Review the plan. Correct scope creep before coding.
5.  Let it implement the task.
6.  Require tests, lint/type checks, and a concise summary of changed
    files.
7.  Run the application or relevant integration test yourself.
8.  Ask a separate reviewer agent to inspect the diff for correctness,
    security, regressions, and missing tests.
9.  Merge only after checks pass.
10. Update the task status and relevant documentation.

**Do not give one agent the entire project specification and ask it to
implement everything in one run.** That encourages invented
functionality, inconsistent architecture, and unverified code.

------------------------------------------------------------------------

## 2. Product definition

### Problem

Telecom fraud can involve suspicious call behaviour, SIM replacement,
abnormal SMS/OTP activity, device changes, unusual location changes, and
coordinated groups of phone numbers or devices. A single record may look
harmless while its wider context is suspicious.

### Product goal

Build a demonstrable platform that ingests simulated telecom events,
detects suspicious activity using complementary detection methods,
explains its assessments, creates investigation cases, and provides a
monitored MLOps lifecycle. The system must be deployable on AWS.

### Explicit scope boundary

This is an **educational simulation**, not a connection to a real
telecom operator. It will not access real carrier infrastructure,
intercept calls/SMS, obtain real subscriber location, or block real
telephone numbers. All events and identities used in the demonstration
must be synthetic or properly licensed/public data.

### Primary user roles

-   **Administrator:** manages users, roles, system configuration, and
    audit records.
-   **Fraud analyst:** investigates alerts, reviews evidence, labels
    cases, and recommends actions.
-   **Operator:** performs approved reversible actions and records
    outcomes.
-   **Viewer:** read-only access to dashboards and reports.

Enforce permissions on the backend. Hiding frontend controls is not
authorization.

### Core user journeys

1.  An administrator signs in and views system health.
2.  A simulator emits CDR, SIM, device, SMS/OTP, and location events.
3.  The ingestion pipeline validates and stores events.
4.  The fraud engine computes supervised, anomaly, graph, and rule
    signals.
5.  The platform returns a calibrated risk assessment with reasons and
    model version.
6.  A high-risk assessment creates an incident.
7.  An analyst investigates the timeline, related entities,
    explanations, and evidence.
8.  An authorized user approves, rejects, or reverses a simulated
    response.
9.  Analyst feedback is stored for later evaluation and retraining.
10. The MLOps pipeline tracks candidate models and only promotes a
    candidate that passes configured quality gates.

------------------------------------------------------------------------

## 3. Scope and priorities

### P0 --- Must work for submission

-   Synthetic CDR/event generator with documented fraud scenarios.
-   Data validation and reproducible feature engineering.
-   Time-aware train/validation/test split.
-   At least three supervised baseline/model candidates.
-   Fraud metrics suitable for class imbalance.
-   FastAPI inference API.
-   PostgreSQL persistence for users, events, predictions, incidents,
    and audit logs.
-   Authentication and backend-enforced RBAC.
-   Explainable prediction output.
-   Analyst incident review workflow.
-   MLflow experiment tracking and model artifact/version management.
-   Dockerized local environment.
-   Automated tests and GitHub Actions CI.
-   AWS-hosted application with a public HTTPS URL and persistent data.
-   Setup, architecture, model, and deployment documentation.

### P1 --- Main differentiators

-   Isolation Forest anomaly score.
-   Entity relationship graph and graph-derived features.
-   Hybrid risk engine combining model, anomaly, graph, and rule
    signals.
-   Live event simulation and dashboard updates.
-   Data quality checks and drift monitoring.
-   Champion/challenger evaluation and controlled model promotion.
-   Model rollback procedure.
-   SHAP explanations for supported model types.
-   Fraud-ring investigation view.

### P2 --- Add only after P0/P1 are stable

-   LLM-assisted investigation report grounded in stored evidence.
-   Conversational fraud/vishing module using a suitable licensed
    dataset.
-   Kafka-based event streaming if the simulator and API path are
    already stable.
-   Airflow-based scheduled retraining if a real repeatable retraining
    need is demonstrated.
-   Advanced graph learning/GNN experiments.
-   More elaborate cloud orchestration such as ECS Fargate.

**Rule:** A P2 feature must not delay a working P0 deployment.

------------------------------------------------------------------------

## 4. Recommended architecture

Start as a **modular monolith plus separate worker processes**, not a
fleet of microservices. This is easier to vibe-code, test, debug, and
deploy. Split services only when a clear scaling or ownership reason
appears.

### Runtime components

-   **Frontend:** React + TypeScript.
-   **Backend:** FastAPI, with modular routers and services.
-   **Database:** PostgreSQL for application data.
-   **ML layer:** Python, Pandas, NumPy, scikit-learn,
    XGBoost/LightGBM/CatBoost where justified.
-   **Graph layer:** NetworkX initially.
-   **Explainability:** SHAP where compatible with the selected model.
-   **Experiment tracking:** MLflow.
-   **Data validation:** Pandera or equivalent.
-   **Drift monitoring:** Evidently or a small documented custom monitor
    initially.
-   **Background work:** start with a simple worker/queue only where
    needed; Redis/Celery can be added later.
-   **Streaming:** start with HTTP event ingestion or Redis Streams; add
    Kafka only if the project demonstrates a need.
-   **Local environment:** Docker Compose.
-   **Cloud:** AWS EC2 for the first public deployment; S3 for
    model/data artifacts; ECR for images; CloudWatch for logs; IAM for
    permissions. Consider ECS only after the EC2 deployment is reliable.
-   **CI/CD:** GitHub Actions.

### Logical flow

``` text
Synthetic Event Generator / CSV Upload
                 |
                 v
       FastAPI Ingestion API
                 |
       Validation + Normalization
                 |
                 v
          PostgreSQL Events
                 |
                 v
       Feature Engineering Layer
          /       |       \
         v        v        v
   Supervised  Anomaly   Graph/Rules
     Models    Model     Intelligence
          \       |       /
           \      v      /
             Risk Engine
                 |
       Prediction + Explanation
                 |
        Incident / Review Queue
                 |
      Analyst / Authorized Operator
                 |
        Feedback + Audit History

Offline MLOps:
Dataset -> Validation -> DVC/version -> Training -> MLflow
       -> Time-aware Evaluation -> Promotion Gate -> Model Registry
       -> Deployment -> Monitoring -> Candidate Retraining
```

### Important architectural rules

-   Training and inference must share the same feature definitions.
-   Store the model version and feature/schema version with every
    prediction.
-   Do not train on future information relative to the prediction
    timestamp.
-   Do not use random train/test splitting when it causes temporal
    leakage.
-   Keep raw events, derived features, predictions, incidents, and
    analyst labels conceptually separate.
-   Make response actions idempotent and auditable.
-   Never claim "real-time" unless latency and event-processing
    behaviour are measured.
-   Keep secrets out of Git and container images.

------------------------------------------------------------------------

## 5. Data plan

### Initial data approach

Use a scenario-based synthetic generator as the primary source because
real telecom CDRs and subscriber data are sensitive and difficult to
obtain legitimately. Public datasets may be used as supplementary
research inputs only after checking their license, schema, label
meaning, and suitability.

### Initial event entities

-   `subscriber_id` --- synthetic identifier.
-   `phone_number_token` --- synthetic token, not a real phone number.
-   `sim_id` --- synthetic SIM identifier.
-   `device_id` --- synthetic device identifier.
-   `ip_token` --- synthetic network identifier.
-   `event_id` --- unique event identifier.
-   `event_type` --- call, SMS, OTP, SIM change, device change,
    location/authentication event.
-   `event_timestamp` --- event time.
-   `latitude`, `longitude` --- generated coordinates or synthetic
    cell-area centroids.
-   `duration_seconds` --- where relevant.
-   `label_fraud` and `fraud_type` --- labels available only in
    generated/training data, never leaked into inference features.

### Initial fraud scenarios

1.  SIM swap followed by OTP/authentication activity.
2.  Rapid-fire calling or SMS bursts.
3.  Unusual international-call behaviour.
4.  Implausible travel between time-stamped locations.
5.  Multiple subscribers sharing a device or network identifier.
6.  Coordinated fraud ring targeting multiple subscribers.
7.  Account takeover involving SIM, device, and IP changes.
8.  Benign lookalikes to test false positives.

### Data quality and leakage safeguards

-   Generate both fraudulent and legitimate examples for each relevant
    context.
-   Avoid a single obvious field that reveals the label.
-   Record scenario provenance and random seed.
-   Use time-based splits and, where possible, entity/group-aware
    splits.
-   Keep a final untouched test set.
-   Document which columns are available at prediction time.
-   Remove label, scenario ID, and future-derived fields from model
    inputs.
-   Report class balance and per-fraud-type performance.
-   Version generator code and dataset configuration.

### Model evaluation

Prioritize: - PR-AUC. - Fraud-class precision and recall. - F1 at a
stated threshold. - False-positive rate. - Confusion matrix. -
Calibration. - Inference latency and throughput.

Accuracy and ROC-AUC may be included, but must not be the only headline
metrics for an imbalanced dataset. A threshold must be selected against
explicit operational costs, not arbitrarily fixed at 0.85.

------------------------------------------------------------------------

## 6. Repository documentation to create before heavy coding

Create these files early:

  -----------------------------------------------------------------------
  File                                Purpose
  ----------------------------------- -----------------------------------
  `AGENTS.md`                         Permanent instructions for coding
                                      agents

  `PROJECT_SPECIFICATION.md`          Product scope, requirements, roles,
                                      acceptance criteria

  `ARCHITECTURE.md`                   Components, boundaries, data flow,
                                      decisions

  `ROADMAP.md`                        Phases, milestones, dependencies,
                                      status

  `TASKS.md`                          Small actionable task backlog

  `DECISIONS.md`                      Architecture Decision Records
                                      (ADRs)

  `docs/DATA_DICTIONARY.md`           Event schemas, field meanings,
                                      label rules

  `docs/ML_EVALUATION.md`             Splits, metrics, leakage controls,
                                      promotion gates

  `docs/LOCAL_SETUP.md`               Reproducible local setup

  `docs/AWS_DEPLOYMENT.md`            AWS deployment and teardown

  `docs/SECURITY.md`                  Threat model, secrets, RBAC, audit
                                      policy

  `docs/features/*.md`                One specification per substantial
                                      feature
  -----------------------------------------------------------------------

Do not duplicate the same architecture in every file. `AGENTS.md` gives
instructions; the specification says what to build; the architecture
says how components fit; feature specs say how an individual feature
behaves; tasks say what to do next.

------------------------------------------------------------------------

## 7. Feature specification template

Use this template for each substantial feature:

``` markdown
# Feature: <name>

## Goal
What user problem does this solve?

## Scope
What is included?

## Out of scope
What must not be implemented in this task?

## User flow
1. ...
2. ...

## Inputs and outputs
Document request/event schemas and response shape.

## Data and persistence
What is stored? Which tables/entities are involved?

## API/UI contract
Endpoints, permissions, states, and visible behaviour.

## Failure cases
Invalid input, missing data, duplicate events, unavailable model, etc.

## Security and privacy
Authorization, sensitive fields, audit requirements.

## Acceptance criteria
- [ ] Observable condition 1
- [ ] Observable condition 2
- [ ] Tests cover expected failures

## Verification commands
Exact commands to run.

## Dependencies
Other features or decisions required first.
```

------------------------------------------------------------------------

## 8. Vibe-coding task workflow

### Task sizing

A good task should usually: - Take one agent session or a small number
of sessions. - Have one clear outcome. - Touch a limited set of
modules. - Have testable acceptance criteria. - Avoid simultaneous
changes to unrelated layers.

Examples of good tasks: - "Add a validated `POST /events` endpoint and
tests for duplicate event IDs." - "Implement the Haversine distance
feature with unit tests." - "Add analyst-only permission to resolve an
incident." - "Add a time-based split utility and a test proving no
future rows enter training."

Examples of bad tasks: - "Build the entire ML system." - "Make the
backend production-ready." - "Add all MLOps features." - "Improve the
dashboard and fix anything broken."

### Standard implementation prompt

Use this prompt for each task:

``` text
You are implementing one bounded task in TeleGuard AI.

Before coding:
1. Read AGENTS.md.
2. Read PROJECT_SPECIFICATION.md and ARCHITECTURE.md.
3. Read the relevant feature specification and task in TASKS.md.
4. Inspect the existing implementation and tests.
5. Summarize the current state, proposed approach, files to change,
   risks, and verification commands.
6. Do not edit files until the plan is clear.

Implementation rules:
- Implement only the requested task.
- Follow existing architecture and conventions.
- Do not invent APIs, schemas, or dependencies.
- Do not silently change unrelated behaviour.
- Add or update tests for success and failure cases.
- Validate inputs and enforce authorization on the backend.
- Never commit secrets or real personal data.
- Keep documentation in sync where behaviour or contracts change.

Before finishing:
1. Run relevant tests, lint, formatting, and type checks.
2. Report exact commands and pass/fail results.
3. List changed files and explain why each changed.
4. List known limitations and follow-up tasks.
5. Do not claim a check passed unless it was actually run.
```

### Independent reviewer prompt

``` text
Act as an independent senior reviewer. Do not implement changes yet.

Read AGENTS.md, the relevant specification, and the complete diff.
Review for:
- Functional correctness and edge cases.
- Data leakage and incorrect ML evaluation.
- Authentication, authorization, and secret handling.
- Database integrity and migration safety.
- API contract compatibility.
- Error handling and observability.
- Missing or weak tests.
- Unnecessary complexity and scope creep.

Return findings ordered by severity, with file and line references.
If no blocker exists, say so and list residual risks.
Do not praise the implementation generically.
```

### Debugging prompt

``` text
Investigate this failure without immediately rewriting the implementation.

1. Reproduce the issue using the exact command or test.
2. Trace the failure to its root cause.
3. Inspect relevant configuration, logs, and related code.
4. Explain the cause and smallest safe fix.
5. Add a regression test.
6. Apply the fix and rerun the regression test plus relevant suite.
7. Report evidence. Do not hide unrelated failures.
```

### Context management

-   Use a new session for a new feature or unrelated bug.
-   Continue an existing session only when it contains useful
    implementation context.
-   At the end of a long session, ask the agent to update the task
    status and write a handoff summary.
-   Keep durable knowledge in repository files, not only in chat
    history.
-   Do not paste the entire repository into every prompt; point the
    agent to the relevant files.
-   Ask agents to inspect the code rather than trusting old summaries.

------------------------------------------------------------------------

## 9. Git and integration workflow

Recommended branches:

-   `main` --- stable, deployable code.
-   `develop` --- integrated work, if the team needs it.
-   `feature/<short-name>` --- one feature or task.
-   `fix/<short-name>` --- one bug fix.

For a small team, feature branches can merge into `main` through pull
requests if CI is reliable. Avoid unnecessary branch complexity.

### Pull request checklist

-   [ ] Scope matches one task/specification.
-   [ ] No secrets, credentials, or real personal data.
-   [ ] Tests added or updated.
-   [ ] Existing tests pass.
-   [ ] Lint/type checks pass.
-   [ ] Database migration reviewed.
-   [ ] API/schema changes documented.
-   [ ] Authorization tested where applicable.
-   [ ] Reviewer findings addressed.
-   [ ] App still starts using documented commands.

Never let multiple agents edit the same files concurrently without
coordination. Assign ownership by module and integrate frequently.

------------------------------------------------------------------------

## 10. Milestones and suggested schedule

This is a dependency-based plan, not a promise that every advanced
feature will fit a fixed number of days. Adjust it to the actual
submission date and team capacity.

### Milestone 0 --- Repository foundation

-   Create repository and documentation files.
-   Agree on stack and module ownership.
-   Create minimal frontend/backend skeleton.
-   Add Docker Compose and health checks.
-   Add CI for formatting, linting, and tests.

**Exit gate:** A clean clone can start the skeleton locally.

### Milestone 1 --- Data and baseline ML

-   Implement scenario-based event generator.
-   Add data dictionary and validation.
-   Build leakage-safe time-based splits.
-   Train baseline models.
-   Save metrics and artifacts.
-   Track experiments in MLflow.

**Exit gate:** A reproducible training run produces documented metrics
and a versioned artifact.

### Milestone 2 --- Inference and persistence

-   Create database schema and migrations.
-   Implement event ingestion.
-   Implement feature pipeline.
-   Implement model loading and prediction API.
-   Persist predictions and model versions.
-   Add API and database integration tests.

**Exit gate:** A generated event can travel through the API and produce
a stored, explainable prediction.

### Milestone 3 --- Intelligence and investigation

-   Add anomaly scoring.
-   Add graph construction and graph features.
-   Add rules and hybrid risk scoring.
-   Add incident lifecycle and analyst review.
-   Add reversible simulated response actions.
-   Add audit records.

**Exit gate:** A seeded scenario creates an incident that an authorized
analyst can investigate and resolve.

### Milestone 4 --- MLOps and monitoring

-   Add model registry workflow.
-   Add candidate evaluation gates.
-   Add champion/challenger comparison.
-   Add data/model monitoring.
-   Add controlled retraining and rollback procedure.

**Exit gate:** A candidate model can be rejected or promoted based on
recorded metrics and policy.

### Milestone 5 --- Frontend and demo quality

-   Complete dashboard and event explorer.
-   Complete incident investigation view.
-   Complete graph visualization.
-   Complete model/MLOps views.
-   Add a one-click seeded demo scenario.
-   Test end-to-end user journeys.

**Exit gate:** A new user can sign in, run the demo, inspect evidence,
and complete an authorized review.

### Milestone 6 --- AWS deployment

-   Build and scan container images.
-   Push images to ECR.
-   Provision EC2 and required AWS resources.
-   Configure environment variables/secrets.
-   Configure HTTPS and domain/subdomain if available.
-   Configure persistent database and S3 artifacts.
-   Configure CloudWatch logs and alarms.
-   Configure GitHub Actions deployment.
-   Test restart, backup/restore, and rollback.

**Exit gate:** Public URL works, data persists across application
restarts, and deployment can be repeated from documentation.

### Milestone 7 --- Final verification

-   Run full automated test suite.
-   Run seeded demo from a clean environment.
-   Verify all user roles and permissions.
-   Verify no secret is exposed in repository or browser.
-   Capture architecture, metrics, and AWS evidence.
-   Finish README and presentation.

**Exit gate:** A reviewer can reproduce the core demo and understand the
system's limitations.

------------------------------------------------------------------------

## 11. AWS deployment strategy

### First deployment: EC2

Use EC2 with Docker Compose for the first working cloud version. This is
easier to operate and less complex than beginning with a multi-service
managed deployment.

Suggested AWS responsibilities: - EC2: application containers. - ECR:
container image storage. - S3: model artifacts, versioned datasets, and
reports. - IAM: least-privilege access. - CloudWatch: application/system
logs and alarms. - PostgreSQL: persistent application database, either
carefully configured on EC2 for a low-cost demo or managed RDS if budget
permits. - GitHub Actions: test, build, push, and deploy.

### Deployment safety

-   Set an AWS Budget and billing alerts before provisioning.
-   Use least-privilege IAM roles.
-   Never commit AWS keys or `.env` files.
-   Restrict database access to the application.
-   Use HTTPS for public access.
-   Do not expose MLflow, database, Redis, or internal monitoring ports
    publicly.
-   Configure backups and test restoration.
-   Document how to stop and delete resources to prevent ongoing
    charges.
-   Keep training jobs off the always-on demo instance where possible.

### Later upgrade: ECS Fargate

Only consider ECS Fargate after the EC2 version works. It is a useful
production-style extension, not a prerequisite for a strong project
submission.

------------------------------------------------------------------------

## 12. Definition of Done

A task is done only when: - The requested behaviour exists. - Acceptance
criteria are met. - Relevant tests pass. - Failure paths are
considered. - Authorization and data handling are correct. -
Documentation/contracts are updated. - The diff is reviewed. - The
application remains runnable.

The project is submission-ready only when: - The public AWS deployment
works. - Core flows work end-to-end. - Model results are reproducible
and honestly reported. - Fraud explanations are traceable to evidence. -
Actions are permission-checked and auditable. - CI is green. - Setup and
deployment instructions work from a clean clone. - Known limitations are
documented.

------------------------------------------------------------------------

## 13. First 10 tasks --- do these in order

Do not start by asking an agent to implement the complete project. Start
with these bounded tasks:

1.  **T001 --- Repository audit and decision log:** inspect the current
    repository (if any), agree on stack, record assumptions and open
    questions.
2.  **T002 --- Project documentation:** create `AGENTS.md`,
    `PROJECT_SPECIFICATION.md`, `ARCHITECTURE.md`, `ROADMAP.md`,
    `TASKS.md`, and `DECISIONS.md`.
3.  **T003 --- Application skeleton:** create FastAPI and React
    skeletons, health endpoint, frontend shell, and Docker Compose.
4.  **T004 --- CI foundation:** add formatting, linting, type checks
    where applicable, and backend/frontend test jobs.
5.  **T005 --- Event schema:** define event types, validation, synthetic
    identifiers, and data dictionary.
6.  **T006 --- Scenario generator:** generate balanced benign/fraud
    scenarios with reproducible seeds and provenance.
7.  **T007 --- Leakage-safe dataset builder:** implement time-aware
    splits and tests preventing target/future leakage.
8.  **T008 --- Baseline training:** train and compare baseline models
    with PR-AUC, precision, recall, F1, calibration, and latency.
9.  **T009 --- MLflow tracking:** log parameters, metrics, artifacts,
    and dataset/config versions.
10. **T010 --- First inference vertical slice:** ingest one synthetic
    event, derive features, score it, explain it, and persist the
    result.

After T010, deploy the minimal application to AWS. Do not wait until the
final week.

------------------------------------------------------------------------

## 14. Decisions to confirm before implementation

Record these in `DECISIONS.md` rather than allowing agents to guess:

-   Team size, member ownership, and available development weeks.
-   AWS budget and whether an existing AWS learner/student credit is
    available.
-   EC2-only first deployment versus eventual ECS migration.
-   Whether conversational fraud is in scope for the first submission.
-   Whether Kafka is justified or HTTP/Redis Streams is sufficient.
-   Whether PostgreSQL is hosted on EC2 or RDS.
-   Whether the frontend is React + TypeScript.
-   Which public datasets are legally usable and actually compatible
    with the generated event schema.

Until confirmed, use the conservative defaults in this plan: React +
TypeScript, FastAPI, PostgreSQL, modular monolith, synthetic primary
data, NetworkX, MLflow, Docker Compose, and EC2-first AWS deployment.

------------------------------------------------------------------------

## 15. Final guidance

The strongest vibe-coding workflow is not "write a huge prompt and
accept whatever the agent produces." It is:

**Specify → delegate a small task → inspect the plan → implement → test
→ independently review → integrate → update docs.**

Use agents to accelerate implementation, not to replace architectural
decisions, testing, or understanding. Every major feature should be
demonstrable, measurable, and explainable.

The first milestone is not an advanced fraud model. It is a clean
repository with clear instructions, a runnable skeleton, automated
checks, and a project specification that every coding agent can follow.

## 16. Execution plan for the incremental release (2026-11-28)

When the owner authorizes implementation, execute the mandatory local phases in order with one continuous instruction. This plan does not authorize AWS provisioning or paid actions. Preserve the modular monolith, existing integrations, historic evidence and repositories/data as specified in [AGENTS.md](AGENTS.md). Use the [audit](docs/REPOSITORY_AUDIT.md) to locate defects and the [matrix](docs/TESTING_AND_TRACEABILITY.md) to close requirements.

| Task | Depends on | Work and principal code surfaces | Required exit evidence |
|---|---|---|---|
| TG-T00 Baseline and recovery | Implementation authorization | Inventory Git and active environments. Record recent evidence, Docker/DB state, migration head, model and artifacts. Rebuild exact source in an isolated Compose project. Run original backend and Playwright checks before edits, fix blocking startup/test harness issues and test upgrade against a preserved copy. | E-01 baseline and tool/version manifest. E-12 initial migration and recoverability evidence. |
| TG-T01 Scoring and release correctness | T00 | In backend scoring, batch and ML lifecycle paths, share event ordering and decision policy, normalize IDs, hash full subscriber ID with stable experiment key, persist routing and policy. Add a transactional release state and current-champion comparison proofs. Remove implicit seed promotion beyond explicit bootstrap and preserve prior observations. | E-04 parity and late/tied-event fixtures, E-06 allocation/stale evidence/race and rollback tests. |
| TG-T02 Data and simulator | T01 contract prerequisites | Extend schemas, generation, ingest adapters, dataset manifests, job worker, Alembic and Data Observatory. Preserve legacy import, dataset and controls. Add simulator profiles, bounded buffer, cursor and label release state. Generate 300k/50k/50k and report positive counts, overlap and lineage. | E-02 checksum/count/disjointness evidence and E-03 live start/pause/resume/stop/restart/backpressure. E-04 invalid/duplicate/quarantine behavior. |
| TG-T03 ML evaluation and artifacts | T01, T02 | Train three tabular candidates using shared features, calibrated scores when justified and validation-only policy selection. Add immutable split proofs, independent scenario and prevalence reports, explainability replay inputs and artifact integrity in MLflow and model metadata. | E-05 reports, fit/holdout integrity, lineage, baseline comparisons, per-slice support, latency and offline replay evidence. |
| TG-T04 Continuous monitoring | T02, T03 | Instrument real serving paths and ModelObservation. Schedule idempotent window aggregation and delayed-label evaluation, version frozen bins, prevent demo-window contamination, persist quality and degradation state and emit actionable monitoring health. | E-07 clean/shift/quality/degradation replay, repeated-breach and dedup tests, label coverage evidence. |
| TG-T05 Automated lifecycle | T03, T04 | Extend dataset-job/worker, MLflow and lifecycle API. Persist durable jobs with stage, lease, retry/cooldown, dedup key, run reconciliation and cancel. Integrate eligible triggers, candidate gates, explicit approval, shadow, measured canary, suspension and recovery. | E-08 no-owner-command automatic retraining, crash/retry and negative trigger tests. E-06 failed candidate, approval, ramp and rollback drill. |
| TG-T06 Investigations and feedback | T02, T03 | Extend incidents, audit, graph, labels and portal. Add bounded case linkage, review sampling and versioned correction/adjudication. Feed accepted feedback through dataset validation and compare incident policies on identical replay. | E-09 label provenance, RBAC and leakage tests. E-10 linkage, workload and replay evidence. Integrate approved feedback with T05 trigger. |
| TG-T07 Complete UI and lab | T02–T06 | Extend App.tsx and OperationalViews.tsx using existing dependencies. Connect RBAC-aware controls, telemetry, lab runs, charts and incident workflows to persisted backend state. Add missing frontend tests and run browser demo in bounded accelerated mode. | E-11 role, accessibility, empty/failure and end-to-end UI evidence. E-14 real complete local demo. |
| TG-T08 Reliability and deployment readiness | T01 onward, full gate after T07 | Harden runtime, extend health checks/telemetry, exact-image integration tests, secure production configuration, reproducible infrastructure definitions and release manifest/rollback. Exercise upgrade, encrypted storage backup flow using local equivalents, isolated restore and cold artifact retrieval. Document sizing, cost and teardown. | E-12 clean and upgrade Compose, backup/restore, liveness/readiness and recovery. E-13 offline AWS readiness evidence and external prerequisite list. |
| TG-T09 Final acceptance and authorized AWS verification | T00–T08 | Close all locally achievable matrix rows, rerun from clean state and submit evidence. Only with explicit deployment approval run hosted release, inspect cloud resources, demo and perform AWS restore/rollback drills. | E-14 repeatable local demo; E-15 live AWS evidence only after authorization. Record completion states separately. |

T06 can start once its prerequisites pass. Avoid making T05 contingent on a UI merge by using persisted, validated labeled fixtures from the same normal pipeline. Final integration must exercise reviewer-originated labels. Fix startup, safety and recovery bugs as soon as discovered because they affect later evidence. Profile before adopting infrastructure or tuning numerical gates.

### Autonomous workflow and resumption

1. Start with the master specification, this section, the matrix, the audit and TASKS.md. Read local instructions and matching feature specs, inspect Git state and pick the earliest unlocked task. Preserve pre-existing changes and provider data.
2. Record the task ID, dependencies, planned edits and risks in TASKS.md. Work in small, reviewable vertical slices on the existing application. Use real input → persistence → inference/job → UI paths. Choose reversible implementation details independently within scope and record consequential decisions in DECISIONS.md.
3. Add regression coverage at the failing boundary. Execute commands in isolated test state. Record date, source revision, dataset/run IDs, command exit status and measurable result. Leave failures open, diagnose them, retry within scope, and finish independent work during external blockers.
4. Add discovered required work as TG-Fnn with the mapped TG requirement, parent task, reproduction, severity, dependencies and pass criterion. Reorder phases when a fix is a dependency. An optional item stays optional under its original conditions.
5. After interruption, context compaction, or usage limit, read TASKS.md, the Git diff, and the last evidence entry. Resume the earliest incomplete prerequisite. Confirm any interrupted job’s persisted state before retrying and avoid replaying completed or destructive operations.
6. Mark a task complete only after its acceptance rows pass on the final applicable revision. If blocked, record the exact command, reason, remaining scope, independent work performed and minimal owner action. Ask for owner help only for external access, permissions, budget, destructive actions or deployment authorization. The owner writes no application code.
7. Produce the four completion states and list outstanding mandatory requirements. Do not imply cloud success from a configuration check or local Docker build.

### External actions at release time

The owner confirms academic acceptance of synthetic data if their rubric is ambiguous. This confirmation does not block the local synthetic-first plan. For live AWS, the owner supplies an authorized account or role, approves region and budget, grants GitHub environment/repository and domain/DNS access as needed, and explicitly authorizes provisioning and deployment. Provide exact actions in the [AWS guide](docs/AWS_DEPLOYMENT_GUIDE.md). Pause affected external work only and complete all offline work first.

### Execution closeout record — 2026-11-28

Local implementation has progressed through the integrated lifecycle and recovery checks recorded in [TASKS.md](TASKS.md#final-integrated-local-checkpoint--2026-11-28). Continue the exact-image security scan/reconciliation as the remaining local E-13 gate. Keep AWS provisioning and hosted acceptance separate: this plan and the current user authorization do not permit cloud deployment.

### Final local execution closeout — 2026-11-28

The remaining exact-image Trivy scan, source reconciliation, offline regional cost estimate and exact-image recovery smoke have been completed and recorded in [the final checkpoint](TASKS.md#final-locally-achievable-completion-checkpoint--2026-11-28) and [acceptance report](docs/LOCAL_ACCEPTANCE_2026-11-28.md#final-local-closure-and-offline-readiness--2026-11-28). E-01–E-14 are accepted locally; TG-T00–TG-T08 and local TG-T09 work are complete. API Scout's reconciled metadata finding remains unsuppressed and its other 2 medium/28 low counts remain disclosed. E-15 live AWS and hosted GitHub checks are external and unauthorized. No cloud deployment is claimed.
