# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
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
    [sys.executable, "-m", "pip", "install", "--retries", "3", "--timeout", "30", *dependencies],
    check=True,
)
PY
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
EXPOSE 8000
CMD ["sh","-c","alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
