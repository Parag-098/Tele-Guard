# Final Release Checklist

> The checked items below represent historical Phase 2/3 evidence. The [incremental acceptance checklist](#incremental-acceptance-checklist-2026-11-28) is intentionally pending until the new release is implemented and tested.

Statuses reflect observed evidence as of 2026-11-16. AWS items remain unverified because no account/CLI session, domain or live resources were available.

## Local application and MLOps

- [x] Compose development baseline, PostgreSQL, API, frontend, MLflow and model artifacts previously verified.
- [x] Synthetic MLOps baseline, drift report, actual retraining, MLflow run, challenger comparison, approval, rollback and inference selection previously exercised end to end.
- [x] SHAP additivity, feature mapping and schema rejection covered by backend tests in this session.
- [x] Incident resolution provenance, assignment validation, search/filter, audit history and auditor authorization covered by backend tests.
- [x] Browser click-through using Playwright: admin login, persisted MLOps sections, SHAP rendering, investigation filters, Auditor-disabled training and hidden approval control. Zero runtime/API request errors.
- [x] Production Compose configuration and internal port exposure validated locally; API and production-path frontend images built.
- [ ] Verify the production composition on an AWS deployment host.

## Security and reliability

- [x] Backend RBAC, session revocation and audit behavior have existing tests.
- [x] Database remains internal-only in the production Compose configuration.
- [x] MLflow remains internal-only; API docs disabled in production settings.
- [x] Production configuration expects IAM roles, protected runtime secrets, restricted CORS and TLS reverse proxy.
- [ ] Confirm AWS IAM, security group, TLS, secret rotation and S3 policies in a real account.
- [ ] Create PostgreSQL backup and perform isolated restore against deployed services.

## Tests and CI

- [x] Backend pytest: `15 passed` after SHAP, investigation and artifact recovery changes.
- [x] Ruff: passed.
- [x] Frontend production build: passed; existing large-bundle warning remains.
- [x] `npm audit --audit-level=high`: passed with zero vulnerabilities after final UI edits.
- [x] Production Compose config validation and API/web image builds completed locally.
- [ ] GitHub-hosted Actions run: blocked by missing authenticated GitHub CLI/session.
- [ ] OIDC-based ECR/SSM release workflow execution: awaits GitHub settings and AWS role configuration.

## AWS and operations

- [ ] AWS EC2 deployment, ECR images, S3 artifacts, persistent data, public URL and health checks.
- [ ] Domain DNS and valid HTTPS certificate.
- [ ] CloudWatch logs and EC2 monitoring.
- [ ] MLflow artifact fetch from the deployed S3-backed service.
- [ ] PostgreSQL backup and isolated restore.
- [ ] Confirm actual monthly estimate in AWS Pricing Calculator and set billing alerts.
- [x] Local college demonstration UI smoke test; [ ] AWS release smoke test.

No item marked pending should be described as deployed or verified. See [AWS deployment](AWS_DEPLOYMENT_GUIDE.md), [production operations](PRODUCTION_OPERATIONS.md), [MLOps demo](MLOPS_DEMO_GUIDE.md), and [college presentation](COLLEGE_PRESENTATION_GUIDE.md).

## Current gate (2026-11-19)

The full local acceptance is recorded in [IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md](IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md). It confirms 150,000 persisted operational rows and the local model lifecycle. **AWS release decision: NO-GO.** The exact final API image rebuild, ECR, EC2/IAM, S3 artifact recovery, public HTTPS, CloudWatch, billing/backup/restore, and GitHub-hosted OIDC acceptance remain pending; no AWS resources were created.

## Incremental acceptance checklist 2026-11-28

Use the [test matrix](TESTING_AND_TRACEABILITY.md#requirement-to-test-matrix) and [master specification](../TeleGuard_AI_Product_Scope_and_Feature_Blueprint.md#completion-and-evidence) for the four independent completion states.

- [ ] Local E-01/E-12: clean exact-source Compose, existing behavior regression, migration against preserved copy, restart and isolated DB/MLflow artifact restore.
- [ ] Local E-02–E-05: >100k unique train rows, historical dataset preserved, independent datasets/checksums, real simulator controls and case outcomes, parity and honest evaluation.
- [ ] Local E-06–E-08: consistent policy, subscriber canary, safe promotion/rollback, scheduled served-traffic metrics, delayed-label support, automatically queued restartable jobs.
- [ ] Local E-09–E-11: adjudication and case correlation, replay impact, authorized professional frontend and negative paths.
- [ ] Local E-14: an actual integrated end-to-end demonstration recorded with lineage and recovery evidence.
- [ ] AWS ready E-13: pinned exact release images, production Compose, IaC and CI checks, cost/role/HTTPS inputs, release and rollback runbooks.
- [ ] AWS verified E-15: owner authorization, hosted ECR/SSM deployment and HTTPS, private services, verified alarm, storage persistence, model artifact recovery, backup restore and rollback with recorded live results.

Keep [TASKS.md](../TASKS.md#incremental-release-progress-2026-11-28) in sync. A failed or unverified gate remains open even if older reports contain a passed preliminary check.

## Final local release checkpoint — 2026-11-28

- [x] Local regression, application/browser checks, 150k+ persisted dataset and >100k eligible training requirement.
- [x] Continuous simulator, drift/quality monitoring, governed feedback, durable automatic retraining, candidate evaluation, human-controlled model release, canary and rollback.
- [x] Production-shaped local exact-image smoke, API/worker restart, checksummed app+MLflow backup, isolated PostgreSQL restore and restored authenticated inference.
- [x] Local Compose/Terraform static validation and bounded load evidence.
- [x] E-13 offline readiness: exact API Scout location discrepancy reconciled without suppressing the finding; full exact final web-image Trivy scan completed with vulnerability/misconfiguration/secret scanners and current databases; local Compose, Terraform, IAM/port review, rollback/recovery smoke and region-specific calculator estimate recorded. API Scout's residual 2 medium and 28 low findings remain disclosed. See [final scanner and readiness evidence](LOCAL_ACCEPTANCE_2026-11-28.md#final-local-closure-and-offline-readiness--2026-11-28).
- [ ] E-15 live AWS and hosted GitHub/OIDC acceptance. AWS deployment is not authorized and has not been attempted.

See the [latest gate disposition](TESTING_AND_TRACEABILITY.md#final-locally-achievable-gate-disposition--2026-11-28). No item above implies AWS deployment.
