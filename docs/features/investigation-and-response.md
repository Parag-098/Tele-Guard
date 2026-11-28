# Feature Spec — Investigation and Simulated Response

## Goal
Give analysts a traceable workflow to review risk signals and give authorized operators a controlled simulated response process.

## Requirements
- Incident queue with search, filters, assignment, status and severity.
- Detail view with event timeline, related synthetic entities, model explanation, graph evidence, fired rules and detector versions.
- Notes and labels: confirmed fraud, legitimate, inconclusive, duplicate.
- Preserve label actor, timestamp and provenance.
- Simulated actions: monitor, escalate, request verification, temporary synthetic restriction.
- Backend permission checks and optional approval step.
- Audit actor, target token, reason, timestamp and state transition.
- Reversal workflow where applicable.

## Acceptance criteria
- Viewer cannot mutate incidents or execute actions.
- Analyst can investigate and label but cannot execute restricted operator actions unless explicitly granted.
- Operator action is persisted and audited.
- Reversal is recorded as a new event, not destructive history editing.
- No real carrier API or real phone-number blocking integration exists.

## Correlated investigations, labels and impact TG-09 to TG-10

Build case association atop existing incidents and predictions. Use bounded indexed lookbacks and require same-subscriber escalation or multiple corroborating evidence types for cross-entity links. Common network/location/device alone is weak evidence. Add configurable max age, link count, case size and risk gates. Use deterministic ordering with one idempotent linkage per scored event. Keep original incident keys and prior audit trail. Record why a link was proposed, approved, declined, merged or reversed. Consolidation retains notes, evidence and actions, offers a traced source/target timeline, and requires authorization and rationale. Reopening preserves the earlier resolution history and triggering evidence.

Support event and case adjudications with confirmed synthetic fraud, legitimate, false-positive disposition, inconclusive, and duplicates. Separate operational disposition from the binary training label; conflicting case/event evidence goes to review, and a case outcome does not silently label every event in it. Record actor, reviewer, time, source, affected scope, justification and correction reference; retain raw simulator truth privately until scheduled release. Use stratified uncertain-case review and reproducible random low-risk sampling to measure selection bias. Validate provenance, corrections, duplicate event/split membership, label availability and review permissions before freezing a new dataset. Keep known label fraud/corruption quarantined.

Retain RBAC for investigation, adjudication, merge/reopen and reversible simulated actions. Approval scope depends on role and action and remains auditable. Expose timeline, SHAP and graph evidence with risk component versions and confidence limits.

Compare one-alert-per-event and correlated policies on identical labeled replay with equal analyst budget. Report cases per 1,000 events, false positives, investigations per analyst review period, distinct fraud episodes alerted, episode precision/recall by family, precision at fixed review budget, duplicate alert reduction, time to first alert and case resolution distribution. Define episode matching and denominators before comparing. Record missed episodes and false merges. Monetary exposure is optional and simulated, with explicit currency, per-scenario cost, event deduplication and assumed probability. Keep it distinct from realized loss or prevention. [Acceptance](../TESTING_AND_TRACEABILITY.md#requirement-to-test-matrix).

## Implemented case and feedback workflow

Migration `0010_investigations` adds case links, consolidation history and adjudications. Existing cases retain their original ID, prediction, notes and actions. The same case association runs for API events, CSV and dataset batches. Each alert links once, and severity follows the strongest saved alert. Default bounds are 120 minutes and 40 alerts per case. Cross-subscriber links require a matching device **and** network and risk of at least 0.60. Override those bounds through `TG_CASE_MAX_AGE_MINUTES`, `TG_CASE_MAX_EVENTS` and `TG_CASE_CROSS_ENTITY_MIN_RISK` in the API and worker environment. The candidate rule is evaluated against the original case anchor, so a sequence of weak matches cannot expand the event window.

- `GET /api/incidents/{id}/timeline` shows scored events, reasons for linkage, related entity tokens, adjudications and prior consolidation actions. Administrators and Investigators can consolidate, reverse consolidation or reopen a closed case. Consolidated records remain addressable in their timelines and disappear from the default queue until a reversal.
- Reviewers can submit event and case adjudications with a rationale. Corrections refer to the latest adjudication and preserve the prior reviewer and decision. An optional request UUID deduplicates retried submissions. A case disposition alone produces no event labels. Conflicting case evidence suppresses the analyst event-label projection until adjudication resolves it.
- Event Explorer exposes the seeded review sample from up to 2,000 unreviewed predictions, combining low-risk candidates with near-threshold cases. Overview compares the existing policy and one-alert-per-event with a configurable review budget on the same scored cohort. Episode family measures use the synthetic label family and a documented inactivity window, with overall precision computed only for known case outcomes.

The [2026-11-28 investigation acceptance report](../INVESTIGATION_ACCEPTANCE_2026-11-28.md) records the paired replay and browser workflow.
