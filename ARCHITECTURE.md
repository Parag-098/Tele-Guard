# ARCHITECTURE.md

## Architectural style
Start with a modular monolith and a small number of containers. Separate offline training jobs from online inference. Split into services only when a measured scaling, reliability, security or ownership need justifies it.

## Logical flow
```text
React + TypeScript UI
        | HTTPS
FastAPI application — authentication/RBAC, APIs, validation
        |
Event ingestion -> PostgreSQL event store -> feature computation
                                          |-> supervised model
                                          |-> anomaly detector
                                          |-> graph intelligence
                                          |-> versioned rules
                                                   |
                                            risk assessment
                                                   |
                                     predictions + evidence store
                                                   |
                                  incident/investigation workflow
                                                   |
                                  human-approved simulated action
                                                   |
                                               audit log

Offline MLOps:
versioned data -> validation -> time-aware split -> features -> training
-> MLflow experiments/artifacts -> evaluation gates -> model registry
-> shadow/canary evaluation -> approved serving model -> monitoring
-> analyst feedback/labels -> candidate retraining
```

The implemented academic lifecycle covers a persisted baseline and drift snapshots, PSI reports, synchronous retraining, same-dataset champion/challenger evaluation, administrator approval/rejection, rollback, and on-demand model-faithful SHAP explanations. Shadow/canary inference, delayed-label performance monitoring, and deeper per-scenario evaluation remain future work.

## Domain modules
- `auth`: identity, sessions/tokens, roles and permissions.
- `events`: event schemas, ingestion, validation, deduplication and persistence.
- `features`: shared versioned online/offline feature definitions.
- `detection`: supervised and anomaly model loading/inference.
- `graph`: synthetic entity relationships, graph features and provenance.
- `rules`: versioned rules, evaluation and backtesting.
- `risk`: documented scoring policy; component outputs remain distinct.
- `incidents`: queue, assignment, investigation, labels and simulated responses.
- `mlops`: experiments, registry, evaluation gates, promotion and rollback.
- `audit`: important actions and state transitions.

## Key data entities (initial conceptual model)
`users`, `roles`, `user_roles`, `events`, `predictions`, `prediction_evidence`, `entity_relationships`, `subscriber_profiles`, `rules`, `rule_versions`, `rule_evaluations`, `scenario_runs`, `incidents`, `incident_notes`, `incident_labels`, `response_actions`, `model_versions`, `model_evaluations`, `audit_logs`.

The implementation also persists revocable `auth_sessions`, synthetic `demo_datasets`, typed `mlops_records`, prediction explanations, incident resolution provenance, and MLflow run IDs for model artifacts. Alembic revisions `0003`–`0005` add these fields/tables without dropping existing data. PostgreSQL stores the active model selection; inference loads the explicit selected model. Explanations use the model version stored on that prediction, validate its feature schema and check SHAP additivity. When a local `.joblib` artifact is missing, the API resolves its trusted stored MLflow run ID and downloads the matching artifact.

## Event lifecycle
1. Validate event type, schema, timestamp and ranges.
2. Deduplicate by stable event ID (idempotent ingestion).
3. Persist normalized event and provenance.
4. Compute only features available at prediction time.
5. Run enabled detectors and rules.
6. Persist component outputs, policy/model/feature versions and evidence.
7. Apply incident policy and return a prediction reference.
8. If a detector is unavailable, report partial/failure status; never silently substitute a fake prediction.

## Prediction contract (illustrative)
```json
{
  "prediction_id": "pred_demo_001",
  "event_id": "evt_demo_001",
  "model_name": "fraud_classifier",
  "model_version": "registry-version",
  "feature_schema_version": "features_v1",
  "scoring_policy_version": "risk_v1",
  "supervised_probability": 0.0,
  "anomaly_score": null,
  "graph_signals": [],
  "triggered_rules": [],
  "risk_score": null,
  "risk_band": "INSUFFICIENT_EVIDENCE",
  "evidence": [],
  "created_at": "ISO-8601"
}
```
Values are illustrative only. Define concrete types in API schemas. Do not copy example values as production logic.

## Risk policy
Keep supervised probability, anomaly score, graph signals, rule results and final operational risk separate. Missing signals are unavailable, not zero risk. Version the policy, document thresholds, calibrate on validation data and explain every material score contribution. A risk band is not a fraud verdict.

## Initial AWS topology
- ECR stores immutable commit-SHA images.
- One EC2 `t3.medium` in `ap-south-1` is the starting academic demonstration target; Docker Compose runs API, web, PostgreSQL, MLflow and Caddy.
- S3 stores proxied MLflow artifacts; PostgreSQL metadata and active model cache use bind mounts on an encrypted persistent EBS volume.
- MLflow tracking uses the PostgreSQL backend store. Both tracking and artifacts remain private behind Compose networking and IAM instance-role authorization.
- CloudWatch receives bounded-retention container logs through the `awslogs` driver; basic EC2 health is available from standard metrics.
- GitHub Actions is prepared to use OIDC, ECR and SSM Run Command for versioned release deployment.
- Caddy provides HTTPS when a domain resolves to the EC2 Elastic IP. This is a single-instance deployment without HA; AWS resources and public HTTPS remain unverified until provisioned.

## Current local acceptance correction (2026-11-19)

The operational data path now includes normalized `dataset_versions`, nullable `events.dataset_version`, a durable PostgreSQL `mlops_jobs` queue and one worker service. A reproducible 150,000-event seed was generated, persisted/scored in chunks, then used to train three candidates and record an MLflow run/model-registry version. The worker reports a database heartbeat; Data observatory and Live monitoring query persisted service data. Event and incident list endpoints batch-load related records so they remain usable at this data volume. `0008_versioned_datasets_jobs` is additive. The initial migration is frozen to the original event-v1 schema so clean installs can advance without prematurely creating later schema objects.

The full 2026-11-19 feature map, exact row/column counts, local test evidence, limitations and deployment decision are in [IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md](docs/IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md). This supersedes earlier statements here that shadow/canary, delayed labels, SHAP and location/travel remained future work. AWS remains unprovisioned and **NO-GO** pending external release acceptance.

Never expose PostgreSQL, MLflow, monitoring dashboards or internal admin ports publicly. Document HTTPS, backups, security groups, secrets, cost alerts and teardown.
