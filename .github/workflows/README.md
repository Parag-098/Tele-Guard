# Continuous integration

`ci.yml` runs for pushes and pull requests. It installs the pinned backend dependencies, runs Ruff and pytest, installs the frontend lockfile with `npm ci`, and runs the production build. A container job validates the Compose file and builds the API/MLflow image and frontend image; MLflow uses the same pinned application image and a different command.

The workflow has read-only repository permissions and does not deploy. The Docker build job supplies disposable values for required Compose interpolation only; it does not start services or publish images.

To reproduce the CI checks locally from PowerShell:

```powershell
Set-Location backend
py -3.12 -m pip install -e '.[dev]'
py -3.12 -m ruff check app tests
py -3.12 -m pytest
Set-Location ..\frontend
npm ci
npm run build
Set-Location ..
$env:POSTGRES_PASSWORD = 'ci-only-database-password'
$env:TG_SECRET_KEY = 'ci-only-test-secret'
docker compose config --quiet
docker compose build api web
```
