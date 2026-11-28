from datetime import datetime, timedelta, timezone
import pytest
import joblib
import mlflow
from sqlalchemy import select

from app.db import SessionLocal
from app.decision_policy import assigned_canary
from app.models import DatasetVersion, DemoDataset, Event, MLOpsJob, MLOpsRecord, ModelRun, Prediction, now
from app.monitoring import compare_to_baseline, refresh_monitoring
from app.runtime_models import MonitorWindow, QuarantinedEvent, ServedSnapshot, SimulatorRun, SyntheticOutcomeRecord
from app.simulator import advance_simulator
from app.worker import requeue_interrupted_jobs


def test_full_subscriber_canary_bucket_is_stable_and_measurable():
    keys = [f"same-prefix-subscriber-{index:05}" for index in range(10_000)]
    stage = {"mode": "canary", "experiment_id": "candidate-a", "canary_percent": 10}
    small = {key for key in keys if assigned_canary(key, stage)}
    assert 800 <= len(small) <= 1200
    assert small == {key for key in reversed(keys) if assigned_canary(key, stage)}
    assert all(assigned_canary(key, {**stage, "canary_percent": 20}) for key in small)
    assert not any(assigned_canary(key, {**stage, "canary_percent": 0}) for key in keys)
    assert all(assigned_canary(key, {**stage, "canary_percent": 100}) for key in keys)


def test_worker_requeues_interrupted_job_without_losing_checkpoint(client):
    with SessionLocal() as db:
        running = MLOpsJob(
            id="interrupted-job", kind="retrain_live", status="running", requested_by="system",
            arguments={"attempts": 1, "window": "window-1", "frozen_outcomes": {"17": 1}},
            result={"stage": "publishing", "training": {"version": "candidate-checkpoint"}},
            progress_current=3, progress_total=5,
        )
        finished = MLOpsJob(
            id="finished-job", kind="retrain_live", status="succeeded", requested_by="admin",
            arguments={"window": "window-done"}, progress_current=5, progress_total=5,
        )
        db.add_all([running, finished])
        db.commit()

        assert requeue_interrupted_jobs(db) == 1
        db.expire_all()
        recovered = db.get(MLOpsJob, "interrupted-job")
        assert recovered.status == "queued"
        assert recovered.arguments == {"attempts": 1, "window": "window-1", "frozen_outcomes": {"17": 1}}
        assert recovered.result == {"stage": "publishing", "training": {"version": "candidate-checkpoint"}}
        assert recovered.progress_current == 3
        assert db.get(MLOpsJob, "finished-job").status == "succeeded"


def test_worker_bounds_transient_mlflow_outage_retries(client, monkeypatch):
    from app import training_jobs
    from app.worker import execute_job

    with SessionLocal() as db:
        job = MLOpsJob(
            id="mlflow-outage-retry", kind="retrain_live", status="queued",
            requested_by="admin", arguments={"attempts": 0},
        )
        db.add(job)
        db.commit()

    def unavailable(_job_id):
        raise ConnectionError("simulated MLflow outage")

    monkeypatch.setattr(training_jobs, "process_training_job", unavailable)
    for attempt in (1, 2):
        assert execute_job("mlflow-outage-retry") is None
        with SessionLocal() as db:
            job = db.get(MLOpsJob, "mlflow-outage-retry")
            assert job.status == "queued"
            assert job.arguments["attempts"] == attempt
            assert "simulated MLflow outage" in job.error
            retry_at = job.updated_at
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            assert retry_at >= now() + timedelta(seconds=30 * 2 ** (attempt - 1) - 2)

    assert execute_job("mlflow-outage-retry") is None
    with SessionLocal() as db:
        job = db.get(MLOpsJob, "mlflow-outage-retry")
        assert job.status == "failed"
        assert job.arguments["attempts"] == 3
        assert job.finished_at is not None


def test_running_training_cancellation_is_honored_before_registry_publish(client, token, tmp_path, monkeypatch):
    from app import experiment, training_jobs

    dataset_version = "cancel-before-publish-dataset"
    job_id = "cancel-before-publish-job"
    artifact = tmp_path / "candidate.joblib"
    artifact.write_bytes(b"synthetic artifact fixture")
    result = {
        "version": "cancelled-candidate", "dataset_version": dataset_version,
        "algorithm": "test-fixture", "artifact_path": str(artifact),
        "artifact_sha256": __import__("hashlib").sha256(artifact.read_bytes()).hexdigest(),
        "metrics": {},
    }
    with SessionLocal() as db:
        db.add(DatasetVersion(
            version=dataset_version, kind="development", generator_version="test",
            seed=1, target_rows=100, row_count=100, status="ready", metadata_json={},
        ))
        db.add(MLOpsJob(
            id=job_id, kind="research_training", status="running", requested_by="admin",
            arguments={"seed": 1}, result={"stage": "fitting_and_evaluating"},
        ))
        db.commit()

    stopped = client.post(
        f"/api/jobs/{job_id}/control", headers={"Authorization": f"Bearer {token}"},
        json={"action": "stop"},
    )
    assert stopped.status_code == 200 and stopped.json()["status"] == "stopping"

    monkeypatch.setattr(training_jobs, "_research_manifests", lambda *_: (
        {"development": tmp_path / "development.manifest"}, {"development": dataset_version},
    ))

    def finish_fit_without_registry(*_args):
        with SessionLocal() as db:
            assert db.get(MLOpsJob, job_id).status == "stopping"
        return result

    monkeypatch.setattr(experiment, "run_experiment", finish_fit_without_registry)
    monkeypatch.setattr(experiment, "publish_experiment", lambda *_: pytest.fail("cancelled job published"))
    completed = training_jobs.process_training_job(job_id)
    assert completed == {
        "status": "stopped", "stage": "cancelled_before_publish",
        "decision": "cancelled", "model_version": "cancelled-candidate",
    }
    with SessionLocal() as db:
        job = db.get(MLOpsJob, job_id)
        assert job.status == "stopped" and job.finished_at is not None
        assert db.scalar(select(ModelRun).where(ModelRun.version == result["version"])) is None


def test_training_retry_reuses_finished_mlflow_run_for_job(tmp_path, monkeypatch):
    original_uri = mlflow.get_tracking_uri()
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking_uri)
    mlflow.set_tracking_uri(tracking_uri)
    try:
        mlflow.set_experiment("teleguard-synthetic-fraud")
        with mlflow.start_run(run_name="already-published") as run:
            mlflow.set_tag("teleguard_job_id", "registry-write-before-crash")
            canonical_run_id = run.info.run_id
        artifact_path = tmp_path / "artifact.joblib"
        joblib.dump({"model": "trusted-test-fixture"}, artifact_path)

        from app.ml import track_training_run

        found_run_id = track_training_run({
            "artifact_path": str(artifact_path), "job_id": "registry-write-before-crash",
            "version": "retry-candidate", "algorithm": "test", "metrics": {},
        })
        runs = mlflow.search_runs(
            filter_string="tags.teleguard_job_id = 'registry-write-before-crash' and attributes.status = 'FINISHED'",
            max_results=10,
        )
        assert found_run_id == canonical_run_id
        assert len(runs) == 1
    finally:
        mlflow.set_tracking_uri(original_uri)


def test_frozen_psi_bins_keep_missing_values_visible():
    baseline = compare_to_baseline([0.0] * 100)
    equal = compare_to_baseline([0.0] * 100, baseline)
    shifted = compare_to_baseline([-20.0] * 75 + [None] * 25, baseline)
    assert equal["psi"] == 0.0
    assert shifted["cuts"] == baseline["cuts"]
    assert shifted["current_counts"][-1] == 25
    assert shifted["psi"] >= 0.20


def test_virtual_network_persists_cursor_quarantine_delayed_labels_and_monitoring(client, token, monkeypatch):
    headers = {"Authorization": f"Bearer {token}"}
    started = client.post("/api/simulator/runs", headers=headers, json={
        "seed": 41, "population": 24, "rate": 20, "event_limit": 80,
        "logical_interval_seconds": 180, "monitor_minimum": 10,
        "drift_at": 40, "invalidate_every": 10,
    })
    assert started.status_code == 202
    run_id = started.json()["id"]
    from fastapi import HTTPException
    from app import main as app_main

    original_ingest = app_main.ingest_event
    injected = False

    def ingest_with_one_conflict(db, event, actor, model, **kwargs):
        nonlocal injected
        if not injected:
            injected = True
            raise HTTPException(409, "injected event ID conflict")
        return original_ingest(db, event, actor, model, **kwargs)

    monkeypatch.setattr(app_main, "ingest_event", ingest_with_one_conflict)
    clock = datetime.now(timezone.utc) + timedelta(seconds=1)
    with SessionLocal() as db:
        advance_simulator(db, clock)
        db.commit()
        assert db.get(SimulatorRun, run_id).cursor == 20
        assert db.query(Event).count() == 19
        assert db.query(Prediction).count() == 19
        assert db.query(SyntheticOutcomeRecord).filter_by(run_id=run_id).count() == 19
        assert db.query(QuarantinedEvent).filter_by(source=run_id, error_code="event_id_conflict").count() == 1
        assert db.query(Event).filter(Event.fraud_label.is_not(None)).count() == 0
        assert db.scalars(select(SyntheticOutcomeRecord).where(SyntheticOutcomeRecord.released_at.is_(None))).first()
    assert client.post(f"/api/simulator/runs/{run_id}/pause", headers=headers).status_code == 200
    with SessionLocal() as db:
        advance_simulator(db, clock + timedelta(seconds=5))
        assert db.get(SimulatorRun, run_id).cursor == 20
    assert client.post(f"/api/simulator/runs/{run_id}/resume", headers=headers).status_code == 200
    for step in (10, 12, 14):
        with SessionLocal() as db:
            advance_simulator(db, clock + timedelta(seconds=step))
            db.commit()
    with SessionLocal() as db:
        run = db.get(SimulatorRun, run_id)
        assert run.status == "completed" and run.cursor == 80 and run.quarantined == 5
        assert db.query(Prediction).count() == 75
        assert db.query(Prediction).filter_by(label_source="synthetic-outcome").count() > 0
        refresh_monitoring(db, clock)
        db.commit()
        initial_count = db.query(MonitorWindow).count()
        assert initial_count > 0
        refresh_monitoring(db, clock)
        db.commit()
        assert db.query(MonitorWindow).count() == initial_count
    windows = client.get(f"/api/monitoring/windows?cohort={run_id}", headers=headers)
    assert windows.status_code == 200
    assert any(item["status"] == "data_quality" for item in windows.json())


def test_corrupt_scheduled_simulator_configuration_is_quarantined(client, token):
    response = client.post("/api/simulator/runs", headers={"Authorization": f"Bearer {token}"}, json={
        "seed": 9021, "population": 24, "rate": 5, "event_limit": 20,
    })
    assert response.status_code == 202
    run_id = response.json()["id"]
    with SessionLocal() as db:
        run = db.get(SimulatorRun, run_id)
        run.configuration = {**run.configuration, "rate": 0}
        db.commit()
        advance_simulator(db, now() + timedelta(seconds=1))
        db.commit()
        run = db.get(SimulatorRun, run_id)
        assert run.status == "failed" and run.cursor == 0 and run.quarantined == 1
        record = db.query(QuarantinedEvent).filter_by(
            source=run_id, error_code="invalid_run_configuration"
        ).one()
        assert record.external_id is None
        assert db.query(Event).filter(Event.event_id.like(f"{run_id}%")).count() == 0


def test_supported_delayed_label_degradation_trains_registered_challenger(client):
    """Only a supported drop with viable chronological data reaches worker training."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_id = "supported-degradation-window"
    with SessionLocal() as db:
        db.add(SimulatorRun(
            id=run_id, created_by="test", status="completed",
            configuration={"monitor_minimum": 20}, cursor=480, quarantined=0,
            created_at=start, next_tick_at=start,
        ))
        for index in range(480):
            window = index // 60
            within_window = index % 60
            label = int(within_window < 10)
            event_id = f"degradation-{index:03d}"
            event_time = start + timedelta(hours=window, minutes=within_window)
            probability = 0.9 if label and window == 0 else 0.1
            event = Event(
                event_id=event_id, event_type="CALL", event_time=event_time,
                subscriber_id=f"subscriber-{index:03d}", fraud_label=label,
            )
            prediction = Prediction(
                event_id=event_id, model_version="degradation-model",
                feature_version="features-test", policy_version="risk-test",
                probability=probability, risk_score=probability, risk_band="low",
                anomaly_score=0, graph_score=0, rule_score=0,
                ground_truth_label=label, label_source="synthetic-outcome",
                label_received_at=event_time + timedelta(minutes=1),
            )
            db.add_all([event, prediction])
            db.flush()
            db.add(ServedSnapshot(
                prediction_id=prediction.id, cohort=run_id, event_type="CALL",
                observed_at=event_time, release=None, assigned_role="champion",
                actual_role="champion", classifier_threshold=0.5,
                values={"duration_seconds": index, "call_count_1h": index % 10,
                        "failed_auth_1h": 0, "subscriber_event_count": 1},
            ))
            db.add(SyntheticOutcomeRecord(
                event_id=event_id, run_id=run_id, actual=label, scenario="synthetic-test",
                available_at=event_time + timedelta(minutes=1),
                released_at=event_time + timedelta(minutes=1),
            ))
        ineligible_prediction_ids = set()
        ineligible_rows = (
            ("manual", 0, None, None),
            ("analyst_review", 1, None, None),
            ("synthetic-outcome", 1, 0, "released"),
            ("synthetic-outcome", 0, 0, "withheld"),
            ("inconclusive", None, None, None),
            (None, None, None, None),
        )
        for index, (source, label, outcome, release_state) in enumerate(ineligible_rows):
            event_id = f"degradation-ineligible-{index}"
            event_time = start + timedelta(hours=7, minutes=50 + index)
            event = Event(
                event_id=event_id, event_type="CALL", event_time=event_time,
                subscriber_id=f"ineligible-subscriber-{index}", fraud_label=label,
            )
            prediction = Prediction(
                event_id=event_id, model_version="degradation-model",
                feature_version="features-test", policy_version="risk-test",
                probability=0.9 if label == 0 else 0.1, risk_score=0.5, risk_band="medium",
                anomaly_score=0, graph_score=0, rule_score=0,
                ground_truth_label=label, label_source=source,
                label_received_at=event_time + timedelta(minutes=1) if label is not None else None,
            )
            db.add_all([event, prediction])
            db.flush()
            ineligible_prediction_ids.add(prediction.id)
            db.add(ServedSnapshot(
                prediction_id=prediction.id, cohort=run_id, event_type="CALL",
                observed_at=event_time, release=None, assigned_role="champion",
                actual_role="champion", classifier_threshold=0.5,
                values={"duration_seconds": index, "call_count_1h": 0,
                        "failed_auth_1h": 0, "subscriber_event_count": 1},
            ))
            if outcome is not None:
                db.add(SyntheticOutcomeRecord(
                    event_id=event_id, run_id=run_id, actual=outcome, scenario="synthetic-test",
                    available_at=event_time + timedelta(minutes=1),
                    released_at=(event_time + timedelta(minutes=2)
                                 if release_state == "released" else None),
                ))
        db.flush()
        refresh_monitoring(db, start + timedelta(hours=8))
        refresh_monitoring(db, start + timedelta(hours=8))
        db.commit()

        windows = list(db.query(MonitorWindow).filter_by(cohort=run_id).order_by(MonitorWindow.start_at))
        jobs = list(db.query(MLOpsJob).filter_by(kind="retrain_live"))
        assert len(windows) == 7
        assert windows[0].result["performance"]["positives"] == 10
        assert windows[1].result["performance_degraded"] is True
        assert len(jobs) == 1
        assert jobs[0].status == "queued"
        assert jobs[0].arguments["window"] == windows[1].key
        assert jobs[0].arguments["count"] == 480
        frozen = dict(jobs[0].arguments["frozen_outcomes"])
        assert len(frozen) == 480
        assert not (set(frozen) & {str(item) for item in ineligible_prediction_ids})
        identifier = next(iter(frozen))
        jobs[0].arguments = {**jobs[0].arguments,
                             "frozen_outcomes": {**frozen, identifier: 1 - frozen[identifier]}}
        db.commit()
        from app.training_jobs import _frozen_training_input
        try:
            _frozen_training_input(db, jobs[0])
            raise AssertionError("tampered frozen outcome was accepted")
        except ValueError as exc:
            assert "not verified" in str(exc)
        assert db.get(DemoDataset, f"reviewed-{jobs[0].id}") is None
        jobs[0].arguments = {**jobs[0].arguments, "frozen_outcomes": frozen}
        db.commit()

    # Prove the scheduled trigger reaches the actual durable worker pipeline. The
    # resulting candidate must be registered with MLflow but never self-promoted.
    from app.worker import execute_job

    result = execute_job(jobs[0].id)
    assert result and result["stage"] == "completed"
    with SessionLocal() as db:
        job = db.get(MLOpsJob, jobs[0].id)
        candidate = db.scalar(select(ModelRun).where(ModelRun.version == result["model_version"]))
        active = db.scalar(select(MLOpsRecord).where(MLOpsRecord.kind == "active_model")
                           .order_by(MLOpsRecord.id.desc()))
        assert job.status == "succeeded"
        assert candidate and candidate.mlflow_run_id
        assert result["decision"] in {"eligible", "rejected_by_gates", "insufficient_evidence"}
        assert not active or active.version != candidate.version
