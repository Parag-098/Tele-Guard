# Testing, traceability and acceptance

This is the acceptance contract for the [incremental release](../TeleGuard_AI_Product_Scope_and_Feature_Blueprint.md#mandatory-requirements) and [execution plan](../TeleGuard_AI_Vibe_Coding_Execution_Plan.md#16-execution-plan-for-the-incremental-release-2026-11-28). E-nn identifies the acceptance evidence, TG-nn the requirement and TG-Tnn the phase. The table preserves the original gate definitions; its initial pending status is historical and is superseded row by row by the latest [local acceptance evidence](LOCAL_ACCEPTANCE_2026-11-28.md) and the checkpoint in [TASKS.md](../TASKS.md). Unverified portions remain open. [Historical evidence](IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md).

## Requirement-to-test matrix

| Evidence | Requirements / tasks | Procedure and passing result | Failures to record |
|---|---|---|---|
| E-01 Preserve baseline | TG-01 / TG-T00 | Record exact revision, tool versions and current test results. On an isolated preserved copy, verify legacy users/roles, sessions, CSV and single ingestion, seed/job controls, event/explorer/graph/SHAP, incident actions and reversal, historic model/MLflow artifacts, demo route behavior, counts and audit invariants. Rerun applicable legacy tests after each affected slice. | Missing legacy records, changed risk evidence, removed working UI/API, or regression with unsupported compatibility. |
| E-02 Dataset scale and reproducibility | TG-02 / TG-T02 | In disposable local PostgreSQL, query group-by dataset, exact distinct event IDs and label/split counts. Generate the development/independent/drift fixtures with manifests and artifact hashes, repeat a canonical seed regeneration and compare digests. Verify >100,000 eligible unique train events, 150,000 preserved historical rows, chronological split order and separate independent scenario/groups. Record realized prevalence and positive support. | Count below minimum, label or identity overlap across disjoint scopes, invalid/changed digest, or unverifiable provenance. |
| E-03 Simulator and lab | TG-03 / TG-T02, TG-T07 | Browser and API start/pause/resume/stop/replay; kill the worker after a committed checkpoint in isolated Compose. Restart and compare expected event sequence and DB totals. Inject load above cap and invalid scheduled outcomes, confirm bounded backlog, observable lag, valid scorer use and quarantine. Outcome joins must wait for the logical release time. | Gaps, repeats, early outcomes, uncontrolled growth, fabricated pipeline state or failing recovery. |
| E-04 Ingestion, data quality and scoring parity | TG-01, TG-04 / TG-T01, TG-T02 | Send same fixture via single/CSV/worker/replay, including late, tied-time, cold-start and >200 prior rows. Verify equal valid features/decisions under the same recorded context, and no future/label feature. Retry and concurrently submit identical/conflicting IDs. Assert atomic invalid CSV, one event/prediction, defined conflict outcome and quarantine for corrupt worker input. | Different policy attribution or unexplained scoring/ordering divergence, non-atomic import, duplicate or scored invalid data. |
| E-05 ML and explainability | TG-05 / TG-T03 | Run model comparison with lineage, chronological seals, independent scenario and rare-prevalence reports. Verify leakage sentinel rejection, validation-only calibration/threshold selection, deterministic split hashes, metric support and approved feature scalers. Compare stored probability/feature vector and SHAP additivity for supported artifacts; show explicit unavailable cases. Capture fit runtime/memory and end-to-end latency separately. | Leaked features, optimistic holdout reuse, false score/SHAP claims, no runtime provenance or inadequate class support. |
| E-06 Release safety | TG-06 / TG-T01, TG-T05 | Replay ≥10,000 distinct subscribers with a common ID prefix. At 10% the deterministic bucket share should be within ±2 percentage points and stable across restart and pathways; test 0%, 100%, nested ramps, repeat events and fallback instrumentation. Test offline, shadow, actual canary, failed/stale/wrong-policy/racing approvals, concurrent rollback and corrupted artifacts. Prove resulting active version and same-policy metric interpretation. | Shadow changes primary output, actual/assigned confusion, train→promote bypass, stale evidence accepted, drifted state or mismatched artifact admitted. |
| E-07 Drift, quality and delayed labels | TG-07 / TG-T04 | Replay clean control, harmless feature shift, unseen-pattern degradation and quality failure through identical pipeline. Validate PSI bins and constant/missing features, late windows, label cutoffs/support. Verify two breaches yield one incident by default, retry deduplication, recovery and no degradation claim from unlabeled shift. Assert quarantined data is excluded. | Healthy drift false alert on sealed control, duplicate actions, mislabeled failure class, unsupported degradation or scheduling gaps hidden. |
| E-08 Automatic training | TG-08 / TG-T05 | Trigger eligible labeled window without a manual script, then query job stages, artifact registry and nonpromoted candidate. Replay same trigger concurrently, simulate failure before/after registry write, resume and prove single canonical run/evidence. Test cooldowns, cancellation, unavailable MLflow, bounded retries and version eligibility. | Duplicate active jobs, scheduled/API request blocks on training, unchecked input, untraceable artifact or implicit promotion. |
| E-09 Feedback | TG-09 / TG-T06 | Test role checks, reviewer identity and timestamps, conflict/correction/audit, deliberate uncertainty, randomized low-risk coverage, explicit confirmation and outcome delay. Rebuild snapshot from approved labels and verify withheld/inconclusive/unauthorized outcomes are excluded. | Data/label corruption, lost provenance, accidental binary label or selection bias concealed. |
| E-10 Investigation and impact | TG-10 / TG-T06 | Replay the same labeled stream through old and new policies. Related episode events converge within configured bounds and unrelated events sharing a single weak entity stay separate. Verify reversible merge/reopen/actions, audit and explained links. Report cases/1,000 events, duplicate alerts, episode detection, false positives, precision at budget, time to first alert and resolution times. Require workload reduction on designated duplicate fixture with no loss of scripted episode coverage there; report trade-offs on larger replay. | Evidence lost, uncontrolled merge, unapproved simulated action, inflated impact or missed scripted comparison. |
| E-11 UX and authorization | TG-11, TG-12 / TG-T07, TG-T08 | Build/lint and Playwright; log in as Administrator, Fraud Analyst, Investigator, ML Engineer and Auditor using isolated fixture accounts. Verify routing, live UI, action constraints, keyboard navigation/focus, desktop/mobile views, charts/table summaries, loading/empty/error/partial/denied and sensitive field redaction. Assert backend permissions independently of UI checks. | Broken legacy entry point, disallowed mutation, screen exposing secret/infra details, invented value or inaccessible blocked control. |
| E-12 Operations and recovery | TG-01, TG-12 / TG-T00, TG-T08 | Validate Alembic fresh and in-place upgrade; run clean and upgraded local PostgreSQL Compose; health at dependency outages; controlled worker crash, restart and graceful shutdown; backup database plus MLflow metadata/artifact linkage, restore separately and cold-load known approved artifact. Recheck stored IDs, counts, model/feature version and sample scores. | Data loss, unscoped access, false readiness, failed restore, wrong artifact, deadlock or silent background failures. |
| E-13 Offline AWS readiness | TG-13 / TG-T08 | Build exact release artifacts, scan dependencies and images, validate production Compose and IaC offline, validate IAM scope/ports, prove image/data rollback in disposable production-shape staging, provide signed-off sizing estimate/runbook and owner prerequisites. Confirm logs/alarms are configured and rendered without real resources. | Unpinned release, public DB/MLflow, undeclared costs, incomplete or destructive migration procedure or static check sold as a live deployment. |
| E-14 Integrated local demo | TG-14 / TG-T07, TG-T09 | Run the full [college demo](COLLEGE_PRESENTATION_GUIDE.md#incremental-release-demonstration) from clean stack and preserve command log/recording, dataset/monitor/job/release IDs and recovery evidence. Prove a rejected gate, successful safe promotion and service/data recovery within declared demo bounds. | Manual fake labels bypass policy, fake metric/progress, missing link in lifecycle or unavailable restore/rollout test. |
| E-15 Authorized live cloud smoke | TG-13, TG-14 / TG-T09 | After explicit approval, record GitHub run and ECR digests, public Caddy HTTPS, scoped IAM and private services. Repeat role/scoring/outcome/monitoring/canary checks, trigger a test alarm, verify S3 artifact integrity and backup/restore, exercise deployment and model rollbacks. | Missing owner authorization, missing live result, overwritten volumes/artifacts, unverified budget/alarms or exposure. |

## Commands and test environment

Run existing checks from the designated directories on isolated data. The current pytest fixture uses a disposable SQLite database, so add separate PostgreSQL integration and recovery tests for locks, leases, migrations and concurrency.

| Location | Command / procedure | Expected outcome and evidence |
|---|---|---|
| Repo root | git status --short; git diff --check | Capture pre-existing untracked work and whitespace status. Commit review is owner workflow; preserve Git history. |
| Backend | python -m pip install -e ".[dev]"; python -m ruff check app tests; python -m pytest -q | Use supported Python and isolated environment. Record actual counts and failing cases, warnings and test version. |
| Backend | alembic upgrade head; alembic current | Run against fresh and historical-copy disposable DBs with configured DSN; record revisions and before/after row invariants. |
| Frontend | npm ci; npm run lint; npm run build; npm audit --audit-level=high; npm run test:e2e | Use the lockfile, Node version in CI, correct Playwright browser install and an isolated running stack. Verify whether new frontend test harness commands are needed in T07. Keep historical warnings distinct from new failures. |
| Repo root | docker compose config --quiet; docker compose build; docker compose up -d --wait; docker compose ps | Use a dedicated test project and isolated ports/volumes. Probe authenticated and public endpoints, dependency failure modes and process restart safely. Do not remove original volumes. |
| Repo root | docker compose --env-file .env.production.example -f docker-compose.prod.yml config --quiet | Config parse and binding inspection using placeholders. This proves no live deployment property. |
| Future IaC directory | terraform fmt -check; terraform init -backend=false; terraform validate | If Terraform is selected, validate templates without credentials or resource creation. Any authenticated plan or apply follows the authorized cloud runbook. |
| Local load lab | Run a versioned replay/load command to be implemented under TG-T08, capture latency/throughput and host resource measurements | Start at 10 events/s steady for 10 minutes and a bounded burst at 2×; record p50/p95, ingest-to-score lag, error rate, queue, peak RAM and exact hardware. Target p95 API scoring ≤500 ms steady, <1% unexpected failures, all valid committed IDs accounted for and backlog drains within 5 min after burst. Freeze or justify revised targets before acceptance using actual capacity tests. |
| Isolated restore | Execute the scripted PostgreSQL plus MLflow/S3-compatible recovery runbook | Record restore duration, last recoverable event timestamp, manifest checksums and scoring output. Proposed demo objectives are ≤24h recovery point with daily backups and ≤60 minutes restoration on declared hardware, subject to measured validation. |

Commands separated by punctuation are individual steps. Do not run writable checks against the historical workspace volume. Use safe fault injection in disposable services. Where tooling or credentials prevent a run, record the exact blocker and evidence still required.

## Evidence template and gate closure

Store dated, redacted evidence under the existing reporting structure. Include requirement and task IDs, Git revision, dependency versions, hardware, logical time settings, command and exit result, dataset and split digest, job/model/MLflow IDs, role and scenario used, expected/observed results, links to test output or sanitized screenshots, failures, remediation and rerun. Never use screenshots as sole proof of the database or registry. Evidence must remain traceable to persisted records. Close checked items in [TASKS.md](../TASKS.md) and the [release checklist](FINAL_RELEASE_CHECKLIST.md) only after passes. Keep unmet cloud items distinct from local completion.

# Original scope preservation crosswalk

| Original scope and open commitments | Retained acceptance |
|---|---|
| Blueprint modules A/B and original P0 ingestion/generator/feature engineering, large versioned datasets, temporal validation, telecom event schema and documented roles | TG-01–TG-05, E-01–E-05. Legacy seed/import and normalized rows remain regression fixtures. |
| Modules C/D/F and original P0/P1 fraud inference, explainable unified risk, graph/rule/anomaly evidence, and SHAP | TG-04, TG-05, TG-10, TG-11, E-04/E-05/E-10/E-11. Explainability resolves saved artifact provenance and retention. |
| Modules E/H/I and original investigations, UI/dashboard, notes and resolution, Operator/Viewer personas, authorization, rate limiting and reversible responses | TG-01, TG-09–TG-12, E-01/E-09–E-12. Role permissions are mapped explicitly and protected with backend and browser checks. |
| Module J and original P0/P1 MLflow, model quality gates, feedback, streaming dashboard, same-stage evaluation, drift, retraining and rollback | TG-03, TG-06–TG-09, TG-11, E-03/E-06–E-09/E-11. Existing small demo and new monitored replay both remain traceable. |
| Original local runtime, CI/CD, real AWS HTTPS, persistent data and artifact recovery, role checks and demo documentation | TG-01, TG-12–TG-14, E-01/E-12–E-15. Completion stages keep live AWS pending independently from local work. |
| Original module G and P2 transcript/LLM, graph-learning, streaming/orchestration and cloud upgrades | TG-O2 and TG-O3 preserve conditional optional scope. TG-O1 adds an optional external benchmark. Optional work cannot replace mandatory acceptance. |

Read the preserved [original blueprint](../TeleGuard_AI_Product_Scope_and_Feature_Blueprint.md) and [original execution sections](../TeleGuard_AI_Vibe_Coding_Execution_Plan.md) alongside this crosswalk. When an open prior requirement lacks a direct test, track it as a required fix before claiming completion.

## Latest gate disposition — 2026-11-28

This addendum maps the current results to E-01–E-15; it supplements the acceptance contract above and retains each exact pass boundary in the [local acceptance report](LOCAL_ACCEPTANCE_2026-11-28.md#integrated-local-lifecycle-and-final-acceptance--2026-11-28).

| Gate | Latest disposition | Evidence pointer |
|---|---|---|
| E-01 | Pass, local | Python production-runtime suite 48 passed/1 PostgreSQL-only skip; Ruff; frontend lint/build/audit; diff check. |
| E-02 | Pass, synthetic size/provenance | 150,000 persisted rows; 300,000 development manifest; 209,285 eligible training rows; checksum validation. |
| E-03 | Pass, synthetic simulator | Run `2fb27f5e-1f6d-46b0-8840-de2364e0143c`: cursor 1000, 997 scored, 3 quarantined, 997 outcomes released. |
| E-04 | Pass, tested contract | Sealed manifest worker/replay, corrupt manifest/config quarantine, late/tied/>200 history parity, retry/conflict and PostgreSQL race. |
| E-05 | Pass, synthetic experiment | Time split, independent cohorts, leakage and fit/holdout checks, model explanation tied to persisted feature vector. |
| E-06 | Pass, local release controls | Real PostgreSQL racing approval/rollback; measured 20% canary; approval, shadow, rollback and fallback evidence. |
| E-07 | Pass, local monitoring contract | Scheduled windows, supported labels, two-breach handling, quarantine/quality distinction and dedup checks. |
| E-08 | Pass, local worker lifecycle | Durable automatic trigger; registry-write exit-86 recovery; retry/backoff, outage, cancellation, cooldown/dedup and no self-promotion. |
| E-09 | Pass, governed synthetic labels | Reviewer provenance, correction/conflict, uncertainty, low-risk sampling, frozen 480-label snapshot and invalid/tampered exclusion. |
| E-10 | Pass with adverse trade-offs reported | Paired 300 replay and latest 10,000-event measured workload/episode/false-positive/miss/unknown/resolution summary. |
| E-11 | Pass for exercised routes/personas | 9 Playwright cases, five roles, backend denial/forged UI role, mobile/keyboard and partial failure/redaction. |
| E-12 | Pass, local fresh/recovery matrix | `0010_investigations` fresh head, preserved `0008` upgrade, exact release restart, isolated PostgreSQL/MLflow restore and restored inference. |
| E-13 | Partial, keep open | Compose, Terraform and exact release smoke pass; exact-image API scanner finding and exact web full-language scan still need closure. No scan suppression. |
| E-14 | Pass, synthetic local lifecycle | Persisted simulation→investigation/feedback→supported retraining→candidate gates→human approval→shadow/canary→rollback→recovery. |
| E-15 | External and unauthorized | No AWS or hosted-GitHub operations were run; owner authorization remains absent by explicit scope. |

Do not describe synthetic metrics as real telecom performance. A local gate can pass while the separately scoped live cloud gate remains not run.

### Superseding regression note — 2026-11-28

The current supported-runtime backend result is **51 passed, 1 PostgreSQL-only skip**; Ruff passes. This supersedes the 48-pass result in the earlier checkpoint. The new route guard inventory covers deferred routers and all explicit `allow(...)` role sets. E-11 is locally accepted for the complete route declaration matrix and tested UX paths. E-13 remains partial while exact web-image Trivy output is being collected; see the latest acceptance addendum.

## Final locally achievable gate disposition — 2026-11-28

This addendum supersedes the earlier E-13 partial status above. The full per-gate evidence and limitations are in the [final local acceptance report](LOCAL_ACCEPTANCE_2026-11-28.md#final-local-closure-and-offline-readiness--2026-11-28). Local E-01–E-14 acceptance is complete. E-15 remains external and unauthorized.

| Gate | Final status | Evidence summary |
|---|---|---|
| E-01 | Pass | Python 3.12 51 passed / 1 PostgreSQL-only skip, separately covered PostgreSQL race paths, Ruff, frontend checks. |
| E-02 | Pass, synthetic | 150,000 historical rows; 300,000 manifest events; 209,285 eligible rows; integrity checks. |
| E-03 | Pass, synthetic | Continuous simulator, actual persisted inference, invalid-event quarantine, delayed labels and scheduled monitoring. |
| E-04 | Pass | Same-manifest worker/replay; corruption; late/tied context; >200-history parity; atomic conflict and idempotency coverage. |
| E-05 | Pass, synthetic | Leakage-safe temporal and independent evaluation, candidate comparison and artifact/explanation provenance. |
| E-06 | Pass locally | PostgreSQL transaction races, fresh approval evidence, measured canary, fallback and rollback. |
| E-07 | Pass locally | Scheduled windows, drift-vs-quality controls, delayed-label support, dedup and retraining trigger. |
| E-08 | Pass locally | Worker crash after registry write and canonical recovery; retry/cooldown/dedup, cancellation and outage evidence. |
| E-09 | Pass locally | Governed reviewer feedback, frozen snapshot checksums/provenance, invalid/unverified label exclusions. |
| E-10 | Pass with transparent trade-offs | Paired 10,000-event incident replay, alert/workload reduction, episode misses, false positives, unlabeled cases and resolution time. |
| E-11 | Pass for exercised matrix | Complete route guard inventory, five roles, backend denials, UI forgery rejection, keyboard/mobile and partial failure/redaction paths. |
| E-12 | Pass locally | Fresh and `0008`→`0010` migration, restarted services, cold MLflow artifact and isolated PostgreSQL/MLflow restore with inference. |
| E-13 | Pass for offline AWS readiness | Exact release images scanned, API Scout discrepancy retained/source-reconciled, production Compose/Terraform/IAM/port checks, release smoke and region estimate. API Scout reports 2 medium and 28 low alongside the reconciled metadata high; findings remain visible. |
| E-14 | Pass, synthetic local | Persisted simulator-to-review-to-retraining-to-human-release-to-rollback-to-recovery lifecycle. |
| E-15 | Not run | Requires explicit AWS authorization and external hosted GitHub/account/domain access. No live deployment is claimed. |

The exact final-image records are [web Trivy JSON](evidence/web-trivy-0.76.2-2026-11-28-final.json), [API Scout reconciliation](evidence/api-scout-discrepancy-2026-11-28.json), [release smoke](evidence/release-smoke-2026-11-28-final-webhardening.json), and [regional cost estimate](evidence/aws-offline-cost-estimate-2026-11-28.json).
