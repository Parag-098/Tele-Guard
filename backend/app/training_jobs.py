"""Versioned worker entry points for research and operational training."""

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
import json
import os

from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import DatasetVersion, DemoDataset, Event, MLOpsJob, ModelRun, Prediction, now


def _set_stage(db, job, stage, progress):
    job.result = {**(job.result or {}), "stage": stage}
    job.progress_current = progress
    job.progress_total = 5
    db.commit()


def _cancel_before_publish(db, job, result):
    """Honor a durable stop request at the last safe pre-registry checkpoint."""
    db.refresh(job)
    if job.status != "stopping":
        return False
    job.status = "stopped"
    job.result = {
        "stage": "cancelled_before_publish", "decision": "cancelled",
        "model_version": result["version"],
    }
    job.finished_at = now()
    db.commit()
    return True


def _research_manifests(db, job):
    from app.dataset_manifest import build_snapshot, load_manifest
    from app.longitudinal import TelecomConfig

    output = Path(settings.model_path).parent / "research-datasets"
    revision = os.environ.get("TG_SOURCE_REVISION", "workspace")
    seed = job.arguments["seed"]
    cohorts = {
        "development": ("development", 300_000, 0.02),
        "independent": ("independent", 50_000, 0.02),
        "adaptation": ("drift", 50_000, 0.02),
        "prevalence-005": ("independent", 50_000, 0.005),
        "prevalence-01": ("independent", 50_000, 0.01),
        "prevalence-05": ("independent", 50_000, 0.05),
    }
    manifests = {}
    versions = {}
    for index, (name, (role, count, prevalence)) in enumerate(cohorts.items()):
        config = TelecomConfig(seed=(seed + index) % 2**32, namespace=f"research-{name}-{seed}",
                               population=2000, prevalence=prevalence, role=role)
        path = build_snapshot(output, config, count, revision)
        info = load_manifest(path, verify_parts=True)
        manifests[name], versions[name] = path, info["version"]
        if db.get(DatasetVersion, info["version"]) is None:
            db.add(DatasetVersion(
                version=info["version"], kind=role, generator_version=info["generator_version"],
                seed=config.seed, target_rows=count, row_count=count, status="ready",
                created_by=job.requested_by, completed_at=now(),
                metadata_json={"manifest": str(path), "manifest_sha256": info["manifest_sha256"],
                               "splits": info["splits"], "experimental_prevalence": prevalence},
            ))
        db.commit()
    return manifests, versions


def _frozen_training_input(db, job):
    from app.main import _operational_training_rows, event_dict
    from app.investigations import approved_labels
    from app.runtime_models import SyntheticOutcomeRecord

    dataset_version = job.arguments.get("dataset_version")
    if job.kind == "retrain_version":
        dataset = db.get(DatasetVersion, dataset_version)
        if not dataset or dataset.status != "ready" or dataset.kind == "development":
            raise ValueError("Requested dataset is no longer ready")
        return dataset_version, _operational_training_rows(db, dataset_version)

    version = f"reviewed-{job.id}"
    labels = job.arguments["frozen_outcomes"]
    if not labels or any(type(value) is not int or value not in (0, 1) for value in labels.values()):
        raise ValueError("Frozen feedback contains invalid labels")
    try:
        cutoff = datetime.fromisoformat(str(job.arguments["label_cutoff"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Frozen feedback has no valid label cutoff") from exc
    if cutoff.tzinfo is None:
        raise ValueError("Frozen feedback cutoff must include a timezone")
    cutoff = cutoff.astimezone(timezone.utc)
    rows = db.execute(
        select(Event, Prediction).join(Prediction, Prediction.event_id == Event.event_id)
        .where(Prediction.id.in_([int(identifier) for identifier in labels]))
        .order_by(Event.event_time, Event.event_id)
    ).all()
    if len(rows) != len(labels):
        raise ValueError("A required frozen label record is no longer available")
    approved = approved_labels(db, cutoff)
    event_ids = [event.event_id for event, _ in rows]
    synthetic_outcomes = {
        row.event_id: row for row in db.scalars(select(SyntheticOutcomeRecord).where(
            SyntheticOutcomeRecord.event_id.in_(event_ids)
        )).all()
    }
    events = []
    for event, prediction in rows:
        label = labels[str(prediction.id)]
        if prediction.label_source == "analyst_review":
            verified = approved.get(event.event_id) == label
        elif prediction.label_source == "synthetic-outcome":
            outcome = synthetic_outcomes.get(event.event_id)
            released_at = outcome.released_at if outcome else None
            if released_at and released_at.tzinfo is None:
                released_at = released_at.replace(tzinfo=timezone.utc)
            verified = bool(
                outcome and outcome.actual == label and released_at and
                released_at.astimezone(timezone.utc) <= cutoff
            )
        else:
            verified = False
        if not verified:
            raise ValueError(f"Frozen label for event {event.event_id} is not verified by cutoff")
        events.append({**event_dict(event), "fraud_label": label, "scenario_label": "live-reviewed"})
    manifest_digest = sha256(json.dumps(events, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = db.scalar(select(DemoDataset).where(DemoDataset.version == version))
    if existing:
        metadata = existing.metadata_json or {}
        if (existing.kind != "reviewed" or existing.events != events or
                metadata.get("job_id") != job.id or metadata.get("label_cutoff") != job.arguments["label_cutoff"] or
                metadata.get("rows") != len(events) or metadata.get("sha256") != manifest_digest):
            raise ValueError("Persisted reviewed-label snapshot failed provenance or checksum validation")
        return version, existing.events
    db.add(DemoDataset(
        version=version, kind="reviewed", seed=0, events=events,
        metadata_json={"job_id": job.id, "monitor_window": job.arguments["window"],
                       "label_cutoff": job.arguments["label_cutoff"],
                       "rows": len(events), "sha256": manifest_digest},
    ))
    db.commit()
    return version, events


def process_training_job(job_id):
    from app.main import _record, mlops_compare
    from app.ml import track_training_run, train_model

    with SessionLocal() as db:
        job = db.get(MLOpsJob, job_id)
        if not job:
            raise ValueError("Unknown training job")
        recorded = (job.result or {}).get("training")
        if not recorded:
            _set_stage(db, job, "validating_inputs", 1)
            if job.kind == "research_training":
                from app.experiment import run_experiment

                manifests, versions = _research_manifests(db, job)
                _set_stage(db, job, "fitting_and_evaluating", 2)
                development = manifests.pop("development")
                result = run_experiment(development, manifests, Path(settings.model_path).parent / "research-models")
                dataset = db.get(DatasetVersion, versions["development"])
                dataset.metadata_json = {
                    **dataset.metadata_json, "evaluation_versions": {
                        name: versions[name] for name in manifests
                    },
                }
            else:
                dataset_version, rows = _frozen_training_input(db, job)
                if len(rows) < 50 or {row.get("fraud_label") for row in rows} != {0, 1}:
                    raise ValueError("Training needs at least 50 verified rows with both labels")
                _set_stage(db, job, "fitting_and_evaluating", 2)
                result = train_model(rows=rows, dataset_version=dataset_version)
                result["artifact_sha256"] = sha256(Path(result["artifact_path"]).read_bytes()).hexdigest()
            job.result = {**job.result, "training": result}
            _set_stage(db, job, "publishing", 3)
            if _cancel_before_publish(db, job, result):
                return {"status": "stopped", **job.result}
        else:
            result = recorded

        if sha256(Path(result["artifact_path"]).read_bytes()).hexdigest() != result["artifact_sha256"]:
            raise ValueError("Recorded training artifact failed integrity validation")
        model_run = db.scalar(select(ModelRun).where(ModelRun.version == result["version"]))
        if not model_run:
            if job.kind == "research_training":
                from app.experiment import publish_experiment

                run_id = publish_experiment({**result, "job_id": job.id})
            else:
                run_id = track_training_run({**result, "job_id": job.id})
            model_run = ModelRun(
                version=result["version"], algorithm=result["algorithm"], dataset_version=result["dataset_version"],
                artifact_path=result["artifact_path"], mlflow_run_id=run_id,
                metrics={**result["metrics"], "artifact_sha256": result["artifact_sha256"]},
            )
            db.add(model_run)
            db.flush()
            _record(db, "retraining", model_run.version,
                    {"job_id": job.id, "dataset_version": model_run.dataset_version,
                     "mlflow_run_id": run_id, "status": "registered"}, job.requested_by)
        _set_stage(db, job, "registered", 4)
        try:
            comparison = mlops_compare({"challenger_version": model_run.version}, db,
                                       SimpleNamespace(username=job.requested_by))
            decision = "eligible" if comparison["passed"] else "rejected_by_gates"
        except HTTPException as exc:
            comparison = {"detail": exc.detail}
            decision = "insufficient_evidence"
        job.result = {"stage": "completed", "decision": decision, "model_version": model_run.version,
                      "dataset_version": model_run.dataset_version, "mlflow_run_id": model_run.mlflow_run_id,
                      "comparison": comparison, "metrics": model_run.metrics}
        job.progress_current = 5
        job.status = "succeeded"
        job.finished_at = now()
        db.commit()
        return job.result
