# TeleGuard AI — Product Scope & Feature Blueprint

**Working title:** TeleGuard AI  
**Proposed subtitle:** Intelligent Telecom Fraud Detection, Investigation & Prevention Platform  
**Document type:** Product definition and feature scope  
**Purpose:** Decide what the finished project will contain before writing implementation tasks or asking coding agents to build it.

---

## 1. Project vision

TeleGuard AI is an educational, cloud-deployed telecom fraud intelligence platform. It ingests simulated telecom events, identifies suspicious activity using multiple detection approaches, connects related entities to uncover coordinated fraud, explains its assessments, and gives analysts a controlled workflow to investigate and respond.

The project must demonstrate both:

1. **Fraud intelligence:** meaningful detection of telecom-specific fraud patterns, including suspicious individual activity and coordinated networks.
2. **MLOps engineering:** repeatable model development, evaluation, registry, deployment, monitoring, and controlled retraining.

This is not intended to be a direct connection to a real mobile operator. All subscriber identities, phone numbers, devices, events, locations, and blocking actions in the demonstration are synthetic. The platform will not intercept calls, read real SMS messages, obtain real subscriber GPS data, or block real phone numbers.

## 2. Problems the platform will detect

The initial product will support six telecom fraud categories plus general anomaly detection.

| Fraud category | Detection objective | Example signals |
|---|---|---|
| SIM swap / account takeover | Detect suspicious SIM replacement followed by account activity | Recent SIM change, new device, new IP, OTP/authentication burst |
| Vishing / social engineering | Identify suspicious conversations and related telecom behaviour | Transcript phrases, conversation progression, repeated scam patterns, unusual call context |
| Location mismatch / impossible travel | Identify incompatible locations across related events | Distance, elapsed time, device identity, cell-area changes |
| Call bombing / rapid-fire calling | Detect high-volume or coordinated call/SMS bursts | Calls per minute, recipient diversity, duration patterns, repeated targets |
| SIM farm / identity abuse | Detect suspicious reuse of devices and network identifiers | Many SIMs/numbers per device, shared IPs, rapid identity changes |
| Coordinated fraud rings | Detect networks of related suspicious entities | Shared devices, SIMs, IPs, callers, recipients and repeated relationships |
| Unknown anomalies | Flag behaviour not matching known labelled scenarios | Unusual behavioural patterns and outlier scores |

**Important scope distinction:** CDR metadata can provide risk indicators for vishing, but cannot prove what was said in a call. Transcript-based vishing detection will be a separate NLP module. Likewise, a location-mismatch demonstration needs a simulated authentication/OTP event feed in addition to telecom events; a telecom operator's CDR alone does not necessarily contain a bank's login location.

## 3. Product modules

### Module A — Data ingestion and event simulator

The platform needs a reliable way to receive data and a convincing way to demonstrate live operation.

**Capabilities**
- Upload CSV datasets for batch processing.
- Generate synthetic telecom events continuously.
- Ingest individual events through a REST API.
- Validate event schemas and reject malformed records.
- Detect duplicate event IDs and make ingestion idempotent.
- Preserve event timestamps and source metadata.
- Show ingestion volume, rejected records and processing status.

**Event families**
- Call detail records: caller, receiver, timestamp, duration, call direction, call outcome, roaming/international indicator.
- SMS records: sender, receiver, timestamp, message type/category and count-level metadata.
- SIM lifecycle: SIM activation, replacement, deactivation and SIM-to-subscriber association changes.
- Device/network: synthetic device identifier, IP/network token, device change and association history.
- Location: synthetic cell area or coordinates with event timestamp and stated source.
- Authentication/OTP: synthetic request/verification events used to demonstrate cross-system location mismatch.
- Optional conversation: transcript or labelled text chunks for the separate vishing module.

**Product output:** a live event feed showing received events, processing state and resulting risk assessments.

### Module B — Feature engineering and behavioural profiles

Create features from event history rather than relying only on isolated rows.

**Initial features**
- Calls and SMS counts over configurable time windows.
- Outgoing/incoming ratio.
- Unique contacts and recipient diversity.
- Average and unusual call duration.
- International/roaming call ratio.
- SIM tenure and time since SIM replacement.
- New-device and new-IP indicators.
- Device/SIM/account sharing counts.
- Location distance and speed/temporal plausibility.
- Failed or repeated OTP/authentication activity.
- Behaviour compared with the subscriber's own historical baseline.
- Graph-derived entity relationship features.

All features used for inference must be computable from information available at the prediction timestamp. Training and serving must use the same feature definitions to prevent training-serving skew.

### Module C — Multi-layer fraud detection engine

The platform should use complementary detection methods. It should not pretend that every model independently detects every fraud category.

**C1. Supervised ML**
- Logistic Regression as an interpretable baseline.
- Random Forest as a non-linear baseline.
- XGBoost and/or LightGBM as strong tabular candidates.
- CatBoost only if it adds measurable value for categorical features.
- Compare models on the same time-aware validation and test splits.

**C2. Unsupervised anomaly detection**
- Isolation Forest as the initial anomaly detector.
- Optional autoencoder experiment only if there is enough useful data and time.
- Produce an anomaly score, not an unsupported claim that an anomaly is definitely fraud.

**C3. Rules engine**
- Configurable rules for high-risk combinations and known operational signals.
- Rules should be inspectable and versioned.
- Record exactly which rules fired for each assessment.
- Rules should complement, not secretly override, model evaluation.

**C4. Graph intelligence**
- Build a graph of subscribers, phone-number tokens, SIMs, devices, IP/network tokens, and event relationships.
- Identify shared devices, high-degree entities, suspicious clusters and repeated connections.
- Start with NetworkX and explainable graph metrics/community detection.
- Treat graph signals as supporting evidence; shared infrastructure alone is not proof of fraud.
- A Graph Neural Network is a later research extension, not a first-version dependency.

**C5. Unified risk engine**
Combine available signals into one risk assessment:
- Calibrated supervised-model probability.
- Anomaly score.
- Graph risk indicators.
- Triggered rules.
- Data-quality/confidence indicators.

Return a risk band such as Low, Medium, High or Critical, along with evidence and recommended next action. Store the contribution of each detection layer. Do not use arbitrary fixed weights without validation; document and evaluate the scoring policy.

### Module D — Explainability and evidence

Every assessment should answer: “Why did the system flag this activity?”

**Capabilities**
- Fraud probability and risk band.
- SHAP explanation for supported supervised models.
- Top contributing features in readable language.
- Triggered rules and their evidence.
- Related entities and graph paths.
- Event timeline with timestamps.
- Model version, feature version and prediction timestamp.
- Data quality warnings and missing evidence.

Use an evidence-based explanation. Do not ask an LLM to invent reasons or treat its narrative as the model's explanation.

### Module E — Fraud investigation and case management

A prediction is not the end of the workflow. Analysts need a place to review it.

**Capabilities**
- Automatically create an incident when configured risk conditions are met.
- Incident queue with risk, time, category and status.
- Incident detail page with event timeline, model reasons, rules and graph connections.
- Assign an incident to an analyst.
- Add notes and evidence references.
- Mark a case as confirmed fraud, legitimate, inconclusive or duplicate.
- Record a reason for every resolution.
- Maintain a complete audit history.
- Generate an evidence-based investigation summary.

**Simulated response actions**
- Approve/allow.
- Flag for review.
- Request additional verification.
- Recommend temporary restriction.
- Approve a simulated temporary block.
- Reverse/unblock a simulated restriction.

All consequential actions must be permission-checked, reversible where possible and recorded. No real subscriber or phone number is blocked.

### Module F — Fraud network explorer

This is one of the project's main visual differentiators.

**Capabilities**
- Interactive graph of related numbers, subscribers, SIMs, devices and IP/network tokens.
- Select an entity and explore its connections.
- Highlight suspicious clusters and shared infrastructure.
- Show why two entities are connected.
- Display the evidence and time range behind an edge.
- Filter by entity type, time range and risk.
- Open an incident from a suspicious cluster.

Do not label every connected group a fraud ring. Present it as a suspicious network for analyst review.

### Module G — Vishing / conversational fraud module

This is an additional, clearly separated detection module.

**Initial capabilities**
- Accept a labelled transcript or conversation chunks.
- Classify text into suspicious/benign or supported fraud categories.
- Support incremental/chunk-level risk updates if the dataset supports it.
- Display highlighted text evidence and category confidence.
- Link the conversation assessment to a synthetic call/session when identifiers match.
- Keep this result separate from CDR-only predictions, then combine it in the unified risk view only when relevant evidence exists.

A potential research dataset is ICFD-31k, which describes English/Hinglish call transcripts, multiple fraud categories, and chunk-level streaming labels. Before using it, inspect its license, data availability, documentation and intended use. Do not make this module a blocker for the core CDR platform.

### Module H — Analyst dashboard and application UI

The finished product should be a proper web application, not only a notebook or a basic ML demo.

**Pages**
1. **Overview:** event volume, incidents, risk distribution, fraud categories and recent activity.
2. **Live Monitoring:** simulated incoming events, live predictions and processing state.
3. **Fraud Explorer:** searchable/filterable events and prediction history.
4. **Network Intelligence:** graph investigation view.
5. **Incident Center:** case queue, assignment, evidence, notes and resolution.
6. **Model Intelligence:** model versions, metrics, comparison and promotion status.
7. **Data Observatory:** data quality, feature distributions and drift.
8. **MLOps Operations:** training runs, model registry, candidate evaluations and retraining history.
9. **System Health:** API latency, errors, event throughput and worker/service health.
10. **Administration:** users, roles, permissions and configuration.

### Module I — User management, security and audit

**Roles**
- Administrator: users, roles, configuration and audit access.
- Fraud Analyst: investigates, adds notes and labels cases.
- Operator: executes approved simulated actions.
- Viewer: read-only dashboards and reports.

**Capabilities**
- Login and secure session/token handling.
- Backend-enforced role and permission checks.
- Password hashing and secure secret management.
- Input validation and API rate limiting.
- Audit records for sign-in, data changes, case decisions and response actions.
- No secrets or real personal data committed to the repository.

### Module J — MLOps lifecycle

This module is compulsory to the identity of the project. The project is not complete if it only trains a model once.

**Capabilities**
- Version datasets and generator configuration.
- Validate input data and training schemas.
- Reproducible training pipeline.
- Track parameters, metrics, artifacts and code/data versions.
- Register model candidates.
- Compare champion and challenger models.
- Apply quality gates before promotion.
- Record model versions used for predictions.
- Monitor input/prediction drift.
- Collect analyst feedback and later labels.
- Trigger a retraining candidate when configured conditions are met.
- Require evaluation and approval/promotion policy before production replacement.
- Roll back to a previously approved model version.

**Recommended promotion metrics**
- PR-AUC.
- Fraud precision and recall.
- F1 at a stated operating threshold.
- False-positive rate.
- Probability calibration.
- Inference latency.
- Performance by fraud category and relevant data segments.

Do not choose a model using accuracy or F1 alone. Fraud is an imbalanced problem and missed fraud and false alarms have different costs.

## 4. Main application workflow

```text
Synthetic CDR / SIM / SMS / Device / Location / OTP Events
                           |
                           v
                  Ingestion + Validation
                           |
                           v
                 Event Storage + Features
                           |
            +--------------+--------------+
            |              |              |
            v              v              v
        Supervised      Anomaly         Graph
          Models         Model        Intelligence
            |              |              |
            +--------------+--------------+
                           |
                      Rules Engine
                           |
                           v
                    Unified Risk Engine
                           |
                           v
             Prediction + Explanation + Evidence
                           |
                 Incident / Review Queue
                           |
                           v
                  Analyst Investigation
                           |
                Approved Simulated Action
                           |
                           v
               Feedback + Audit History

Offline MLOps:
Versioned Data -> Validation -> Training -> MLflow
              -> Evaluation Gates -> Model Registry
              -> Approved Model -> Serving
              -> Monitoring -> Candidate Retraining
```

## 5. Data strategy

The existing presentation proposes 50,000 synthetic CDR records and a small feature set. Keep that as the starting baseline, but expand it into a relational, event-based synthetic telecom dataset.

### Recommended data design

Instead of one flat CSV, generate related tables/files:

- `subscribers`
- `call_events`
- `sms_events`
- `sim_events`
- `device_events`
- `network_events`
- `location_events`
- `authentication_events`
- `entity_relationships`
- `fraud_labels`
- `incident_scenarios`

Use synthetic identifiers and generated locations. Create both fraudulent and benign lookalike scenarios.

### Fraud scenario generator

Generate labelled scenarios for:
- SIM replacement followed by suspicious activity.
- High-velocity call/SMS bursts.
- Unusual international calling.
- Implausible location changes.
- Shared devices and SIM farms.
- Coordinated groups targeting multiple subscribers.
- Account takeover with multiple correlated changes.
- Legitimate SIM replacement, travel, device upgrades and high-volume business calling to measure false positives.

Start with a manageable dataset and scale after the pipeline works. A target of 100,000–300,000 generated events is a reasonable first engineering target, not a requirement or claim of realism. Use fixed seeds and record generator version/configuration.

### Data safeguards

- No label leakage: labels, scenario names and future outcomes cannot become inference features.
- Use time-based splits and group/entity-aware checks where possible.
- Keep an untouched holdout test set.
- Document what is known at prediction time.
- Test that benign lookalikes are not trivially flagged.
- Check the license and schema before integrating any external dataset.
- Do not mix transcript rows and CDR events as if they were the same data type.

## 6. User roles and primary journeys

### Journey 1 — Live detection
A simulator emits a suspicious SIM event followed by new-device, OTP and location events. The platform enriches the activity, scores it and creates an incident if the configured policy is met.

### Journey 2 — Fraud ring investigation
An analyst opens an incident, sees its timeline, explores related devices and numbers in the graph, reviews SHAP/rule evidence, and records a decision.

### Journey 3 — Safe response
An authorized operator reviews an analyst recommendation, approves a simulated temporary restriction, and can later reverse it. Every action is audited.

### Journey 4 — Model lifecycle
An ML engineer trains a candidate model, compares it with the champion on a time-aware holdout, reviews the quality gate, and promotes or rejects it. The prediction service records which version served each prediction.

### Journey 5 — Drift and feedback
The system monitors incoming feature distributions. Analyst labels are collected. A configured monitoring/retraining workflow can prepare a new candidate, but does not silently deploy an unvalidated model.

## 7. What the professor should see in the final demo

Prepare three reliable seeded scenarios instead of depending on random demo data.

### Demo A — SIM swap / account takeover
- Recent SIM replacement.
- New device and network context.
- OTP/authentication burst.
- Model + rules identify elevated risk.
- Timeline and explanation are shown.
- Incident enters analyst queue.

### Demo B — Coordinated fraud ring
- Several synthetic numbers share devices/IP tokens and target multiple victims.
- Graph explorer displays a suspicious cluster.
- Analyst investigates the relationships and marks the case.

### Demo C — Legitimate behaviour
- A legitimate SIM replacement or device upgrade occurs.
- Some signals look unusual, but the total evidence is insufficient for a fraud decision.
- System allows or requests review rather than blindly blocking.
- This demonstrates attention to false positives.

Optional fourth demo: a Hinglish/English vishing transcript is analysed by the separate conversation module.

The presentation should show measurable results: precision, recall, PR-AUC, false-positive rate, latency, throughput, model version, drift status, and successful AWS deployment.

## 8. AWS product deployment requirement

The final application must be publicly reachable through an AWS-hosted URL and provide a working end-to-end demo.

### First deployment target
Use a cost-conscious EC2 deployment with Docker containers, ECR for images, S3 for model/data artifacts, CloudWatch for logs/alarms, IAM for permissions, and persistent PostgreSQL storage. Configure HTTPS and protect all internal services.

### Possible later upgrade
Move selected services to ECS Fargate if time and budget justify it. ECS is an extension, not a condition for calling the AWS deployment complete.

### AWS acceptance conditions
- Public HTTPS application URL.
- Login and seeded demo accounts with different roles.
- Live synthetic event demo.
- Real model inference, not hardcoded predictions.
- Persistent incident and review records.
- Model artifacts retrievable from durable storage.
- Cloud logs and a basic health/alert view.
- Documented restart, backup and teardown procedures.
- Budget alerts and least-privilege permissions.

## 9. Technology direction

| Area | Proposed choice |
|---|---|
| Frontend | React + TypeScript |
| Backend | FastAPI |
| Database | PostgreSQL |
| Data/ML | Python, Pandas, NumPy, scikit-learn |
| Supervised models | XGBoost / LightGBM; baselines for comparison |
| Anomaly detection | Isolation Forest |
| Graph analytics | NetworkX initially |
| Graph UI | Cytoscape.js |
| Explainability | SHAP |
| Experiment tracking/registry | MLflow |
| Data versioning | DVC |
| Data validation | Pandera |
| Tuning | Optuna, only where useful |
| Drift | Evidently or a measured custom monitor |
| Local environment | Docker Compose |
| Cloud | AWS EC2, ECR, S3, IAM, CloudWatch |
| CI | GitHub Actions |
| Tests | Pytest, frontend component tests and Playwright for key flows |

Do not add Kafka, Airflow, Kubernetes, Redis, Celery, RDS or a GNN just to increase the technology count. Add them only when the product behaviour needs them. The first working system should be easy to run locally and deploy.

## 10. Feature priority — what is actually in the project

### P0 — Required product
- Synthetic event generator and documented event schema.
- CDR, SIM, device, SMS, location and authentication events.
- Data validation and time-aware feature engineering.
- Multiple supervised models and honest evaluation.
- FastAPI inference.
- PostgreSQL persistence.
- Unified risk assessment and evidence.
- Basic rules engine.
- SHAP explanations where supported.
- Incident queue and analyst workflow.
- Backend authentication and RBAC.
- MLflow experiment tracking and model versioning.
- React dashboard.
- Docker local environment.
- CI tests.
- AWS public deployment.

### P1 — Signature differentiators
- Isolation Forest anomaly detection.
- Graph-based suspicious network exploration.
- Hybrid risk scoring across available detection layers.
- Live event simulator and streaming dashboard updates.
- Model quality gates and champion/challenger promotion.
- Drift monitoring and analyst feedback.
- Reversible simulated response actions with audit trail.

### P2 — Advanced extensions
- Transcript-based English/Hinglish vishing classifier.
- Chunk-level/streaming conversation analysis.
- LLM-generated evidence-grounded investigation summaries.
- Kafka streaming.
- Airflow-based retraining orchestration.
- Graph Neural Network research experiment.
- ECS Fargate deployment upgrade.

P0 and P1 must work before P2 is attempted. If schedule or budget becomes constrained, P2 is reduced first.

## 11. Features we are deliberately NOT promising

- Integration with a real telecom operator or carrier network.
- Real phone-number blocking.
- Access to real GPS, private SMS, OTP or call audio.
- Guaranteed detection of every scam type.
- A production-ready GNN before graph data is validated.
- Fully autonomous blocking without human/policy controls.
- A chatbot that makes fraud decisions.
- “Real-time” performance claims without measurements.
- Enterprise-scale availability or compliance certification.

These boundaries make the project credible and prevent a demo from claiming capabilities it does not have.

## 12. GitHub research and design inspiration

These repositories are useful references for patterns to study. We should implement our own telecom-specific product and not copy code without reviewing its license and dependencies.

1. **Databricks telecom fraud prevention:** https://github.com/databricks-industry-solutions/fraud_prevention_in_telco  
   Useful ideas: separate executive/management/analyst experiences, multiple data sources, rule-based CDR checks, and guided demo scenarios.

2. **Fraud Detection MLOps Platform:** https://github.com/RidhanPar/fraud-mlops-platform  
   Useful ideas: time-ordered evaluation, PR-AUC-based promotion gates, serving parity, explanation-linked audit records, drift monitoring and AWS deployment.

3. **ICFD-31k conversational fraud dataset:** https://github.com/SPELLAILab/ICFD-31k  
   Potential source for a separate English/Hinglish transcript analysis module with chunk-level labels. Check license and availability before use.

4. **End-to-end MLOps fraud pipeline:** https://github.com/rafiveyisov/end-to-end-mlops-fraud-detection  
   Useful lifecycle reference for data preprocessing, MLflow, model serving, monitoring and automation.

5. **AWS MLOps best practices:** https://github.com/aws-samples/sample-mlops-bestpractices  
   Useful reference for AWS-native monitoring and managed pipeline patterns.

## 13. Final definition of the product

The first complete version of TeleGuard AI will be:

> A cloud-deployed telecom fraud intelligence platform that ingests synthetic telecom and related authentication events, detects SIM-swap/account-takeover patterns, abnormal calling/SMS behaviour and suspicious entity networks through supervised ML, anomaly detection, graph analytics and rules, generates traceable explanations, and supports human-reviewed incident response. Its MLOps pipeline versions data and models, evaluates model candidates, monitors drift, and supports controlled retraining and rollback.

This is the product scope. Only after this scope is accepted should it be converted into `PROJECT_SPECIFICATION.md`, `ARCHITECTURE.md`, feature specifications, `AGENTS.md`, and small implementation tasks.
