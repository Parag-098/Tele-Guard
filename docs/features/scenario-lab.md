# Feature Spec — Scenario Lab

## Goal
Generate repeatable synthetic telecom event streams for development, demonstrations, evaluation and controlled model comparisons.

## User stories
- As an analyst, I can start a named scenario and see events appear with timestamps and processing states.
- As a developer, I can reproduce a run using a seed and generator version.
- As a reviewer, I can compare a fraud scenario with a benign lookalike.

## Requirements
- Include benign baseline traffic and labelled scenarios: SIM swap/account takeover, rapid-fire call/SMS burst, Wangiri-style missed-call campaign, coordinated ring and legitimate lookalikes.
- Support seed, scenario type, duration, rate and simulation speed.
- Store scenario run metadata separately from event features.
- Allow pause/resume/stop and replay where feasible.
- Label all data and UI as synthetic simulation.

## Acceptance criteria
1. Same seed/config/generator version reproduces the same logical event sequence.
2. Generated events pass schema validation.
3. Scenario labels are not present in inference features.
4. A run can be stopped without corrupting already persisted events.
5. UI distinguishes simulated/replayed events from any other source.

## Location and travel scoring

Events may carry a synthetic location token and/or a latitude/longitude pair. Coordinates are optional and validated as a pair and within geographic bounds. At ingestion, the scorer compares coordinates with the prior location for the same subscriber, computes Haversine distance and elapsed time, checks configurable maximum speed and travel window, and records findings in prediction evidence. Repeated-history location tokens can also produce a review signal. Missing coordinates/tokens skip geographic checks with an explicit explanation. Scenario configuration is stored as versioned PostgreSQL MLOps records and is editable by administrators. Coordinates and scenario provenance are not supervised model features.

## API and persistence

- `POST /api/mlops/scenarios` stores bounded thresholds and named event-type/location-token rules (Administrator only).
- Evidence is stored with each `Prediction` and shown in the investigation evidence panel.
- Migration `0006_context_serving_labels` adds optional synthetic coordinates to events.
