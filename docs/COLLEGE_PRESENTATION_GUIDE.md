# TeleGuard AI college presentation guide

## Project overview and problem

TeleGuard AI is an educational telecom fraud investigation simulation. It demonstrates how synthetic call, SIM, device, network, location, and account-activity events can be scored and investigated. Scores are risk signals for human review, not proof of fraud. The project does not connect to carriers, read private communications/GPS, or block real subscribers.

## Architecture and stack

- React, TypeScript, Vite, Tailwind-style application CSS, Recharts, and Lucide icons for the workspace.
- FastAPI modular monolith for authentication, RBAC, event ingestion, inference, incidents, audit, and MLOps APIs.
- PostgreSQL with SQLAlchemy/Alembic for durable application records; SQLite is used by local automated tests.
- scikit-learn for supervised models and Isolation Forest; NetworkX for synthetic entity relationships.
- MLflow for experiment runs, metrics, artifacts, and model registration. PostgreSQL active-model records control which persisted artifact serves predictions.
- Docker Compose for PostgreSQL, API, web, and private MLflow. GitHub Actions runs tests/lint/build/container checks.

## Synthetic data and fraud methodology

The event generator uses fixed seeds and synthetic identifiers. It labels generated scenarios such as SIM swap, call burst, SIM farm, coordinated ring, and benign activity. The training feature set covers duration, event type, prior device/network reuse, time-of-day, subscriber history, call frequency/contact diversity, and prior SIM changes. Scenario names and fraud labels are excluded from model input features. Training uses chronological ordering and fits model preprocessing on its training partition; the held-out tail is used for evaluation.

The serving assessment keeps supervised probability, Isolation Forest anomaly score, graph reuse signal, rule result, and final weighted risk score distinct. NetworkX links synthetic subscribers through shared SIM/device/network tokens. Shared infrastructure alone is weak context and does not prove fraud. Incidents include event evidence, notes, assignment/status changes, and audit history. Consequential actions are reversible simulation records only.

## Explainability and investigation

Current prediction evidence reports supervised probability, anomaly score, shared-entity signal, and fired metadata rules. Incident details show associated events, graph links, and an on-demand SHAP explanation tied to the model version that produced that prediction. Random Forest uses TreeExplainer in fraud-probability space; Logistic Regression uses LinearExplainer in transformed feature space and reports log-odds. Unsupported model/schema or failed additivity checks return an unavailable explanation rather than fabricated values.

## MLOps lifecycle

Baseline and drift datasets are versioned snapshots in PostgreSQL. The administrator can generate a seeded feature-shift batch that lengthens synthetic call durations and concentrates network/location tokens while retaining generated labels. PSI compares feature distributions; PSI ≥ 0.20 is the demonstration threshold. This measures input data drift only. It does not establish concept drift (a changed input/label relationship) or model degradation (worse predictive quality on later labeled data).

Retraining calls the existing scikit-learn training pipeline and sends a real run to MLflow. Artifacts and metrics are stored with a model run. The challenger and current champion are evaluated on one chronological holdout from the challenger dataset. The demonstration uses a recall-prioritized 0.30 comparison threshold and explicit PR-AUC, recall, and false-positive gates. A human administrator approves or rejects; drift never automatically changes the serving model. Rollback can select a previously approved model and inference uses the selected artifact.

## RBAC and audit

Administrators manage users and make MLOps promotion decisions. ML Engineers may run training/evaluation but cannot approve or roll back. Fraud Analysts and Investigators update cases and notes; simulated response permissions are backend-enforced. Auditors can inspect audit history and cannot change investigations or execute response actions. Login sessions can be revoked server-side; user deactivation revokes active sessions.

## Live demonstration order

1. Start Compose and sign in as the configured administrator.
2. Show the overview and a synthetic incident with risk evidence.
3. Open **MLOps lifecycle** and identify the current champion and baseline dataset.
4. Run **Run Complete MLOps Demo**. Explain the deliberate feature shifts and retained labels.
5. Inspect PSI scores, threshold, changed distributions, and the distinction between data drift and model performance.
6. Inspect the real MLflow run ID and candidate metrics/confusion matrix.
7. Review the common-set comparison and decision gates. Approve only if all gates pass; otherwise reject and show the champion remains active.
8. If approved, roll back to the earlier approved model and show the active version changes. Review audit records.

Follow [MLOPS_DEMO_GUIDE.md](MLOPS_DEMO_GUIDE.md) for exact commands and recovery steps.

## Limitations to state

- All data and metrics are synthetic; results do not estimate real-world performance.
- The generator is small and scenario-correlated; per-class evaluation can be unstable.
- Deep per-scenario/location/travel analysis, transcript/vishing NLP, calibrated real-world thresholds, delayed-label performance monitoring, asynchronous training jobs, shadow/canary serving, and a hosted GitHub Actions result are not complete/verified.
- The comparison policy is a transparent college-demo gate, not a production telecom release policy.
- AWS Compose/ECR/SSM deployment configuration is prepared, but no live EC2, public HTTPS, AWS secret delivery, backup/restore, CloudWatch logs, remote S3 artifact recovery, or hosted Actions run has been verified. No public URL exists.

## Likely viva questions

**Why use time-aware evaluation?** Events are temporal; training on future events relative to evaluation would leak information. The chronological split better approximates scoring later events.

**What is data drift?** A change in the input feature distribution. PSI flags such changes against a reference. It does not tell us that the relationship to fraud labels changed.

**What is concept drift?** A change in the relationship between input features and the target. It needs later labels or another justified target-relationship analysis; this demo does not claim to detect it.

**Why not promote the newest model automatically?** A new run is only a challenger. Common-set gates and an administrator decision keep an unvalidated model from changing production-style inference.

**How does rollback work?** The backend verifies the target was previously approved, records a new active-model selection and loads that artifact for subsequent inference.

**Why include graph analytics?** Shared synthetic entities can provide investigation leads about coordination. They are supporting evidence only because legitimate subscribers can share network infrastructure.

**Does an auditor have write access?** No. The backend checks roles for incident changes, simulated actions, training, promotion, and rollback; hiding controls in the UI is not the security boundary.

**Can this block subscribers?** No. Response actions are synthetic, reversible audit records. No carrier integration or real subscriber restriction exists.
