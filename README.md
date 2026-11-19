# TeleGuard AI

TeleGuard AI is an educational fraud intelligence simulation using synthetic telecom events and identities. It does not connect to carrier infrastructure, inspect real subscriber communications/location, or restrict real subscribers. Risk scores are review signals, not findings of fraud.

## Stack and layout

- `backend/`: FastAPI modular monolith, SQLAlchemy, Alembic, synthetic generation and scikit-learn inference.
- `frontend/`: React + TypeScript + Vite responsive investigation workspace.
- `docker-compose.yml`: local PostgreSQL, API, web UI, and private MLflow service with local persistent volumes.
- `docker-compose.prod.yml`: prepared single-EC2 production stack with Caddy HTTPS, private PostgreSQL and MLflow, bind-mounted EBS data, S3-backed MLflow artifacts, and CloudWatch logs.
- `backend/app/schemas/event-contract.json`: canonical `event-v1` event contract.

## Local development (Docker)

Install Docker Desktop / Docker Engine and Compose. Python 3.12 and Node 22 are used by the containers. Then run from the repository root:

```powershell
Copy-Item .env.example .env
# Edit .env and set unique local POSTGRES_PASSWORD, TG_SECRET_KEY, and TG_ADMIN_PASSWORD (12+ chars).
docker compose up --build -d
docker compose exec api python -m app.bootstrap
```

Open the UI at <http://localhost:5173>, API docs at <http://localhost:8000/docs>, and health at <http://localhost:8000/api/health>. The MLflow service is internal to Compose and has no host port published. PostgreSQL data, model artifacts, and MLflow metadata persist in named local volumes.

Generate a demo dataset from the UI's **Run scenario** button or call:

```powershell
$token = (Invoke-RestMethod -Method Post http://localhost:8000/api/auth/login -ContentType 'application/json' -Body '{"username":"admin","password":"YOUR_LOCAL_ADMIN_PASSWORD"}').access_token
Invoke-RestMethod -Method Post http://localhost:8000/api/scenarios/generate -Headers @{Authorization="Bearer $token"} -ContentType 'application/json' -Body '{"count":140,"seed":42}'
```

The generator is reproducible for the same seed and event count. Ingestion is idempotent by `event_id`. Every event is persisted and scored by a trained Random Forest plus separate anomaly, graph and rule signals; persisted evidence includes the component values. Incident changes, notes, simulated actions and model training runs are persisted. Use the **Train candidate** button or `docker compose exec api python -m app.train` to train/evaluate and record a model run. Metrics describe synthetic generated data only.

The **MLOps lifecycle** page runs the versioned baseline → seeded feature drift → PSI report → real retraining → same-holdout challenger evaluation → administrator decision workflow. Candidates do not automatically replace the active model. Administrators can approve/reject and roll back to previously approved versions. Individual saved predictions can be explained on demand with SHAP for the exact recorded model and feature schema. Location/travel evidence, administrator-controlled shadow/canary serving, and delayed-label model monitoring are integrated into scoring and lifecycle workflows. See [docs/MLOPS_DEMO_GUIDE.md](docs/MLOPS_DEMO_GUIDE.md) and [docs/COLLEGE_PRESENTATION_GUIDE.md](docs/COLLEGE_PRESENTATION_GUIDE.md).

### Create the initial operational dataset

Sign in as an Administrator, open **Data observatory**, and choose **Generate 150,000 events**. This queues a durable worker job (supported range 100,000–300,000, fixed seed recorded per version). The worker generates reproducible batches, stores normalized rows in PostgreSQL `events` with a `dataset_version`, computes as-of-time features, persists predictions/observations/incidents, then trains and tracks three supervised candidates against a chronological 70/15/15 split. Dataset, model and MLflow run IDs are persisted. Existing active models remain active until the normal challenger comparison and approval workflow promotes a candidate. Job progress and pause/resume/stop are available in Data observatory; worker heartbeat appears under **Live monitoring**.

The initial dataset has 150,000 rows in `events` (24 current columns); version metadata records generator version, seed, target/count, status and model/run provenance. It is synthetic and has a 60/40 fraud/legitimate class mix by generator design. For CSV ingestion, use **CSV event ingestion** in Data observatory or `POST /api/events/upload-csv`: UTF-8 CSV, required columns `event_id,event_type,event_time,subscriber_id`, maximum 25 MB and 5,000 rows per request. The entire file is validated before any row is committed. See [the implementation and local acceptance report](docs/IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md) for evidence and detailed schema counts.

Data observatory reports PostgreSQL event/prediction/incident totals, dataset versions, event type/label distributions and missing-value rates. Live monitoring polls API, PostgreSQL, worker heartbeat and MLflow health plus persisted service metrics. These values come from operational records, not UI fixtures.

## Backend development without Docker

Requires Python 3.12. From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
$env:TG_DATABASE_URL='sqlite:///./teleguard.db'
$env:TG_SECRET_KEY='local-only-replace-this-secret'
alembic upgrade head
python -m app.bootstrap
uvicorn app.main:app --reload
```

When using local development, set `TG_ADMIN_USERNAME` and `TG_ADMIN_PASSWORD` before `python -m app.bootstrap`; the password must be at least 12 characters. Do not use example values outside an isolated local demo.

## Frontend development

Requires Node 22+. From `frontend/`:

```powershell
npm install
$env:VITE_API_URL='http://localhost:8000/api'
npm run dev
npm run build
```

## Checks

```powershell
cd backend
python -m pytest
python -m ruff check app tests
cd ..\frontend
npm audit --audit-level=high
npm run build
```

CI runs backend tests/lint, frontend dependency audit/build, and Compose/container builds on pushes and pull requests. Docker checks require Docker Compose.

## Docker build and Compose verification (2026-11-13)

The original sqlalchemy==2.0.39 (from versions: none) error was **not** caused by an invalid pin, Python version, or CPU architecture. The host Python 3.11 download succeeded; a fresh python:3.12-slim Linux/amd64 container also downloaded the same pin from https://pypi.org/simple; and the full API image later resolved and installed SQLAlchemy 2.0.39 and all other declared dependencies. The original failing HTTP response was not captured, so its precise transient error cannot be reconstructed. The evidence points to intermittent/slow access through Docker Desktop's package-network path: Docker Engine reported http.docker.internal:3128 for HTTP and HTTPS proxy, while Windows WinHTTP reported direct access. During the uncached API build, large PyPI wheels transferred at roughly 50–200 KB/s and dependency installation took 1,919 seconds. This was a throughput/network-path problem, not a dependency workaround.

The Dockerfile keeps the dependency layer independent of application source: it copies pyproject.toml, installs every declared pinned dependency with pip retries and timeout, retains /root/.cache/pip through a BuildKit cache mount, then copies application and migration source. PIP_INDEX_URL remains an optional Compose build argument. The full uncached command docker compose --progress plain build --no-cache api completed successfully. A following docker compose up -d --build reused the completed API dependency layer from cache and built the frontend image successfully. No dependency pin was changed or package removed. docker buildx build --check ./backend reported no warnings.

For networks where Docker Desktop's default PyPI path is too slow or intermittently unavailable, configure Docker Desktop's outbound proxy to reach PyPI reliably, or use an organization-approved PyPI-compatible mirror through the existing build argument. Example (mirror URL is environment-specific and was not tested here):

~~~powershell
$env:PIP_INDEX_URL = 'https://<approved-mirror>/simple'
docker compose build api
~~~

Do not put mirror credentials in the build argument. Keep TLS verification enabled. The build was verified against the public PyPI URL; the alternate mirror is a documented option, not a verified requirement.

The complete Compose stack started successfully. PostgreSQL 16 passed pg_isready; the API's internal /api/health returned {"status":"ok","database":"connected","contract_version":"event-v1"}; a SQLAlchemy SELECT 1 from inside the API container returned 1; MLflow /health returned OK; and the frontend returned HTTP 200 at port 5173. The API container applied both Alembic migrations to a newly created PostgreSQL volume.

The initial administrator was bootstrapped from local .env settings and logged in. A real model training request through POST /api/models/train completed and returned a persisted model version and synthetic holdout metrics. MLflow at http://mlflow:5000 recorded experiment teleguard-synthetic-fraud, a run, the joblib artifact, sklearn model artifacts, and registry version 1 for TeleGuardSyntheticFraud. The private tracking service used the Compose URI and did not publish port 5000 to the host. After docker compose up -d --force-recreate mlflow, the run and registry version were still queryable; its SQLite metadata database remained on the named volume; six artifact files totaling 4,224,903 bytes remained on the artifact volume; and the API-side MLflow client downloaded the persisted 3,016,650-byte joblib artifact.

Checks rerun on 2026-11-13: py -3.11 -m pytest -q passed (9 tests), py -3.11 -m ruff check app tests passed, and npm run build passed (Vite reports the existing 628 KB JavaScript chunk-size warning). The Dockerfile static check passed. The GitHub Actions workflow was not dispatched to GitHub in this verification; local tests/builds are not evidence of a remote Actions run.

In this PowerShell session the Docker Desktop CLI was not on PATH. Ensure Docker Desktop's CLI directory is on PATH, or use a shell where the docker command is available.

The usual developer start sequence remains docker compose up --build -d, then docker compose exec api python -m app.bootstrap for the first administrator.

## AWS deployment readiness

AWS deployment has **not** been performed. It is blocked on AWS account/role and domain access. The production Compose file, Caddy configuration, ECR/SSM GitHub Actions release job, operations guide and cost assumptions are prepared in [docs/AWS_DEPLOYMENT_GUIDE.md](docs/AWS_DEPLOYMENT_GUIDE.md). Do not consider those files evidence of a live URL, HTTPS certificate, AWS persistence, S3 artifact retrieval, or hosted CI/CD success. See [docs/FINAL_RELEASE_CHECKLIST.md](docs/FINAL_RELEASE_CHECKLIST.md) for verified and pending gates.
## Implemented scope and limitations

Current implementation includes login/JWT, backend role dependencies, synthetic event generation/ingestion, event/prediction persistence, trained model artifact, temporal synthetic evaluation, fitted anomaly detector, NetworkX relationships, rules and evidence-backed risk score, incident queue/notes/status, audit history, reversible simulated action records, dashboard/event/model/scenario/incident detail/admin views, PostgreSQL Compose, Alembic schema versions, and initial MLflow tracking/model registration.

Implemented lifecycle controls include persisted PSI drift reports, real approval-gated retraining, challenger evaluation, model approval/rejection, rollback, shadow/canary routing, delayed-label monitoring, and browser-verified MLOps views. Scenario scoring stores location/travel findings with each prediction and displays them in investigation detail. Per-prediction SHAP and incident resolution provenance/search are implemented and tested. The AWS deployment is prepared but not live; see the deployment guide and release checklist. Vishing/NLP is deferred. Synthetic performance cannot establish real-world fraud performance.

The 2026-11-19 acceptance pass additionally verifies the 150,000-row operational dataset, actual PostgreSQL persistence and model lifecycle promotion/rollback. Historical checkpoint statements in this README and older reports are superseded by [IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md](docs/IMPLEMENTATION_AND_LOCAL_ACCEPTANCE_2026-11-19.md), which includes the measured model results, test evidence, limitations and AWS **NO-GO** decision. AWS resources were not created.
