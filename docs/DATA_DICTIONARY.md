# Canonical Event Contract — `event-v1`

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
