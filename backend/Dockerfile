# syntax=docker/dockerfile:1.7
FROM python:3.12-slim@sha256:5b5fe805d367f8f5a359ded6ab2652b7f9a206453ee6ee789c0045ba6ec15016
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN --mount=type=cache,target=/root/.cache/pip \
    PIP_INDEX_URL="$PIP_INDEX_URL" python - <<'PY'
import subprocess
import sys
import tomllib
from pathlib import Path

dependencies = tomllib.loads(Path("pyproject.toml").read_text())["project"]["dependencies"]
subprocess.run(
    [sys.executable, "-m", "pip", "install", "--upgrade", "pip==26.3"],
    check=True,
)
subprocess.run(
    [sys.executable, "-m", "pip", "install", "--upgrade", "setuptools==84.2.1"],
    check=True,
)
subprocess.run(
    [sys.executable, "-m", "pip", "install", "--retries", "3", "--timeout", "30", *dependencies],
    check=True,
)
PY
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
EXPOSE 8000
CMD ["sh","-c","alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${TG_API_WORKERS:-1}"]
