# Dataset and live simulator specification

Planned under [TG-02–TG-04](../TeleGuard_AI_Product_Scope_and_Feature_Blueprint.md#mandatory-requirements). The existing event contract is documented in the [data dictionary](DATA_DICTIONARY.md) and enforced by [EventIn](../backend/app/schemas.py). Keep the existing deterministic generator and seed workflow available for historical reproduction.

## Dataset inventory and partitioning

| Dataset | Volume | Role and isolation |
|---|---:|---|
| Historical synthetic-v2-150000-20261119 | 150,000 | Preserve version, prior predictions, events, MLflow linkage and event/policy semantics. Seed 20261119 and a 90k/60k generated fraud/legitimate mix. This is historical reproducibility and regression evidence. |
| Improved development | About 300,000 | Chronological 70/15/15 target, about 210k/45k/45k before exclusions, with a release gate of >100k unique valid labeled training events after cleaning. Fit/calibration/model-selection partitions and boundaries must be explicit. |
| Independent evaluation | About 50,000 | Separate subscriber and coordinated-group namespaces, future or independently fixed periods, held-out profile families and fraud variants, frozen before tuning. Includes difficult legitimate lookalikes. |
| Drift and adaptation | About 50,000 | Ordered reference, change, outcome-arrival and recovery segments. Disjoint from independent evaluation. Reserve a later untouched post-change gate and record transferred labels and exclusion decisions. |
| Live synthetic stream | Grows within configured capacity | Persist run/source tags, checkpoints and counters. Only validated, explicitly labeled slices can be admitted to a fresh immutable training snapshot. |

Approximate volume is configurable. Record deviations with measured runtime, class support and storage rationale. Report event, unique-event, subscriber, episode and label counts independently. Keep existing synthetic-v2 API limits and version behavior. Create the new generator and manifest schema as distinct versions. Store compact fixtures in Git and datasets outside Git.

## Generation and reproducibility

- Model synthetic subscribers with stable identifiers, profile mixtures and histories. Maintain artificial SIM/device associations, contact and network graphs, commuting/roaming, changing devices, hour/day/season patterns, activity bursts and inactivity. Generate CALL metadata, justified SMS counts, SIM/device changes, login outcomes and synthetic location observations. Generate event metadata only.
- Include benign and overlapping fraud variants at both event and episode level. Extend existing six fraud and four benign/lookalike families. Allow ordinary background events within an affected episode, shared devices/networks across legitimate users, bursty business usage, travel and legitimate SIM changes. Encode uncertain cases separately at label time.
- Configure explicit event-level and episode-level prevalence denominators. Evaluate 0.5%, 1%, 2%, and 5% event prevalence as experimental settings, with reported realized proportions, counts per category and randomization method. Rare-case sample support may require multiple seeds or larger dedicated optional stress fixtures.
- Use independent seeded streams for subscriber profiles, scheduling, scenario choice, measurement noise and label delay. Assign opaque deterministic event, subscriber and episode identities with namespaces. Scenario parameters, injection markers, clock sequence IDs, simulator source flags, generation labels and label arrival data remain provenance, outside features. Missingness may be an input only when available at serving and justified.
- Support valid optional missingness, duplicates/retries and separately invalid or corrupt inputs. Bounds violations and malformed rows enter quarantine with reason codes. Gold labels and scenario truth stay in a restricted sidecar or equivalent logical store until release through the outcome pipeline. Repeat generation with the same seed, config and version and reproduce the logical event stream and content hash. Keep environment metadata separate from the canonical content digest.

## Dataset manifests and ingestion

Use PostgreSQL for version and lineage state. Export deterministically ordered, bounded canonical parts to private file storage locally and versioned S3 on AWS when authorized. Start with compressed CSV or Parquet based on measured cost and existing dependency support. Include checksum per part and manifest SHA-256, schema, generation config and code revision, seed, source/rights, normalization version, total and unique records, per-class/event/scenario counts, capture range and ingestion cutoff, known quality issues, split memberships and hashes, approved label cutoff, storage locator/version, run IDs and feature version. Use a staged manifest and publish ready only after verification. Existing DatasetVersion statuses are compatible; model/job state has its own status. A completed version is immutable and superseded by a new version when inputs or labels change.

Validate type-specific fields, UTC timestamps and compatible contract versions. Existing identical retries return original results. Define behavior for identical duplicate rows, conflicting payloads with the same ID, malformed uploads, and worker quarantine with no score for invalid records. Preserve the legacy CSV endpoint’s size limit and atomic failure semantics. Use a staged bounded worker path for larger validated imports and record accepted, duplicate, rejected and quarantined totals. Restrict and redact quarantine previews. Stream input data in chunks, index query shapes and document retention for live events, quarantine, telemetry, datasets and backups. Cleanup must respect protected datasets, incident/audit references, MLflow and retention windows.

Log event time, arrival time and scoring time separately. Persist a canonical UTC ordering and stable tie-break key. Define whether an event enters the online state given a watermark and bounded lateness. Reproduce the same eligibility from the manifest in offline processing. Keep historical predictions immutable. Replays or corrections get new run records and a defined isolation context.

## Persistent virtual network

Store simulator run config and version, seed, logical time, generator checkpoint, event cursor, event idempotency namespace, state transition audit, backlog, resource caps and last heartbeat. Generate artificial events through an adapter into the shared ingestion service, with the same verification, event-time features, scoring, evidence, persistence and monitoring as ordinary input. Development snapshot generation may remain offline, and the lab exercises the live serving path.

| Control | Behavior |
|---|---|
| Start | Validate authorized actor, bounded active runs, profile config and storage headroom. Acquire work lease before producing events. |
| Pause / resume | Commit a batch and cursor before acknowledging pause. Resume from the durable cursor and release any expired ownership. A stopped run may be replayed with a new isolated namespace. |
| Stop | Stop accepting new generation, drain or explicitly cancel queued work according to documented policy, reconcile metrics and release ownership. Preserve committed events and issued labels. |
| Accelerate / replay | Speed changes wall-clock scheduling while retaining logical timestamps, event order, outcome availability and monitor windows. Use replay IDs, fixed seeds and an explicit mode indicator. |
| Backpressure | Bound rate, queue depth, active runs, payload size, retries and disk quota. Pause or slow on high-watermark, recover below low-watermark, and persist reasons/counters. Never silently discard events. |
| Simulate change | Schedule legitimate shifts, unseen fraud variants, prior/prevalence changes, quality failures and delayed labels using the virtual clock. Route valid events to inference and invalid ones to quarantine. Evaluation reports arise from the real scheduled windows. |

A checkpoint persists after committed output or coordinates a retry-safe transaction. Duplicated replay attempts must leave one scoring result, one authorized outcome and no duplicated case evidence. Block concurrent ownership of a simulator run via lease/lock with bounded expiry. Expose lag, queued/scored/quarantined totals, drift cohort, progress, current rate, configured quotas and oldest pending label through the UI. Small demo runs use the same code path and explicit lower sample settings.

## Public data and research

| Source | Access, terms and suitability | Practical decision |
|---|---|---|
| [FraudZen Zenodo v1](https://zenodo.org/records/15706356) | Public synthetic cellular CDR benchmark under CC BY 4.0. The source lists a 133.7 MB ZIP and MD5 395fb1e8c21c0c752ecfbbab8bfe8d54. Attribution, license link and documentation of changes are required for reuse. Its prevalence percentages use incoming international calls as denominator. | Optional separate SIMBox/bypass benchmark. Budget archive plus measured unpacked/staged size. Before importing, inspect sampled headers, time units, roles, IDs, label sidecars and scenarios. Map eligible calls to event-v1 tokens and UTC time, preserve scenario/run groups for holdout, and leave unavailable SMS/SIM-change/auth fields empty. Never coerce the entire mixed-event TeleGuard estimator into a comparable score if its input assumptions differ. |
| [FraudZen simulator repository](https://gitlab.inria.fr/simbox-fraud-mitigation/fraudzen) and [authors’ research](https://doi.org/10.1145/3634737.3657023) | The dataset entry references a C++ simulator and its scholarly provenance. During review the GitLab page returned an access-denied interstitial, so its source license and exact column schema remain unverified. A [separate publisher record](https://entrepot.recherche.data.gouv.fr/dataset.xhtml?persistentId=doi%3A10.57745%2FTAV6PQ) shows a different version, file size, checksum and custom terms. | Verify the exact distribution terms independently before reusing code or archives. Integration is optional and likely requires a dedicated adapter, source-specific feature availability report and comparison within its own scenario splits. |
| [ITU synthetic Nairobi CDR documentation](https://www.itu.int/itu-d/sites/bigdata/wp-content/uploads/sites/60/2026/03/Synthetic-Mobile-Phone-Data-Nairobi-Kenya.pdf) and [tools page](https://www.itu.int/itu-d/sites/bigdata/mobile-phone-data/tools/) | Describes synthetic mobility/usage from 3,000 generated subscribers. Useful for schema inspiration and legitimate mobility variation. Fraud supervision, exact download size and redistribution terms were not verified here. | Reference only initially. Confirm terms and storage, then evaluate a small mobility validation fixture if needed. No default training dependency. |

The documentation audit used publisher metadata and research references. It imported no external archives. Synthetic metrics establish reproducibility and behavior within the modeled distributions. Independent synthetic scenarios stress generalization within that envelope. Real-world performance requires independent operator validation under an approved data and privacy process.

See [E-02 to E-05](TESTING_AND_TRACEABILITY.md#requirement-to-test-matrix) for dataset acceptance and [Scenario Lab](features/scenario-lab.md) for the reproducible cases.

## Implemented snapshot and assessment commands

The v3 [generator](../backend/app/longitudinal.py) supports deterministic seeking by event index for a fixed immutable configuration and phase. Each input is validated by event-v1 without outcome fields. A separate synthetic outcome records scenario, episode, label and logical availability. The manifest writer publishes immutable gzip event and outcome parts with both compressed-file and uncompressed-stream SHA-256 digests. The reader checks strict chronology, unique IDs, split membership and counts, and outcome alignment and availability. The input namespace disjoins evaluation subscribers, events and campaign episodes.

From the backend Python environment, generate and verify the three full-size snapshots plus four optional prevalence sweeps. Replace the placeholder with the source revision used for the experiment. Paths should stay under ignored local storage.

~~~text
python -m app.dataset_manifest --root ../data/raw/incremental-v3 --source-revision SOURCE_REVISION --prevalence-sweep
~~~

The command prints paths for the development, independent, drift and prevalence manifests. Run the assessor using those paths; additional prevalence cohorts repeat the evaluation argument.

~~~text
python -m app.experiment --development DEVELOPMENT_MANIFEST --evaluation independent=INDEPENDENT_MANIFEST --evaluation drift=DRIFT_MANIFEST --output ../artifacts/research
~~~

The development partitions are 70% training, 7.5% calibration, 7.5% selection, and 15% final test. Labels must be available strictly before the subsequent partition boundary to enter training, calibration or selection. The report records excluded late labels and digests of actual eligible manifest positions. Fit three class-weighted classifiers, select by validation PR-AUC and a validation false-positive budget, then assess the untouched test and independent snapshots. The separate sigmoid calibration diagnostic measures potential improvement without changing serving scores. The reported batch classifier timing is separate from end-to-end API performance. Pass the tracking flag against an explicitly configured local MLflow store to register the candidate and attach the assessment and artifact digests. An offline assessment does not activate a model.
