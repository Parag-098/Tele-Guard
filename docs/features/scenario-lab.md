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
