"""Durable, resumable large-dataset generation, scoring and training jobs."""

import time
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db import SessionLocal
from app.config import settings
from app.models import (
    AuditLog,
    DatasetVersion,
    Event,
    MLOpsJob,
    ModelObservation,
    ModelRun,
    Prediction,
    now,
)
from app.synthetic import GENERATOR_VERSION, iter_event_batches

DEFAULT_INITIAL_ROWS = 150_000
MIN_INITIAL_ROWS = 100_000
MAX_INITIAL_ROWS = 300_000
INSERT_BATCH_SIZE = 1500


def dataset_version_for(count: int, seed: int) -> str:
    return f"{GENERATOR_VERSION}-{count}-{seed}"


def queue_job(db, kind: str, requested_by: str, arguments: dict) -> MLOpsJob:
    from uuid import uuid4

    job = MLOpsJob(
        id=str(uuid4()), kind=kind, status="queued", requested_by=requested_by,
        arguments=arguments, progress_current=0, progress_total=int(arguments.get("count", 0)),
    )
    db.add(job)
    db.flush()
    summary = {key: value for key, value in arguments.items()
               if key not in {"example_ids", "frozen_outcomes"}}
    db.add(AuditLog(actor=requested_by, action=f"mlops.job_queued.{kind}", target=job.id,
                    details={"arguments": summary}))
    return job


def process_seed_dataset(job_id: str) -> dict:
    """Generate, persist, batch-score and train a versioned synthetic dataset.

    Each insert/score chunk commits independently. Replaying the deterministic
    event stream after a worker restart skips already persisted event IDs and
    predictions, so the same job resumes without deleting or duplicating data.
    """
    from app.batch_scoring import BatchScoringState
    from app.investigations import attach_predictions
    from app.main import (
        _mlops_state,
        current_scenario_config,
        current_serving_config,
        load_model_run,
        persist_serving_snapshot,
    )
    from app.ml import FeatureState, load_model, train_model, track_training_run
    from app.models import AuthSession  # noqa: F401 - ensures model metadata import order

    with SessionLocal() as db:
        job = db.get(MLOpsJob, job_id)
        if not job or job.kind != "seed_dataset":
            raise ValueError("Seed dataset job not found")
        count = int(job.arguments["count"])
        seed = int(job.arguments["seed"])
        version = dataset_version_for(count, seed)
        dataset = db.get(DatasetVersion, version)
        if not dataset:
            prior_predictions = db.query(Prediction).count()
            dataset = DatasetVersion(
                version=version,
                kind="initial" if job.arguments.get("initial", True) else "scenario",
                generator_version=GENERATOR_VERSION,
                seed=seed,
                target_rows=count,
                row_count=0,
                status="building",
                created_by=job.requested_by,
                metadata_json={
                    "generator_version": GENERATOR_VERSION,
                    "seed": seed,
                    "target_rows": count,
                    "event_prefix": f"tg2_{count}_{seed}",
                    "initial_prediction_count": prior_predictions,
                    "feature_version": "features-v2",
                },
            )
            db.add(dataset)
            db.commit()
        dataset.status = "building"
        job.status = "running"
        job.started_at = job.started_at or now()
        job.progress_total = count
        db.commit()

        active_version = _mlops_state(db)
        active_row = db.query(ModelRun).filter_by(version=active_version).first()
        champion = load_model_run(active_row) if active_row else load_model()
        serving = current_serving_config(db)
        challenger = None
        challenger_version = serving.get("challenger_version")
        if serving.get("mode") in {"shadow", "canary"} and challenger_version:
            challenger_row = db.query(ModelRun).filter_by(version=challenger_version).first()
            if challenger_row:
                try:
                    challenger = load_model_run(challenger_row)
                except Exception as exc:
                    db.add(AuditLog(actor="system", action="model.challenger_failed",
                                    target=challenger_version, reason=str(exc)[:250],
                                    details={"champion_retained": True, "job_id": job_id}))
                    db.commit()
        scenario = current_scenario_config(db)
        feature_state = FeatureState()
        signal_state = BatchScoringState()
        event_prefix = f"tg2_{count}_{seed}"
        completed = 0

        for batch in iter_event_batches(count, seed, INSERT_BATCH_SIZE, event_prefix=event_prefix):
            rows = [event.model_dump(mode="python", exclude={"contract_version"}) for event in batch]
            row_dicts = [event.model_dump(mode="json", exclude={"contract_version"}) for event in batch]
            feature_frame = feature_state.transform(row_dicts)
            scored = signal_state.score(row_dicts, feature_frame, champion, challenger, serving, scenario)

            event_values = [dict(row, dataset_version=version) for row in rows]
            insert_stmt = pg_insert(Event) if db.bind.dialect.name == "postgresql" else sqlite_insert(Event)
            db.execute(insert_stmt.values(event_values).on_conflict_do_nothing(index_elements=[Event.event_id]))
            persisted = db.query(Event).filter(Event.event_id.in_([r["event_id"] for r in row_dicts])).all()
            by_event_id = {event.event_id: event for event in persisted}
            if len(by_event_id) != len(batch) or any(event.dataset_version != version for event in persisted):
                raise RuntimeError("Deterministic event ID collided with data outside this dataset version")

            event_ids = list(by_event_id)
            existing_predictions = {
                event_id for (event_id,) in db.query(Prediction.event_id)
                .filter(Prediction.event_id.in_(event_ids)).all()
            }
            new_predictions = [result for result in scored if result["event_id"] not in existing_predictions]
            if new_predictions:
                prediction_values = [{
                    "event_id": result["event_id"],
                    "model_version": result["model_version"],
                    "feature_version": result["feature_version"],
                    "policy_version": settings.risk_policy_version,
                    "probability": result["probability"],
                    "anomaly_score": result["anomaly_score"],
                    "graph_score": result["graph_score"],
                    "rule_score": result["rule_score"],
                    "risk_score": result["risk_score"],
                    "risk_band": result["risk_band"],
                    "evidence": result["evidence"],
                } for result in new_predictions]
                p_insert = pg_insert(Prediction) if db.bind.dialect.name == "postgresql" else sqlite_insert(Prediction)
                db.execute(p_insert.values(prediction_values).on_conflict_do_nothing(index_elements=[Prediction.event_id]))
                prediction_rows = db.query(Prediction).filter(Prediction.event_id.in_([r["event_id"] for r in new_predictions])).all()
                predictions_by_event = {prediction.event_id: prediction for prediction in prediction_rows}
                observations = []
                for result in new_predictions:
                    prediction = predictions_by_event[result["event_id"]]
                    for model_version, role, probability, threshold in result["observations"]:
                        observations.append({
                            "prediction_id": prediction.id,
                            "model_version": model_version,
                            "serving_role": role,
                            "probability": probability,
                            "predicted_label": int(probability >= threshold),
                        })
                    if serving.get("deployment_id"):
                        observation = next(item for item in result["observations"] if item[0] == prediction.model_version)
                        persist_serving_snapshot(
                            db, by_event_id[prediction.event_id], prediction, serving,
                            result["monitor_features"], observation[3], observation[1], "offline_seed",
                        )
                db.execute((pg_insert(ModelObservation) if db.bind.dialect.name == "postgresql" else sqlite_insert(ModelObservation)).values(observations))
                attach_predictions(db, [(by_event_id[p.event_id], p) for p in prediction_rows], job.requested_by)

            completed += len(batch)
            dataset.row_count = completed
            job.progress_current = completed
            db.commit()
            control = _await_job_control(job_id)
            if control == "stopped":
                dataset.status = "stopped"
                db.commit()
                return {"status": "stopped", "dataset_version": version, "rows": completed}

        dataset.row_count = db.query(Event).filter_by(dataset_version=version).count()
        if dataset.row_count != count:
            raise RuntimeError(f"Expected {count} dataset rows, found {dataset.row_count}")
        dataset.status = "ready"
        dataset.completed_at = now()
        db.commit()

        existing_run = db.query(ModelRun).filter_by(dataset_version=version).order_by(ModelRun.created_at.desc()).first()
        if existing_run and existing_run.mlflow_run_id:
            job.result = {"dataset_version": version, "rows": count,
                          "model_version": existing_run.version, "mlflow_run_id": existing_run.mlflow_run_id,
                          "already_seeded": True}
            job.status = "succeeded"
            job.finished_at = now()
            db.commit()
            return job.result

        training_rows = []
        for event in db.query(Event).filter_by(dataset_version=version).order_by(Event.event_time).yield_per(10_000):
            item = {
                "event_id": event.event_id, "event_type": event.event_type,
                "event_time": event.event_time, "subscriber_id": event.subscriber_id,
                "source_token": event.source_token, "destination_token": event.destination_token,
                "sim_id": event.sim_id, "device_id": event.device_id,
                "network_token": event.network_token, "location_token": event.location_token,
                "latitude": event.latitude, "longitude": event.longitude,
                "duration_seconds": event.duration_seconds, "call_direction": event.call_direction,
                "call_status": event.call_status, "is_international": event.is_international,
                "is_roaming": event.is_roaming, "message_count": event.message_count,
                "auth_outcome": event.auth_outcome, "scenario_label": event.scenario_label,
                "fraud_label": event.fraud_label,
            }
            training_rows.append(item)
        result = train_model(rows=training_rows, dataset_version=version)
        run_id = track_training_run(result)
        model_run = ModelRun(
            version=result["version"], algorithm=result["algorithm"], dataset_version=version,
            metrics=result["metrics"], artifact_path=result["artifact_path"], mlflow_run_id=run_id,
        )
        db.add(model_run)
        db.flush()
        metadata = dict(dataset.metadata_json or {})
        metadata.update({"model_version": result["version"], "mlflow_run_id": run_id,
                         "training_rows": count, "features": result["metrics"].get("dataset_rows")})
        dataset.metadata_json = metadata
        db.add(AuditLog(actor=job.requested_by, action="dataset.initial_seeded", target=version,
                        details={"rows": count, "model_version": result["version"], "mlflow_run_id": run_id}))
        job.result = {"dataset_version": version, "rows": count, "model_version": result["version"],
                      "mlflow_run_id": run_id, "metrics": result["metrics"]}
        job.status = "succeeded"
        job.finished_at = now()
        db.commit()
        return job.result


def _await_job_control(job_id: str) -> str | None:
    while True:
        with SessionLocal() as db:
            job = db.get(MLOpsJob, job_id)
            if not job:
                raise RuntimeError("Job disappeared while processing")
            if job.status == "stopping":
                job.status = "stopped"
                job.finished_at = now()
                db.commit()
                return "stopped"
            if job.status == "paused":
                time.sleep(0.5)
                continue
            if job.status == "queued":
                job.status = "running"
                db.commit()
            return None
