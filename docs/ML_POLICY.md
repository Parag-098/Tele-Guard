# Initial synthetic model and risk policy

The first artifact is trained offline by `backend/app/ml.py` from a fixed-seed synthetic generator. Events are ordered by `event_time`; the first 80% trains and final 20% is a temporal holdout. Logistic Regression with training-only scaling is compared with a class-weighted Random Forest; serving selects the higher holdout PR-AUC candidate. The artifact contains the classifier and an Isolation Forest trained only on benign rows in the training partition. The artifact version, selected algorithm, feature schema and synthetic dataset version are retained with model-run metadata.

The input features (`features-v1`) are duration, event type indicators, prior same-subscriber device/network token frequency and event hour. Label and scenario fields are not model features. History is sorted temporally and uses only records at or before the scored event timestamp.

The default `risk-v2` policy extends the provisional deterministic weighted signal summary with a configurable location/travel scenario contribution (default context weight 0.20, independently configurable). Base weights and incident threshold can be overridden with `TG_RISK_*` and `TG_INCIDENT_RISK_THRESHOLD`; deployments must bump `TG_RISK_POLICY_VERSION` whenever policy values change:

| Component | Weight |
|---|---:|
| Supervised probability | 0.62 |
| Isolation Forest normalized outlier score | 0.18 |
| Graph-linked subscriber count (capped normalization) | 0.08 |
| Fired versioned metadata rule | 0.12 |

The context contribution adds `context_weight ? scenario_risk` to the base score before clipping to `[0,1]`. Risk bands are Low `<0.35`, Medium `0.35?0.59`, High `0.60?0.79`, and Critical `>=0.80`. Scores `>=0.35` open an investigation. These thresholds and weights are demonstration policy values, not calibrated operating thresholds. Shared-device/network and location context signals are leads for analyst review, not proof of fraud. All displayed evaluation values use synthetic data and are not estimates of real-world performance.

MLflow logs training parameters, scalar metrics and the serialized artifact when the tracking service is available. Administrator-controlled shadow/canary serving persists per-model outputs; delayed-label monitoring reports metrics after labels arrive and compares rolling windows for degradation.

## Phase 2 MLOps lifecycle controls

The application snapshots the deterministic 1,400-row seed-2026 baseline and seeded drift batches in PostgreSQL. Drift simulation shifts call duration and synthetic network/location token distributions while preserving generated fraud labels. The persisted PSI report uses a 0.20 feature threshold and states that feature drift alone does not prove concept drift or predictive degradation.

Retraining uses the versioned drift snapshot with the existing chronological 80/20 training/evaluation split and logs an actual MLflow run plus artifact. Candidate training never changes the active model pointer. Champion and challenger are compared on the same chronological 20% holdout from the challenger dataset at probability threshold 0.30, selected to prioritize fraud recall for this academic simulation. Promotion gates require PR-AUC no more than 0.02 below champion, recall no more than 0.03 below champion, and false-positive rate no more than 0.03 above champion. These thresholds are illustrative and need domain validation before any real operation. An administrator approval is required; failed candidates can be rejected without changing inference. Previously approved models can be restored through audited rollback. The active pointer is persisted in PostgreSQL and the API loads that artifact at startup.

The comparison gate is distinct from training-run metrics, which remain reported at the training pipeline's recorded 0.50 threshold. Metrics are synthetic and the generator's class composition can make false-positive estimates unstable. No claim of real-world performance is made.
