# Continuous integration and release

`.github/workflows/ci.yml` runs on pushes, pull requests and version tags. CI installs pinned Python dependencies, runs Ruff and pytest, installs the frontend lockfile with `npm ci`, runs `npm audit --audit-level=high` and the production build, validates local and production Compose configuration, and builds API/web images including the same-origin `/api` production frontend.

A `v*` tag enables the release job after all CI jobs pass. The release job expects a protected GitHub `production` environment and these environment/repository variables:

- `AWS_ROLE_ARN`: IAM role trusted for GitHub OIDC restricted to this repo/environment.
- `AWS_REGION`: normally `ap-south-1`.
- `ECR_REGISTRY`: account registry hostname, without repository or tag.
- `EC2_INSTANCE_ID`: prepared SSM-managed instance.

It builds API/web images tagged with the full commit SHA, pushes them to ECR, then uses SSM Run Command to invoke `/opt/teleguard/deploy-release.sh`. No long-lived AWS access key secret is used. The host must already have Docker, Compose, SSM Agent, IAM instance profile, protected `.env.production`, `docker-compose.prod.yml`, Caddy config and deploy script in place. The production environment can require a human reviewer before this job runs.

No GitHub-hosted CI/CD execution has been observed from the current workspace because no authenticated GitHub CLI/session or repository settings access was available. A configured workflow is not evidence of a passed hosted run or successful AWS deployment.

## Local PowerShell checks

```powershell
Set-Location backend
py -3.11 -m pip install -e '.[dev]'
py -3.11 -m ruff check app tests
py -3.11 -m pytest tests -q
Set-Location ..\frontend
npm ci
npm audit --audit-level=high
npm run build
Set-Location ..
$env:POSTGRES_PASSWORD = 'local-ci-password'
$env:TG_SECRET_KEY = 'local-ci-secret-key-at-least-32-bytes'
docker compose config --quiet
docker compose build api web
docker compose --env-file .env.production.example -f docker-compose.prod.yml config --quiet
```

## Incremental release gates

The current workflow is a baseline. Add an exact-image PostgreSQL/Playwright smoke and preserved-version migration test before shipping. Include application/worker readiness and verified model artifact, preserve a versioned release manifest for host files plus images, and validate IaC offline in CI. Keep the production environment guarded and record hosted Actions, ECR and SSM results only from authorized runs. See the [incremental AWS gates](../../docs/AWS_DEPLOYMENT_GUIDE.md#incremental-aws-readiness-and-verification-tg-13).
