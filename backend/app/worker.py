"""Single-process PostgreSQL-backed worker for durable dataset/model jobs."""

import logging
import os
import signal
import socket
import threading
import time
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.db import Base, SessionLocal, engine
from app.models import DatasetVersion, MLOpsJob, ServiceHeartbeat, now

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("teleguard.worker")
_heartbeat_stop = threading.Event()
_current_job_id: str | None = None


def _heartbeat_loop():
    while not _heartbeat_stop.is_set():
        try:
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
        except OperationalError:
            logger.warning("Worker heartbeat could not reach PostgreSQL")
        _heartbeat_stop.wait(10)


def _scheduled_operations():
    from app.monitoring import refresh_monitoring
    from app.simulator import advance_simulator, settle_finished_runs

    next_monitor = 0.0
    while not _heartbeat_stop.is_set():
        try:
            with SessionLocal() as db:
                clock = now()
                advance_simulator(db, clock)
                settle_finished_runs(db, clock)
                db.commit()
            if time.monotonic() >= next_monitor:
                next_monitor = time.monotonic() + 15
                with SessionLocal() as db:
                    refresh_monitoring(db, now())
                    db.commit()
        except Exception:
            logger.exception("Continuous operations iteration failed")
        _heartbeat_stop.wait(1)


def execute_job(job_id: str):
    global _current_job_id
    from app.dataset_jobs import process_seed_dataset
    from app.training_jobs import process_training_job

    try:
        _current_job_id = job_id
        with SessionLocal() as db:
            job = db.get(MLOpsJob, job_id)
            if not job:
                return None
            kind = job.kind
        if kind == "seed_dataset":
            result = process_seed_dataset(job_id)
        elif kind in {"retrain_live", "retrain_version", "research_training"}:
            result = process_training_job(job_id)
        else:
            raise ValueError(f"Unsupported job kind {kind}")
        logger.info("job %s finished with %s", job_id, result.get("status", "succeeded"))
        return result
    except Exception as exc:
        logger.exception("job %s failed", job_id)
        with SessionLocal() as db:
            job = db.get(MLOpsJob, job_id)
            if job:
                job.error = str(exc)[:2000]
                attempts = int(job.arguments.get("attempts", 0)) + 1
                job.arguments = {**job.arguments, "attempts": attempts}
                retry = job.kind != "seed_dataset" and not isinstance(exc, ValueError) and attempts < 3
                job.status = "queued" if retry else "failed"
                job.updated_at = now() + timedelta(seconds=30 * 2 ** (attempts - 1) if retry else 0)
                job.finished_at = None if retry else now()
                version = job.arguments.get("dataset_version")
                dataset = db.get(DatasetVersion, version) if version else None
                if dataset and dataset.status == "building":
                    dataset.status = "failed"
                db.commit()
        return None
    finally:
        _current_job_id = None


def claim_job() -> str | None:
    with SessionLocal() as db:
        statement = (
            select(MLOpsJob)
            .where(MLOpsJob.status == "queued", MLOpsJob.updated_at <= now())
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


def requeue_interrupted_jobs(db) -> int:
    """Make jobs left running by a lost worker eligible for the same worker again."""
    recovered = db.query(MLOpsJob).filter(MLOpsJob.status == "running").update(
        {"status": "queued", "updated_at": now()}, synchronize_session=False,
    )
    db.commit()
    return recovered


def run_worker(poll_seconds: float = 2.0):
    _heartbeat_stop.clear()
    signal.signal(signal.SIGTERM, lambda *_: _heartbeat_stop.set())
    signal.signal(signal.SIGINT, lambda *_: _heartbeat_stop.set())
    while not _heartbeat_stop.is_set():
        try:
            with engine.connect() as connection:
                if connection.dialect.name == "postgresql" and not connection.scalar(
                    text("SELECT pg_try_advisory_lock(1712527020)")
                ):
                    logger.info("Waiting for the active TeleGuard worker")
                    _heartbeat_stop.wait(5)
                    continue
                _run_owned_worker(connection, poll_seconds)
                return
        except OperationalError:
            logger.warning("Waiting for PostgreSQL before starting or recovering the worker")
            _heartbeat_stop.wait(5)


def _run_owned_worker(connection, poll_seconds):
    from app import investigations, runtime_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        requeue_interrupted_jobs(db)
    threads = (
        threading.Thread(target=_heartbeat_loop, name="worker-heartbeat", daemon=True),
        threading.Thread(target=_scheduled_operations, name="worker-scheduler", daemon=True),
    )
    for thread in threads:
        thread.start()
    logger.info("TeleGuard job worker started")
    try:
        while not _heartbeat_stop.is_set():
            if connection.dialect.name == "postgresql":
                connection.execute(text("SELECT 1"))
                connection.commit()
            job_id = claim_job()
            if job_id:
                execute_job(job_id)
            else:
                _heartbeat_stop.wait(poll_seconds)
    finally:
        _heartbeat_stop.set()
        for thread in threads:
            thread.join(timeout=5)
        if connection.dialect.name == "postgresql" and not connection.invalidated:
            connection.execute(text("SELECT pg_advisory_unlock(1712527020)"))
            connection.commit()
        _heartbeat_stop.clear()


if __name__ == "__main__":
    run_worker()
