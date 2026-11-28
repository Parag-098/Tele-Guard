# AGENTS.md — Instructions for every coding agent

> Use the [incremental specification](TeleGuard_AI_Product_Scope_and_Feature_Blueprint.md#14-requirements-for-the-incremental-release-2026-11-28) and [execution plan](TeleGuard_AI_Vibe_Coding_Execution_Plan.md#16-execution-plan-for-the-incremental-release-2026-11-28) together. Current task and authorization determine whether the agent may implement or only plan.

## Before coding
Read `README.md`, `TeleGuard_AI_Product_Scope_and_Feature_Blueprint.md`, `TeleGuard_AI_Vibe_Coding_Execution_Plan.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `TASKS.md`, and the relevant feature spec. Inspect the actual repository; do not assume previous chat context describes current code.

## Working method
1. Work on one assigned task only.
2. First report repository state, proposed plan, files to change, risks, and tests.
3. Implement the smallest complete vertical slice.
4. Add tests for normal, invalid, boundary, persistence, and authorization cases as relevant.
5. Run checks and report exact commands and results.
6. Inspect `git diff`; remove unrelated changes and secrets.
7. Update specs, API contracts, and task status when behaviour changes.
8. Do not claim success for checks that were not run.

## Project boundaries
- This is an educational telecom fraud simulation using synthetic identities, events, numbers, devices, SIMs, IP/network tokens and locations.
- Never connect to carrier infrastructure, intercept communications, access private real SMS/OTP/audio/GPS data, or block real subscribers/numbers.
- Predictions are risk signals, not proof. Shared device/network/location alone is not proof of fraud.
- LLMs must not autonomously block or restrict entities. Simulated actions require backend authorization and audit records.
- Synthetic-data results must never be represented as real-world performance.

## Engineering guardrails
- Start as a modular monolith; do not create microservices by default.
- Keep training separate from online inference; version datasets, features, models and scoring policy.
- Use time-aware splits and prevent target/future leakage. Do not use scenario IDs or labels as features.
- Keep supervised probability, anomaly score, graph signals, rule results and final risk score distinct.
- Do not add Kafka, Kubernetes, Airflow, Redis, a graph database or GNN without a documented need and decision.
- Use migrations; PostgreSQL is the deployed application database.
- Enforce RBAC on the backend, not just in the UI.
- Never commit credentials, `.env`, keys, datasets, model binaries, caches or logs.
- Use least-privilege AWS IAM; do not expose databases or internal admin/monitoring ports publicly.
- Do not hardcode demo predictions in the real inference path.

## Completion report
State: implemented behaviour; changed files; commands run and results; acceptance criteria met/not met; known limitations; next smallest task. If a check could not run, explain why.

## Incremental implementation and preservation

- Preserve working UI/API behavior, datasets, models, MLflow experiments, migration history, case/audit records and original docs. Historical evidence is append-only. Mark outdated instructions as historical or superseded and link the replacement. Do not silently reduce any mandatory requirement or erase deferrals.
- Work on one dependency-safe vertical slice at a time within the authorized end-to-end plan. Persist status and evidence in [TASKS.md](TASKS.md). Continue autonomously to the next unlocked task after validation, incorporating newly discovered required fixes from the [audit](docs/REPOSITORY_AUDIT.md).
- Read prior tracker and diff after a restart or context compaction. Execute tests and review failures; record actual outcomes and leave unsupported gates open. Use [requirement-level evidence](docs/TESTING_AND_TRACEABILITY.md) and preserve environments with isolated test data and Docker projects.
- Use real pipelines for demos, with original behavior covered by regression tests. Retain current components unless an evidenced defect or dependency requires a change. Document decisions, migration steps and backward compatibility.
- Keep development and documentation authorization distinct from cloud authorization. Do not provision, spend, deploy, change live settings or perform destructive operations without the required approval. Exhaust the available locally authorized work while waiting on external access. Never require the owner to implement features manually.

## Final autonomous completion checkpoint — 2026-11-28

The locally authorized E-01–E-14 implementation and acceptance work is complete. Use [TASKS.md](TASKS.md#final-locally-achievable-completion-checkpoint--2026-11-28), the [traceability matrix](docs/TESTING_AND_TRACEABILITY.md#final-locally-achievable-gate-disposition--2026-11-28) and [final local acceptance report](docs/LOCAL_ACCEPTANCE_2026-11-28.md#final-local-closure-and-offline-readiness--2026-11-28) as the current status. Preserve historical findings and raw scan evidence. The API Scout BOM location mismatch is source-reconciled without suppression; the 2 medium and 28 low counts remain disclosed. E-15 hosted GitHub/AWS work remains external and unauthorized. Never infer live cloud behavior from offline validation.
