"""Regression tests for case association, analyst review and measured replay impact."""

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from os import environ
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app import investigations
from app.investigations import (
    CasePolicy,
    CasePrediction,
    approved_labels,
    attach_predictions,
    replay_impact,
    router,
)
from app.models import AuditLog, Event, Incident, ModelObservation, Prediction, User, now
from app.investigations import Adjudication
from app.security import current_user

BASE_TIME = datetime(2026, 11, 28, tzinfo=timezone.utc)
FRAUD = {"outcome": "confirmed_fraud", "reason": "Reviewer corroborated the fraud evidence"}


@pytest.fixture()
def database():
    url = environ.get("TG_CASE_TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
        with engine.connect() as connection, connection.begin() as transaction:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                yield db
            transaction.rollback()
        engine.dispose()
        return
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def pair(db, event_id, at, subscriber, *, device=None, network=None, risk=0.85, label=1):
    event = Event(
        event_id=event_id, event_type="CALL", event_time=BASE_TIME + timedelta(minutes=at),
        subscriber_id=subscriber, device_id=device, network_token=network, fraud_label=label,
        scenario_label="synthetic-test", location_token="common-location",
    )
    prediction = Prediction(
        event_id=event_id, model_version="test-model", probability=risk, risk_score=risk,
        risk_band="high" if risk >= 0.6 else "medium", anomaly_score=0, graph_score=0, rule_score=0,
    )
    db.add_all([event, prediction])
    return event, prediction


def api_client(db, role="Administrator"):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: User(username="reviewer", role=role)
    return TestClient(app)


def test_runtime_and_replay_agree_and_deduplicate(database):
    db = database
    rows = [
        pair(db, "episode-start", 0, "sub-1", device="d1", network="n1", risk=0.1),
        pair(db, "alert-anchor", 5, "sub-1", device="d1", network="n1"),
        pair(db, "same-subscriber", 10, "sub-1", device="d2", network="n2"),
        pair(db, "unrelated-device", 12, "sub-2", device="d1", network="n3", label=0),
        pair(db, "unrelated-network", 15, "sub-3", device="d3", network="n1", label=0),
        pair(db, "supported-cross-link", 20, "sub-4", device="d1", network="n1"),
        pair(db, "after-window", 130, "sub-1", device="d1", network="n1"),
    ]
    attach_predictions(db, reversed(rows[:5]), "processing-worker")
    db.commit()
    attach_predictions(db, rows, "processing-worker")
    db.commit()

    assert db.query(Incident).count() == 4
    assert db.query(CasePrediction).count() == 6
    linked = dict(db.execute(select(Prediction.event_id, CasePrediction.decision)
                             .join(CasePrediction)).all())
    assert linked["same-subscriber"] == "same_subscriber"
    assert linked["supported-cross-link"] == "shared_device_and_network"
    assert linked["unrelated-device"] == linked["unrelated-network"] == "first_alert"

    report = replay_impact(rows, 3)
    assert report["correlated"]["investigations"] == db.query(Incident).count()
    assert report["one_alert_per_event"]["investigations"] == 6
    assert report["correlated"]["fraud_episodes_detected"] == report["one_alert_per_event"]["fraud_episodes_detected"]
    assert report["correlated"]["false_positive_cases"] == 2
    assert report["duplicate_alert_reduction"] == pytest.approx(1 / 3)
    assert report["correlated"]["review_budget"] == 3
    with api_client(db, "Auditor") as api:
        impact = api.get("/api/analytics/impact")
        assert impact.status_code == 200
        assert impact.json()["correlated"]["investigations"] == 4


def test_case_adjudication_does_not_label_case_events_and_conflict_is_excluded(database):
    db = database
    event1, score1 = pair(db, "review-positive", 0, "sub-1")
    event2, score2 = pair(db, "case-only", 5, "sub-1")
    attach_predictions(db, [(event1, score1), (event2, score2)], "processing-worker")
    db.flush()
    db.add(ModelObservation(
        prediction_id=score1.id, model_version="test-model", serving_role="champion",
        probability=0.85, predicted_label=1,
    ))
    _, rogue_score = pair(db, "unverified-import", 1, "sub-unverified")
    db.flush()
    db.add(Adjudication(
        prediction_id=rogue_score.id, outcome="confirmed_fraud", reviewer="importer",
        reason="Imported binary label without an authorized review", source="legacy_import",
        reviewed_at=now(),
    ))
    db.commit()
    case_id = db.scalar(select(Incident.id))
    with api_client(db, "Fraud Analyst") as api:
        request = {**FRAUD, "request_id": str(uuid4())}
        record = api.post("/api/predictions/review-positive/adjudications", json=request)
        assert record.status_code == 201
        assert api.post("/api/predictions/review-positive/adjudications", json=request).json() == record.json()
        assert db.get(Prediction, score1.id).ground_truth_label == 1
        assert db.get(Prediction, score2.id).ground_truth_label is None
        assert db.scalar(select(ModelObservation.outcome_label)) == 1
        assert approved_labels(db, now()) == {"review-positive": 1}
        assert approved_labels(db, BASE_TIME - timedelta(days=1)) == {}

        negative = {"outcome": "legitimate", "reason": "Case evidence supports legitimate activity"}
        response = api.post(f"/api/incidents/{case_id}/adjudications", json=negative)
        assert response.status_code == 201
        assert approved_labels(db, now()) == {}
        assert db.get(Prediction, score1.id).ground_truth_label is None
        assert db.get(Prediction, score2.id).ground_truth_label is None
        assert db.scalar(select(ModelObservation.outcome_label)) is None
        assert api.post(f"/api/incidents/{case_id}/adjudications", json=FRAUD).status_code == 409
        corrected = api.post(f"/api/incidents/{case_id}/adjudications",
                             json={**FRAUD, "correction_of": response.json()["id"]})
        assert corrected.status_code == 201
        assert approved_labels(db, now()) == {"review-positive": 1}
        assert db.get(Prediction, score2.id).ground_truth_label is None

    with api_client(db, "Auditor") as api:
        assert api.post("/api/predictions/case-only/adjudications", json=FRAUD).status_code == 403
        assert api.get(f"/api/incidents/{case_id}/timeline").status_code == 200


def test_merge_preserves_legacy_case_and_is_reversible(database):
    db = database
    events = [
        pair(db, "old-case", 0, "sub-1", network="n1"),
        pair(db, "duplicate-case", 15, "sub-1", network="n1"),
        pair(db, "different-subscriber", 20, "sub-2", network="n1"),
    ]
    db.flush()
    for event, prediction in events:
        db.add(Incident(prediction_id=prediction.id, subscriber_id=event.subscriber_id,
                        title=event.event_id, severity="High", status="New"))
    db.commit()
    first, duplicate, unrelated = tuple(db.scalars(select(Incident.id).order_by(Incident.id)))
    reason = "Controlled consolidation of matching evidence"
    with api_client(db, "Investigator") as api:
        assert api.post(f"/api/incidents/{first}/merge", json={
            "source_id": unrelated, "reason": reason,
        }).status_code == 409
        result = api.post(f"/api/incidents/{first}/merge", json={
            "source_id": duplicate, "reason": reason,
        })
        assert result.status_code == 201
        assert len(api.get(f"/api/incidents/{first}/timeline").json()["events"]) == 2
        assert db.query(Incident).count() == 3
        assert api.post(f"/api/incidents/{duplicate}/unmerge", json={"reason": reason}).status_code == 200
        assert len(api.get(f"/api/incidents/{first}/timeline").json()["events"]) == 1
    assert set(db.scalars(select(AuditLog.action))) == {"incident.merged", "incident.merge_reversed"}


def test_review_queue_has_reproducible_low_risk_sample(database):
    db = database
    for i in range(12):
        pair(db, f"low-risk-{i}", i, f"sub-{i}", risk=0.10)
    pair(db, "near-threshold", 14, "last-subscriber", risk=0.349)
    db.commit()
    with api_client(db, "Investigator") as api:
        first = api.get("/api/review/queue?seed=842&limit=4").json()
        assert first == api.get("/api/review/queue?seed=842&limit=4").json()
        assert len({item["event_id"] for item in first["events"]}) == 4
        assert [item["sampling"] for item in first["events"]].count("random_low_risk") == 2
        assert first["events"][2]["event_id"] == "near-threshold"


def test_runtime_enforces_case_capacity(database, monkeypatch):
    db = database
    monkeypatch.setattr(investigations, "policy", CasePolicy(max_events=2))
    rows = [pair(db, f"bounded-{i}", i, "same-subscriber") for i in range(5)]
    attach_predictions(db, rows, "processing-worker")
    db.commit()
    assert db.query(Incident).count() == 3
    assert db.query(CasePrediction).count() == 5
    assert replay_impact(rows, 5)["correlated"]["investigations"] == 3


def test_concurrent_postgres_ingestion_uses_one_case():
    url = environ.get("TG_CASE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TG_CASE_TEST_DATABASE_URL to a migrated, disposable PostgreSQL database.")
    engine = create_engine(url)
    namespace = uuid4().hex
    event_ids = [f"{namespace}-a", f"{namespace}-b"]
    barrier = Barrier(2, timeout=10)

    def submit(event_id):
        with Session(engine) as db:
            event, prediction = pair(db, event_id, 0, namespace)
            db.flush()
            barrier.wait()
            attach_predictions(db, [(event, prediction)], "processing-worker")
            db.commit()

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(submit, event_ids, timeout=20))
        with Session(engine) as db:
            assert db.query(Incident).filter_by(subscriber_id=namespace).count() == 1
            assert db.query(CasePrediction).join(Prediction).filter(Prediction.event_id.in_(event_ids)).count() == 2
    finally:
        with Session(engine) as db, db.begin():
            selected_predictions = select(Prediction.id).where(Prediction.event_id.in_(event_ids))
            db.execute(delete(CasePrediction).where(CasePrediction.prediction_id.in_(selected_predictions)))
            db.execute(delete(Incident).where(Incident.subscriber_id == namespace))
            db.execute(delete(Prediction).where(Prediction.event_id.in_(event_ids)))
            db.execute(delete(Event).where(Event.event_id.in_(event_ids)))
        engine.dispose()
