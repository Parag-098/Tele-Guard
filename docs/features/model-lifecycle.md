# Feature Spec — Model Lifecycle and MLOps

> The Phase 2 notes record the demo implementation, including its historical fixed thresholds and routing. The [incremental lifecycle](#incremental-lifecycle-tg-06-to-tg-08) adds the operational design and fixes identified in the [2026-11-28 audit](../REPOSITORY_AUDIT.md#incremental-release-audit-2026-11-28).

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

## Incremental lifecycle TG-06 to TG-08

### Serving policy, routing and release state

Use a versioned decision policy artifact. Persist classifier threshold and comparable calibration, hybrid risk weights/cuts, scenario config, feature contract and routing ID. Use the recorded classifier decision consistently for evaluation, online/batch scoring, shadow and delayed-label metrics. The risk score and incident trigger are separate, explicitly versioned decisions. Keep old 0.30/0.50 results and risk-v2 attributions as historical policy observations and make comparison conditions visible to reviewers.

Use the full canonical subscriber identifier with a stable hash such as SHA-256 and a persisted experiment namespace. Map to fixed buckets, record 0%/100% boundaries and keep an assignment nested as the percentage grows. A run pinned to a policy and release remains explainable after restart. Track eligible unique subscribers/events, assigned challenger, actual served, shadow observations and fallback by release, stage and time. Treat low-volume traffic as inconclusive and report cohort denominators instead of promising exact ratios. Compare configured percent primarily to eligible distinct-subscriber allocation, and separately show event allocation and real fallback. Use the same logic for single, CSV, seed and live paths.

State sequence: trained → compared (passed / rejected) → shadow → approved and staged canary → promoted, suspended or rejected. Candidate work remains isolated until an administrator grants authority for any production canary and explicitly approves full promotion. Require evidence keyed to current champion release epoch, exact candidate artifact digests, independent evaluation manifest, feature/decision policy and gate profile. Any changed dependency invalidates approval evidence. Update release state and audit atomically with a lock or compare-and-set revision. Reject stale or incompatible changes, load trusted artifacts before transition, and update process caches from committed state. A newly created dataset cannot silently replace the champion. Initial bootstrap uses a pinned validated baseline and an explicit audited first-release path. Prior approved releases remain rollback targets. A strict failure limit may suspend canary and fall back to the current champion without new promotion.

Gates are reproducible, versioned and set before viewing final holdout results. Initial targets use the existing policy tolerances as starting guardrails: PR-AUC decline ≤0.02, recall decline ≤0.03 and FPR increase ≤0.03, plus an absolute alert budget, critical-category recall and legitimate-lookalike FPR guard with minimum positive/negative support. Add p95 end-to-end latency with an initial target of ≤500 ms at the documented evaluation load and hardware, no material regression above the approved tolerance, exact feature compatibility, valid manifests/digests and no split leakage. Use uncertainty intervals where support permits. Define category/support limits using development data, record reported denominators, and block promotion as insufficient evidence where a mandatory slice is underpowered. Record gates, reasons and comparisons for allowed and rejected candidates.

### Scheduled traffic monitoring

Persist exact serving features or reproducible privacy-safe aggregate inputs attributed to the actual model, schema, policy, source and role. Build frozen bins/categories, quality and score baselines from validated reference inference from a known release. Bin numeric values on reference quantiles with explicit missing, tail and constant-feature handling. Use PSI for stable distributions and, where justified, Jensen–Shannon distance or category shift summaries for low-cardinality fields. Track schema rejects, expected/missing rates, prediction/risk drift, predicted prevalence and score distribution. Do not combine legacy, demo, shadow or different schema views without explicit cohorting. Keep raw and retained summary data bounded.

Start with hourly windows, at least 500 scored events for the monitored cohort and at least two consecutive comparable windows over the configured PSI 0.20 investigation threshold. These are initial research settings. Use bounded adjustable window duration, watermark, sample floor, consecutive-window count and thresholds. Demo settings may lower support/accelerate clock and must be visible. Track planned window versus observed window, scheduling lag, support and freshness. Idempotency key includes reference, model/schema/policy, cohort and time window. Store one alert per continuing breach episode, record recovery and suppress duplicate actions. A missing or undersized window is a visible status.

Join events to labels available by the evaluated label cutoff, report label lag, coverage and source/subsampling mix. Monitor precision, recall, FPR, PR-AUC where both classes exist, Brier/calibration and episode performance. Require support for positives and negatives, and compare cohorts of compatible label age and review policy. Changes in true class prevalence require outcome evidence. Underpowered or unlabeled data may suggest covariate shift, class mix change or a data-quality issue. Concept drift is a hypothesis to investigate using comparable labeled distributions and outcomes.

| Signal | Action |
|---|---|
| Schema, excessive missingness or bad integrity | Quarantine invalid inputs, alert with source and reason, suspend dataset eligibility and fix upstream. |
| Sustained feature or prediction shift | Open a deduplicated investigation, break down affected cohorts and collect outcome evidence. |
| Supported delayed-label degradation or validated new adjudicated dataset | Apply versioned triggers and cooldown, then enqueue an eligible training job after quality/preflight check. |
| Routine schedule | Enqueue only when new approved labeled inputs and resource window meet policy. Otherwise record a skipped trigger and reason. |
| Low coverage, insufficient samples or monitoring outage | Emit a supported state and investigate availability. Keep serving the approved model under the recorded policy. |

### Durable training and automatic triggers

Extend the PostgreSQL worker with explicit typed stages: queued → validating → preparing → fitting → evaluating → publishing → registered; terminal failure, cancelled or rejected have durable reasons. Job idempotency key binds trigger window/reason, dataset manifest and policy/config. Lock claims transactionally and use renewable ownership leases and a sweeper for expired jobs. Pin all versions and workspace-compatible dependencies before starting. Bound workers, retries, exponential backoff, memory, timeout, artifact writes and cooldown. Use checksummed staging outputs, checkpoints at safe boundaries, and idempotent reconciliation for partial MLflow runs or artifacts. Store attempts/outcomes and cancellation requests. Abort or checkpoint only at supported boundaries and preserve prior successful dataset outputs.

Create jobs automatically from eligible scheduled/event triggers without owner scripts and keep manual submission authorized and audited. On failure serve the existing champion and keep candidate evidence. MLflow captures revision, dependency lock, dataset/split digest, fit and assessment configuration, policy/calibration artifact, metrics and explanations, compute/runtime, and content digest. Persist run ID and registered model selection before exposing the candidate. A tracking outage may pause/retry publication, but a run lacking required lineage cannot be eligible for release. Link monitoring, trigger, job, dataset, result, approval and subsequent rollout. The [matrix](../TESTING_AND_TRACEABILITY.md#requirement-to-test-matrix) defines pass/failure evidence.
