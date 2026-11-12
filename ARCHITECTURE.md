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
- ECR stores container images.
- EC2 runs Docker Compose for the first affordable deployment.
- S3 stores datasets, model artifacts and reports.
- IAM instance role grants least-privilege access.
- CloudWatch receives application logs and basic alarms.
- PostgreSQL uses persistent storage; decide EC2-hosted PostgreSQL versus RDS after cost/backup review.
- HTTPS reverse proxy or load balancer and DNS provide public access.

Never expose PostgreSQL, MLflow, monitoring dashboards or internal admin ports publicly. Document HTTPS, backups, security groups, secrets, cost alerts and teardown.
