# Final Release Checklist

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
