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
