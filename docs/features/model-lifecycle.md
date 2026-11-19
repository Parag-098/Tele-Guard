# Feature Spec — Model Lifecycle and MLOps

## Goal
Demonstrate reproducible model development, evaluation, registry, controlled release, monitoring and rollback.

## Requirements
- Record dataset/generator version, feature schema, source revision, parameters, metrics and artifacts.
- Use time-aware splits; fit preprocessing only on training data.
- Compare a simple interpretable baseline with at least two candidate models.
- Report PR-AUC, precision, recall, F1 at a stated threshold, false-positive rate and calibration; include per-scenario results when labels support them.
- Register candidate runs in MLflow and persist approval/active selection records in PostgreSQL.
- Enforce explicit same-holdout evaluation gates before promotion; administrator approval is mandatory.
- Support seeded feature-drift simulation and persist PSI reports against versioned reference/current datasets.
- Support explicit rejection and rollback to an earlier approved model; candidate training must not alter active inference.
- Record model version for every prediction.
- Monitor feature/prediction drift; distinguish drift from measured performance deterioration when labels are delayed.

## Acceptance criteria
- A run is reproducible from recorded metadata.
- Candidate promotion can be rejected by a failed gate.
- Rollback restores a previously approved model.
- No model artifact is loaded from an untrusted arbitrary path supplied by a request.
- UI shows model version and relevant evaluation evidence.

## Phase 2 implementation notes

The MLOps page and API now support a fixed-seed baseline, generated feature-shift batches, PSI feature reports, real MLflow-backed retraining, shared-dataset champion/challenger metrics, administrator approval/rejection, and approved-model rollback. Comparison uses a fixed 0.30 recall-prioritized threshold and gates on PR-AUC, recall, and false-positive rate. The PSI report explicitly distinguishes feature drift from concept drift/performance degradation.

## Shadow and canary serving

`POST /api/mlops/serving` is Administrator-only and stores each serving configuration in PostgreSQL with audit history. Shadow mode sends each eligible input to the selected candidate while the champion result remains the saved prediction. Canary mode deterministically assigns event IDs to the configured 0–100% challenger share; assigned inputs use challenger prediction output. Challenger artifacts are loaded and version-checked before configuration is saved. Runtime errors are audited and leave champion predictions in place. Promotion and rollback restore champion-only routing. Each champion/shadow/canary probability and outcome is persisted in `model_observations`.

## Delayed labels and performance monitoring

Predictions start with no ground-truth label. Authorized analysts, investigators, ML engineers, or administrators can submit one label at `POST /api/predictions/{event_id}/label`; a row lock and immutable-label check prevent duplicate updates. All stored model observations for the prediction receive the outcome exactly once. Monitoring reports pending/received labels, confusion counts, precision, recall, false-positive rate, Brier score and PR-AUC when both classes exist. Once 40 labeled observations are available for a version, the last 20 are compared with the prior 20; material recall/FPR degradation creates a dashboard alert with review and rollback/retraining guidance. Thresholds are demonstration defaults, not calibrated operational policy.

Migration `0006_context_serving_labels` adds coordinates, label fields and durable model observations. The MLOps dashboard displays deployment configuration, per-model monitoring, and alert state. Event Explorer supports delayed label entry. Playwright coverage is in `frontend/e2e`.
