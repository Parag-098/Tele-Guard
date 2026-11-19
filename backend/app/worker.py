"""Single-process PostgreSQL-backed worker for durable dataset/model jobs."""

import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import DatasetVersion, MLOpsJob, ServiceHeartbeat, now

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("teleguard.worker")
_heartbeat_stop = threading.Event()
_current_job_id: str | None = None


def _heartbeat_loop():
    while not _heartbeat_stop.is_set():
        with SessionLocal() as db:
            row = db.get(ServiceHeartbeat, "worker")
            if row:
                row.instance_id = socket.gethostname()
                row.status = "healthy"
                row.current_job_id = _current_job_id
                row.updated_at = now()
            else:
                db.add(ServiceHeartbeat(service="worker", instance_id=socket.gethostname(),
                                        status="healthy", current_job_id=_current_job_id,
                                        updated_at=now()))
            db.commit()
        _heartbeat_stop.wait(10)


def execute_job(job_id: str):
    global _current_job_id
    from app.dataset_jobs import process_seed_dataset

    try:
        _current_job_id = job_id
        result = process_seed_dataset(job_id)
        logger.info("job %s finished with %s", job_id, result.get("status", "succeeded"))
        _current_job_id = None
        return result
    except Exception as exc:
        logger.exception("job %s failed", job_id)
        with SessionLocal() as db:
            job = db.get(MLOpsJob, job_id)
            if job:
                job.status = "failed"
                job.error = str(exc)[:2000]
                job.finished_at = now()
                version = job.arguments.get("dataset_version")
                dataset = db.get(DatasetVersion, version) if version else None
                if dataset and dataset.status == "building":
                    dataset.status = "failed"
                db.commit()
        _current_job_id = None
        return None


def claim_job() -> str | None:
    with SessionLocal() as db:
        statement = (
            select(MLOpsJob)
            .where(MLOpsJob.status == "queued")
            .order_by(MLOpsJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = db.execute(statement).scalars().first()
        if not job:
            return None
        job.status = "running"
        job.started_at = job.started_at or now()
        job.updated_at = now()
        db.commit()
    return job.id


def run_worker(poll_seconds: float = 2.0):
    Base.metadata.create_all(bind=engine)
    # Compose runs one worker process. Re-queue jobs interrupted by a container
    # restart; each job is idempotent and replays committed chunks safely.
    with SessionLocal() as db:
        db.query(MLOpsJob).filter(MLOpsJob.status == "running").update(
            {"status": "queued", "updated_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        db.commit()
    _heartbeat_stop.clear()
    threading.Thread(target=_heartbeat_loop, name="worker-heartbeat", daemon=True).start()
    logger.info("TeleGuard job worker started")
    while True:
        job_id = claim_job()
        if job_id:
            execute_job(job_id)
        else:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_worker()
