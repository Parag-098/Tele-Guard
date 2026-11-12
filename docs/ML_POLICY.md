# Initial synthetic model and risk policy

The first artifact is trained offline by `backend/app/ml.py` from a fixed-seed synthetic generator. Events are ordered by `event_time`; the first 80% trains and final 20% is a temporal holdout. Logistic Regression with training-only scaling is compared with a class-weighted Random Forest; serving selects the higher holdout PR-AUC candidate. The artifact contains the classifier and an Isolation Forest trained only on benign rows in the training partition. The artifact version, selected algorithm, feature schema and synthetic dataset version are retained with model-run metadata.

The input features (`features-v1`) are duration, event type indicators, prior same-subscriber device/network token frequency and event hour. Label and scenario fields are not model features. History is sorted temporally and uses only records at or before the scored event timestamp.

The default `risk-v1` policy is an explicitly provisional, deterministic weighted signal summary. Weights and incident threshold can be overridden with `TG_RISK_*` and `TG_INCIDENT_RISK_THRESHOLD`; deployments must bump `TG_RISK_POLICY_VERSION` whenever they change policy values:

| Component | Weight |
|---|---:|
| Supervised probability | 0.62 |
| Isolation Forest normalized outlier score | 0.18 |
| Graph-linked subscriber count (capped normalization) | 0.08 |
| Fired versioned metadata rule | 0.12 |

Risk bands are Low `<0.35`, Medium `0.35–0.59`, High `0.60–0.79`, and Critical `>=0.80`. Scores `>=0.35` open an investigation. This threshold and weighting are demonstration policy values, not calibrated operating thresholds. A shared device/network alone cannot prove fraud; graph evidence has low weight and is presented as a lead for analyst review. All displayed evaluation values are based on synthetic data and are not estimates of real-world performance.

MLflow logs training parameters, scalar metrics and the serialized artifact when the tracking service is available. Model promotion gates, approval, shadow/canary, rollback and drift/performance monitoring are not implemented in this phase.
