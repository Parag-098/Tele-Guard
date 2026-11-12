# DECISIONS.md — Architecture Decision Log

Status values: **Accepted baseline**, **To validate**, **Deferred**.

| ID | Decision | Status | Rationale / revisit condition |
|---|---|---|---|
| D001 | Build a modular monolith first | Accepted baseline | Lower complexity for a student project; split only with evidence. |
| D002 | FastAPI backend | Accepted baseline | Python-native ML integration and typed API contracts. |
| D003 | React + TypeScript frontend | Accepted baseline | Dashboard and interactive investigation workflows. |
| D004 | PostgreSQL as deployed system of record | Accepted baseline | Relational persistence, migrations and auditability. |
| D005 | Synthetic scenario-driven dataset first | Accepted baseline | Reproducible labels and safe demos; external data can supplement after license review. |
| D006 | Time-aware evaluation and leakage checks | Accepted baseline | Telecom events are temporal; random split alone can overstate performance. |
| D007 | MLflow for experiment tracking/registry | To validate | Keep only if it can be run and demonstrated within AWS budget. |
| D008 | NetworkX for initial graph intelligence | Accepted baseline | Explainable graph features without operational graph DB overhead. |
| D009 | EC2 + Docker Compose for first AWS deployment | Accepted baseline | Cost-conscious and demonstrable; consider managed services if budget permits. |
| D010 | RDS versus PostgreSQL on EC2 | To validate | Compare monthly cost, backups, operational risk and available credits. |
| D011 | Kafka/Kubernetes/Airflow/GNN | Deferred | Add only if implemented use case and measured need justify complexity. |
| D012 | No real carrier integration or subscriber blocking | Accepted baseline | Strict educational simulation boundary. |

## Audit decisions (2026-11-12)

| ID | Decision | Status | Rationale / revisit condition |
|---|---|---|---|
| D013 | Treat the checked-out workspace as a documentation-only starter pack; do not infer implementation from plans | Accepted | Full recursive inventory found no application source, schema, tests, containers, workflow, or deployment code. Re-audit after the intended code repository is restored/initialized. |
| D014 | Preserve the stack baseline: React + TypeScript, FastAPI/Python, PostgreSQL, scikit-learn, NetworkX, Docker Compose, GitHub Actions | Accepted | Fits the educational app and Python ML pipeline; no evidence supports replacing it. Use Vite and migration-backed SQLAlchemy/Alembic as concrete implementation choices unless repository restoration reveals established alternatives. |
| D015 | Deliver as a modular monolith with offline training commands/worker; do not introduce microservices | Accepted | No scale, team ownership, or reliability requirement warrants service decomposition. Training remains separate from online inference. |
| D016 | Make Phase 2 a local end-to-end synthetic event-to-investigation application; Phase 3 completes MLOps controls and AWS deployment | Accepted | Fits requested two-prompt implementation plan while preserving dependency gates and a working core. AWS deployment remains compulsory. |
| D017 | Standardize event names and API/data contracts before implementing generation or inference | Accepted | Current docs conflict (`event_time`/`event_timestamp`, `network_token`/`ip_token`, `fraud_label`/`label_fraud`); one versioned contract prevents incompatible code and label leakage. |
| D018 | Prefer RDS PostgreSQL when the confirmed budget permits; otherwise use encrypted persistent EC2 storage with tested backup/restore | To validate before provisioning | RDS reduces database operations risk but incurs ongoing cost; the audit cannot see AWS credits/budget. Both options must keep DB private and persist data across deploy/restart. |
| D019 | Keep MLflow private/internal and store deployed model artifacts in S3 | Accepted | The public application needs model lifecycle evidence; the tracking interface is administrative/internal and must not be exposed as a public service. |
| D020 | Defer vishing NLP and advanced infrastructure from the required delivery path | Accepted | Blueprint labels vishing/advanced streaming/orchestration as optional or P2; they add dataset, operations and deployment risk before core acceptance. Revisit only after P0 and P1 gates pass. |
| D021 | Use a fixed synthetic dataset seed, chronological 80/20 holdout, Logistic Regression vs. Random Forest selection by PR-AUC, and a weighted `risk-v1` policy | Accepted for Phase 2 demo | Reproducible baseline that can be exercised without external data. Policy weights and threshold are provisional and must not be described as calibrated real-world performance. |
| D022 | Bootstrap the first Administrator using an explicit environment-provided username and 12+ character password; no default account | Accepted | Avoids a committed/shared credential and keeps account creation under deployment owner control. |
| D023 | Run the private Compose MLflow service from the exact API image; persist its SQLite backend and proxied artifacts in separate named volumes | Accepted for local Phase 2 | Avoid a second independently versioned MLflow image and prevent client containers from receiving an inaccessible `file:` artifact URI. The API waits for MLflow health; this remains to be verified by a completed Compose startup and training run. |

Add a new entry before changing an accepted architecture decision. Include context, options, decision, consequences and date.
