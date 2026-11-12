# AGENTS.md — Instructions for every coding agent

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
