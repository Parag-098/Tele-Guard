# TeleGuard AI

TeleGuard AI is an educational fraud intelligence simulation using synthetic telecom events and identities. It does not connect to carrier infrastructure, inspect real subscriber communications/location, or restrict real subscribers. Risk scores are review signals, not findings of fraud.

## Stack and layout

- `backend/`: FastAPI modular monolith, SQLAlchemy, Alembic, synthetic generation and scikit-learn inference.
- `frontend/`: React + TypeScript + Vite responsive investigation workspace.
- `docker-compose.yml`: PostgreSQL, API, web UI, and private MLflow service. MLflow reuses the API image/version and has persistent backend and artifact volumes.
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
npm run build
```

CI runs backend tests/lint and frontend production build on pushes and pull requests. Docker checks require Docker Compose.

## Local container verification (2026-11-12)

The Compose configuration validates and the PostgreSQL 16 service was started with a new named data volume. Both Alembic migrations were applied to that fresh PostgreSQL database; `alembic current` reported `0002_response_actions (head)`, and `alembic check` reported no new upgrade operations. The API was then run on the host against that PostgreSQL instance. Administrator bootstrap/login, seeded scenario ingestion, persisted predictions with evidence, incident status/assignment and notes, an authorized simulated monitor action, and audit records were exercised. SQL queries confirmed 140 events, 140 predictions with evidence, 121 incidents, 2 notes, 2 simulated actions, and 2 matching action audit rows. A PostgreSQL-backed Auditor login was also denied incident updates and simulated actions (HTTP 403). The frontend Docker image served HTTP 200 on port 5173, and API CORS preflight allowed that origin. Backend tests passed (9 tests), Ruff passed, `npm ci` passed with 0 vulnerabilities, and `npm run build` passed.

The complete application did **not** start wholly in Docker Compose during this verification. An initial API image build failed with a package-index read timeout. A retry spent about 28 minutes downloading dependencies; transfers from `files.pythonhosted.org` stayed around 50–80 KB/s, so it was stopped before the API image completed. A host-side probe also stalled while downloading a new 15.3 MB package from the same package source. This points to slow package-index/CDN egress in this environment, rather than a Docker-only issue.

The API Dockerfile has since been adjusted so the dependency installation layer depends only on pinned `pyproject.toml` requirements, is cached with BuildKit across builds, and is not invalidated by application source changes. Pip's own cache is retained. Compose accepts a `PIP_INDEX_URL` build argument for a reachable PyPI-compatible mirror; direct dependencies remain pinned in `pyproject.toml`. `docker buildx build --check ./backend` reported no Dockerfile warnings. The frontend image also rebuilt successfully, with build context reduced to 143 KB by its new `.dockerignore`. No faster PyPI mirror is configured here, and the revised API Dockerfile has not yet completed an image build. Consequently, API container startup/health, API-container-to-PostgreSQL access, and Compose-backed MLflow training are **not verified**.

Compose now runs MLflow from the same built API image to avoid a separate image/version, persists the tracking SQLite database and artifacts in separate named volumes, enables artifact proxying for API clients, and gates API startup on MLflow health. Its configuration parses, but runtime tracking and training through this Compose service remain **unverified** until the API image build completes. The MLflow tracking port remains internal.

The prior PostgreSQL-backed end-to-end workflow used the host API against Docker PostgreSQL; it is valid evidence for database behavior, but it does not establish full Compose startup. To use a faster package mirror, set a non-credentialed PyPI-compatible URL before building:

```powershell
$env:PIP_INDEX_URL = 'https://your-approved-mirror/simple'
docker compose up --build -d
```

Do not place credentials in this build argument. With the default PyPI source, the same Compose command is `docker compose up --build -d`.

Docker Desktop's per-user CLI directory was missing from `PATH` in the verification shell. On this machine it was run with:

```powershell
$env:Path = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;$env:Path"
```

Then use the standard commands above (`docker compose up --build -d`, followed by `docker compose exec api python -m app.bootstrap`).

## Implemented scope and limitations

Current implementation includes login/JWT, backend role dependencies, synthetic event generation/ingestion, event/prediction persistence, trained model artifact, temporal synthetic evaluation, fitted anomaly detector, NetworkX relationships, rules and evidence-backed risk score, incident queue/notes/status, audit history, reversible simulated action records, dashboard/event/model/scenario/incident detail/admin views, PostgreSQL Compose, Alembic schema versions, and initial MLflow tracking/model registration.

Model promotion gates, model registry approval, shadow/canary routing, rollback, drift detection, delayed-label monitoring, automated retraining approval, real AWS provisioning/deployment, HTTPS, backups, cloud logs/alerts, incident assignment controls, session revocation, and exhaustive administration/settings remain incomplete. Vishing/NLP is deferred. SHAP explanations and advanced location/travel indicators are not implemented. Synthetic performance cannot establish real-world fraud performance.
