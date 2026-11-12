# Feature Spec — Model Lifecycle and MLOps

## Goal
Demonstrate reproducible model development, evaluation, registry, controlled release, monitoring and rollback.

## Requirements
- Record dataset/generator version, feature schema, source revision, parameters, metrics and artifacts.
- Use time-aware splits; fit preprocessing only on training data.
- Compare a simple interpretable baseline with at least two candidate models.
- Report PR-AUC, precision, recall, F1 at a stated threshold, false-positive rate and calibration; include per-scenario results when labels support them.
- Register candidate and approved model versions.
- Enforce explicit evaluation gates before promotion.
- Support shadow inference; challenger outputs must not affect operational actions.
- Support controlled simulation-only canary and rollback.
- Record model version for every prediction.
- Monitor feature/prediction drift; distinguish drift from measured performance deterioration when labels are delayed.

## Acceptance criteria
- A run is reproducible from recorded metadata.
- Candidate promotion can be rejected by a failed gate.
- Rollback restores a previously approved model.
- No model artifact is loaded from an untrusted arbitrary path supplied by a request.
- UI shows model version and relevant evaluation evidence.
