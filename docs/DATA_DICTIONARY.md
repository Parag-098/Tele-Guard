# Canonical Event Contract — `event-v1`

> The opening table is the original event-v1 summary. The 2026-11-19 expansion and current JSON/Pydantic sources take precedence for fields and enum values. The [incremental contracts](SYSTEM_CONTRACTS.md) and [dataset specification](DATASET_AND_SIMULATOR.md) document proposed additions.

The authoritative machine-readable definition is [`backend/app/schemas/event-contract.json`](../backend/app/schemas/event-contract.json), enforced by `backend/app/schemas.py` and persisted by `backend/app/models.py`. Use this contract in generation, ingestion, feature building, inference, investigation and UI responses. All identifiers are synthetic tokens. `event_time` is the canonical spelling (replaces `event_timestamp`); `network_token` is canonical (replaces `ip_token`).

| Field | Type | Required | Meaning and validation |
|---|---|---:|---|
| `contract_version` | string | no | Must be `event-v1`; defaults to this version. |
| `event_id` | string | yes | Stable unique ingestion key, 4–64 chars; metadata, not a model feature. |
| `event_type` | enum | yes | `CALL`, `SMS`, `SIM_CHANGE`, `DEVICE_CHANGE`, `ACCOUNT_ACTIVITY`, `NETWORK_ACTIVITY`, `LOCATION`. |
| `event_time` | timezone-aware timestamp | yes | Event occurrence time; features use only information available at this timestamp. |
| `subscriber_id` | synthetic token | yes | Synthetic subscriber key, 3–64 chars. |
| `source_token`, `destination_token` | token/null | no | Synthetic source/destination tokens; never phone numbers. |
| `sim_id`, `device_id`, `network_token` | token/null | no | Synthetic identity/device/network tokens; no SIM serial, device serial, raw IP or carrier identifier. |
| `location_token` | synthetic region/null | no | Coarse generated region token; no GPS coordinates. |
| `duration_seconds` | integer/null | no | 0–86400, relevant to calls. |
| `scenario_label` | string/null | no | Generator provenance; excluded from inference features and public event response does not expose fraud ground truth. |
| `fraud_label` | integer/null | no | Synthetic training/evaluation label (0/1); excluded from inference features and event API response. |

Extra input fields are rejected. Duplicate `event_id` returns the existing event/prediction and does not duplicate persistence. Inference features are `duration_seconds`, event-type indicators, prior per-subscriber device/network token frequency, and event hour (`features-v1`). They contain no label, scenario, entity ID or future-event values. The online feature context includes events from the same subscriber at or before the scored event time.

## Related persisted records

`events` records the canonical event and training-only label; `predictions` stores component signal values, policy/model/feature versions and evidence; `incidents` refer to predictions; `incident_notes` capture investigation notes; `audit_logs` records actor/action/target/reason/details and time; `model_runs` stores synthetic dataset version, model algorithm, metrics and artifact path. Event and prediction are joined through the stable `event_id`.

## Schema and dataset expansion (2026-11-19, migration `0008`)

The table above describes the original event-v1 baseline. The backward-compatible event type enum now also accepts `OTP_REQUEST` and `AUTHENTICATION`. `events` now has 24 columns: `id`, `event_id`, nullable `dataset_version`, `event_type`, `event_time`, `subscriber_id`, `source_token`, `destination_token`, `sim_id`, `device_id`, `network_token`, `location_token`, nullable `latitude`, `longitude`, `duration_seconds`, `call_direction`, `call_status`, `is_international`, `is_roaming`, `message_count`, `auth_outcome`, `scenario_label`, `fraud_label`, and `created_at`. Telecom-specific metadata is optional; tokens and generated coordinates remain synthetic. `dataset_version` references `dataset_versions.version`, which stores dataset kind/status, generator version, seed, target/actual row count, JSON provenance and creation/completion metadata. Existing rows retain a null dataset version.

Feature version `features-v1` retains the original first eleven columns; `features-v2` adds outgoing-call status, international/roaming ratios, rolling SMS and failed-auth counts, mean call duration and time since SIM change (18 total). Training and inference share the as-of-time `FeatureState`; label/scenario/identity tokens are excluded. The model adapter keeps old 11-column artifacts callable and stamps each saved prediction with the model's actual feature version.

The accepted initial dataset is `synthetic-v2-150000-20261119`: 150,000 rows, seed 20261119, generator `synthetic-v2`, with 60,000 label 0 and 90,000 label 1 rows. Event type row counts: AUTHENTICATION 1,250; CALL 96,276; DEVICE_CHANGE 7,992; LOCATION 15,416; NETWORK_ACTIVITY 10,540; OTP_REQUEST 1,250; SIM_CHANGE 11,749; SMS 5,527. These are generator outputs, not a sample of carrier traffic. CSV ingestion requires `event_id,event_type,event_time,subscriber_id`, caps requests at 25 MB/5,000 data rows, validates the complete request before writing, and ignores duplicate event IDs.

## Incremental provenance

Preserve current event, prediction, observation and model records. Planned provenance separates event occurrence/arrival/scoring times, source and replay/run tags, immutable manifest, split and feature derivation, scored risk and classifier policy, model artifact digest and routing/release observation. Keep label source, reviewer, availability and correction references restricted and out of inference features. Existing rows remain readable without invented provenance. Test schema compatibility and backfill with [migration acceptance](TESTING_AND_TRACEABILITY.md#requirement-to-test-matrix).
