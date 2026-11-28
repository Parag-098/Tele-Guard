from datetime import datetime, timedelta, timezone
import csv
import io
import pytest
from app.ml import features, FEATURES, train_model, explain_prediction
from app.main import load_model_run
from app.db import SessionLocal
from app.models import ModelRun, MLOpsJob, MLOpsRecord, Event, Prediction, ModelObservation
from app.runtime_models import ServedSnapshot
from app.synthetic import generate_events
from app.config import Settings
from pydantic import ValidationError


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_authentication_required_and_invalid_credentials_rejected(client):
    assert client.get("/api/dashboard").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "incorrect-password"},
        ).status_code
        == 401
    )


def test_risk_policy_configuration_is_bounded_and_balanced():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, risk_supervised_weight=0.5)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, incident_risk_threshold=1.1)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key="too-short")


def test_seeded_scenarios_are_reproducible_and_labeled():
    a = generate_events(30, 91)
    b = generate_events(30, 91)
    assert [x.model_dump() for x in a] == [x.model_dump() for x in b]
    assert {x.scenario_label for x in a} == {"sim_swap", "call_burst", "sim_farm"}


def test_synthetic_batches_cover_requested_size_and_are_reproducible():
    from app.synthetic import iter_event_batches

    first = list(iter_event_batches(1500, 27, batch_size=127, event_prefix="batch-a"))
    second = list(iter_event_batches(1500, 27, batch_size=127, event_prefix="batch-a"))
    assert [event.event_id for batch in first for event in batch] == [
        event.event_id for batch in second for event in batch
    ]
    assert sum(map(len, first)) == 1500
    assert max(map(len, first)) == 127
    assert {event.event_type for batch in first for event in batch} >= {
        "OTP_REQUEST", "AUTHENTICATION", "CALL", "LOCATION"
    }


def test_contract_rejects_bad_type_and_negative_duration(client, token):
    base = {
        "event_id": "evt_invalid",
        "event_type": "REAL_CALL",
        "event_time": datetime.now(timezone.utc).isoformat(),
        "subscriber_id": "sub_1",
    }
    assert client.post("/api/events", json=base, headers=auth(token)).status_code == 422
    base.update(event_type="CALL", duration_seconds=-1)
    assert client.post("/api/events", json=base, headers=auth(token)).status_code == 422
    base.update(duration_seconds=0, event_time="2026-01-01T12:00:00", subscriber_id="1234567890")
    assert client.post("/api/events", json=base, headers=auth(token)).status_code == 422


def test_inference_is_persisted_and_idempotent(client, token):
    data = {
        "event_id": "evt_test_001",
        "event_type": "SIM_CHANGE",
        "event_time": datetime.now(timezone.utc).isoformat(),
        "subscriber_id": "sub_test",
        "device_id": "dev_test",
        "network_token": "net_test",
        "fraud_label": 1,
        "scenario_label": "test",
    }
    first = client.post("/api/events", json=data, headers=auth(token))
    assert first.status_code == 201
    result = first.json()["prediction"]
    assert result["model_version"] and result["evidence"] and 0 <= result["risk_score"] <= 1
    assert result["policy_version"] == "risk-v2"
    assert "fraud_label" not in first.json()["event"]
    graph = client.get("/api/graph", headers=auth(token)).json()
    assert any(node["kind"] == "subscriber" for node in graph["nodes"])
    assert graph["edges"]
    again = client.post("/api/events", json=data, headers=auth(token))
    assert again.json()["duplicate"] is True
    conflict = client.post(
        "/api/events", json={**data, "subscriber_id": "different-subscriber"}, headers=auth(token)
    )
    assert conflict.status_code == 409
    found = client.get("/api/events?q=evt_test_001", headers=auth(token))
    assert found.status_code == 200 and [row["event_id"] for row in found.json()] == ["evt_test_001"]
    assert client.get("/api/dashboard", headers=auth(token)).json()["events"] == 1


def test_csv_batch_upload_is_validated_idempotent_and_persisted(client, token):
    csv_body = (
        "event_id,event_type,event_time,subscriber_id,duration_seconds,fraud_label\n"
        "csv_event_1,CALL,2026-10-01T10:00:00Z,csv_sub_1,32,1\n"
        "csv_event_2,OTP_REQUEST,2026-10-01T10:01:00Z,csv_sub_1,,0\n"
    )
    response = client.post(
        "/api/events/upload-csv", content=csv_body,
        headers={**auth(token), "Content-Type": "text/csv"},
    )
    assert response.status_code == 201
    assert response.json()["created"] == 2
    assert response.json()["predictions"] == 2
    duplicate = client.post(
        "/api/events/upload-csv", content=csv_body,
        headers={**auth(token), "Content-Type": "text/csv"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["created"] == 0 and duplicate.json()["duplicates"] == 2
    assert client.get("/api/dashboard", headers=auth(token)).json()["events"] == 2
    conflict_csv = (
        "event_id,event_type,event_time,subscriber_id,duration_seconds\n"
        "csv_event_1,CALL,2026-10-01T10:00:00Z,conflicting-subscriber,32\n"
        "csv_new,CALL,2026-10-01T10:02:00Z,csv_sub_1,22\n"
    )
    conflict = client.post(
        "/api/events/upload-csv", content=conflict_csv,
        headers={**auth(token), "Content-Type": "text/csv"},
    )
    assert conflict.status_code == 409
    assert client.get("/api/dashboard", headers=auth(token)).json()["events"] == 2


def test_online_and_csv_scoring_match_with_tied_times_and_over_200_prior_events(client, token):
    """Ingress paths share the same ordered, as-of feature history contract."""
    online_subscriber, batch_subscriber = "parity-online-205", "parity-batch-205"
    start = datetime.now(timezone.utc) - timedelta(minutes=104)
    history = []
    for index in range(206):
        event_time = start + timedelta(minutes=index // 2)
        for subscriber in (online_subscriber, batch_subscriber):
            history.append(Event(
                event_id=f"parity-{subscriber}-{index:03d}", event_type="CALL",
                event_time=event_time, subscriber_id=subscriber,
                destination_token=f"synthetic-destination-{index % 13}",
                duration_seconds=20 + index % 70, call_direction="outgoing",
                is_international=index % 7 == 0, is_roaming=index % 11 == 0,
            ))
    with SessionLocal() as db:
        db.add_all(history)
        db.commit()

    event_time = start + timedelta(minutes=103)
    online = {
        "event_id": "parity-online-live", "event_type": "CALL",
        "event_time": event_time.isoformat(), "subscriber_id": online_subscriber,
        "destination_token": "synthetic-destination-current", "duration_seconds": 41,
        "call_direction": "outgoing", "is_international": False, "is_roaming": False,
    }
    online_result = client.post("/api/events", headers=auth(token), json=online)
    assert online_result.status_code == 201

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=list(online))
    writer.writeheader()
    writer.writerow({**online, "event_id": "parity-batch-live", "subscriber_id": batch_subscriber})
    batch_result = client.post(
        "/api/events/upload-csv", headers={**auth(token), "Content-Type": "text/csv"},
        content=csv_buffer.getvalue(),
    )
    assert batch_result.status_code == 201
    online_prediction = online_result.json()["prediction"]
    with SessionLocal() as db:
        batch_prediction = db.query(Prediction).filter_by(event_id="parity-batch-live").one()
        online_snapshot = db.query(ServedSnapshot).join(
            Prediction, Prediction.id == ServedSnapshot.prediction_id
        ).filter(Prediction.event_id == "parity-online-live").one()
        batch_snapshot = db.query(ServedSnapshot).join(
            Prediction, Prediction.id == ServedSnapshot.prediction_id
        ).filter(Prediction.event_id == "parity-batch-live").one()
        assert online_prediction["probability"] == pytest.approx(batch_prediction.probability)
        assert online_prediction["risk_score"] == pytest.approx(batch_prediction.risk_score)
        assert online_prediction["anomaly_score"] == pytest.approx(batch_prediction.anomaly_score)
        assert online_prediction["graph_score"] == pytest.approx(batch_prediction.graph_score)
        assert online_prediction["rule_score"] == pytest.approx(batch_prediction.rule_score)
        assert online_snapshot.values == batch_snapshot.values


def test_late_online_and_csv_events_ignore_already_persisted_future_context(client, token):
    start = datetime.now(timezone.utc) - timedelta(hours=3)
    before, late, future = start, start + timedelta(hours=1), start + timedelta(hours=2)
    history = []
    for subscriber in ("late-online", "late-csv"):
        history.extend((
            Event(
                event_id=f"{subscriber}-before", event_type="CALL", event_time=before,
                subscriber_id=subscriber, duration_seconds=60,
            ),
            Event(
                event_id=f"{subscriber}-future", event_type="AUTHENTICATION", event_time=future,
                subscriber_id=subscriber, auth_outcome="failed",
            ),
        ))
    with SessionLocal() as db:
        db.add_all(history)
        db.commit()

    common = {
        "event_type": "CALL", "event_time": late.isoformat(), "duration_seconds": 35,
        "call_direction": "outgoing", "is_international": False, "is_roaming": False,
    }
    online = client.post("/api/events", headers=auth(token), json={
        **common, "event_id": "late-online-arrived-last", "subscriber_id": "late-online",
    })
    assert online.status_code == 201
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=[
        "event_id", "event_type", "event_time", "subscriber_id", "duration_seconds",
        "call_direction", "is_international", "is_roaming",
    ])
    writer.writeheader()
    writer.writerow({
        **common, "event_id": "late-csv-arrived-last", "subscriber_id": "late-csv",
    })
    batch = client.post(
        "/api/events/upload-csv", headers={**auth(token), "Content-Type": "text/csv"},
        content=csv_buffer.getvalue(),
    )
    assert batch.status_code == 201
    with SessionLocal() as db:
        snapshots = {
            event_id: db.query(ServedSnapshot).join(
                Prediction, Prediction.id == ServedSnapshot.prediction_id
            ).filter(Prediction.event_id == event_id).one()
            for event_id in ("late-online-arrived-last", "late-csv-arrived-last")
        }
    assert snapshots["late-online-arrived-last"].values == snapshots["late-csv-arrived-last"].values
    for snapshot in snapshots.values():
        assert snapshot.values["subscriber_event_count"] == 1
        assert snapshot.values["failed_auth_1h"] == 0


def test_csv_upload_validation_is_atomic_and_seed_job_is_admin_only(client, token):
    bad_csv = (
        "event_id,event_type,event_time,subscriber_id\n"
        "csv_valid,CALL,2026-10-01T10:00:00Z,csv_sub\n"
        "csv_bad,NOT_A_REAL_EVENT,2026-10-01T10:01:00Z,csv_sub\n"
    )
    response = client.post(
        "/api/events/upload-csv", content=bad_csv,
        headers={**auth(token), "Content-Type": "text/csv"},
    )
    assert response.status_code == 422
    assert client.get("/api/dashboard", headers=auth(token)).json()["events"] == 0
    auditor = client.post(
        "/api/auth/login", json={"username": "auditor", "password": "test-password-123"}
    ).json()["access_token"]
    assert client.post(
        "/api/datasets/seed", headers=auth(auditor), json={"count": 150000, "seed": 42}
    ).status_code == 403
    queued = client.post(
        "/api/datasets/seed", headers=auth(token), json={"count": 150000, "seed": 42}
    )
    assert queued.status_code == 202
    job = client.get(f"/api/jobs/{queued.json()['job_id']}", headers=auth(token)).json()
    assert job["status"] == "queued" and job["progress_total"] == 150000


def test_location_travel_evidence_and_missing_location_are_safe(client, token):
    first = {
        "event_id": "evt_geo_first", "event_type": "LOCATION", "event_time": "2026-10-01T10:00:00Z",
        "subscriber_id": "sub_geo", "location_token": "loc_west", "latitude": 19.076, "longitude": 72.877,
    }
    second = {
        "event_id": "evt_geo_next", "event_type": "LOCATION", "event_time": "2026-10-01T11:00:00Z",
        "subscriber_id": "sub_geo", "location_token": "loc_east", "latitude": 28.613, "longitude": 77.209,
    }
    assert client.post("/api/events", json=first, headers=auth(token)).status_code == 201
    prediction = client.post("/api/events", json=second, headers=auth(token)).json()["prediction"]
    evidence = next(x for x in prediction["evidence"] if x["signal"] == "location_travel_scenario")
    assert any(x["code"] == "impossible_travel" for x in evidence["findings"])
    missing = {"event_id": "evt_geo_none", "event_type": "CALL", "event_time": "2026-10-01T12:00:00Z", "subscriber_id": "sub_no_geo"}
    skipped = client.post("/api/events", json=missing, headers=auth(token))
    assert skipped.status_code == 201
    assert "geographic checks were skipped" in next(x for x in skipped.json()["prediction"]["evidence"] if x["signal"] == "location_travel_scenario")["detail"]
    missing["event_id"] = "evt_geo_partial"
    missing["latitude"] = 45
    assert client.post("/api/events", json=missing, headers=auth(token)).status_code == 422


def test_delayed_label_is_immutable_and_dashboard_metrics_update(client, token):
    event = {"event_id": "evt_label_wait", "event_type": "CALL", "event_time": datetime.now(timezone.utc).isoformat(), "subscriber_id": "sub_label"}
    assert client.post("/api/events", json=event, headers=auth(token)).status_code == 201
    before = client.get("/api/mlops/monitoring", headers=auth(token)).json()
    assert before["pending_labels"] == 1
    labeled = client.post("/api/predictions/evt_label_wait/label", headers=auth(token), json={"label": 1, "reason": "Analyst confirmed the synthetic account takeover evidence"})
    assert labeled.status_code == 200 and labeled.json()["status"] == "evaluated"
    review = client.get("/api/predictions/evt_label_wait/adjudications", headers=auth(token))
    assert review.status_code == 200
    assert review.json()[0]["outcome"] == "confirmed_fraud"
    assert review.json()[0]["reviewer"] == "admin"
    assert review.json()[0]["reason"] == "Analyst confirmed the synthetic account takeover evidence"
    assert labeled.json()["monitoring"]["received_labels"] == 1
    missing_reason = client.post("/api/predictions/evt_label_wait/label", headers=auth(token), json={"label": 0})
    assert missing_reason.status_code == 422
    duplicate = client.post("/api/predictions/evt_label_wait/label", headers=auth(token), json={"label": 0, "reason": "Attempted conflicting legacy label"})
    assert duplicate.status_code == 409
    invalid = client.post("/api/predictions/evt_label_wait/label", headers=auth(token), json={"label": 2, "reason": "Invalid label test"})
    assert invalid.status_code == 422


def test_serving_configuration_is_admin_controlled_and_validated(client, token):
    auditor = client.post("/api/auth/login", json={"username": "auditor", "password": "test-password-123"}).json()["access_token"]
    assert client.post("/api/mlops/serving", headers=auth(auditor), json={"mode":"champion"}).status_code == 403
    assert client.post("/api/mlops/serving", headers=auth(token), json={"mode":"canary", "challenger_version":"missing", "canary_percent":10}).status_code == 422
    saved = client.post("/api/mlops/serving", headers=auth(token), json={"mode":"champion", "canary_percent":0})
    assert saved.status_code == 200 and saved.json()["mode"] == "champion"
    assert client.post("/api/mlops/scenarios", headers=auth(auditor), json={"max_speed_kmh":500}).status_code == 403
    configured = client.post("/api/mlops/scenarios", headers=auth(token), json={"max_speed_kmh":500,"risk_weight":0.3,"scenario_rules":{"night_access":{"event_type":"ACCOUNT_ACTIVITY","description":"Review synthetic account activity"}}})
    assert configured.status_code == 200
    retained = client.post("/api/mlops/scenarios", headers=auth(token), json={"max_speed_kmh":600})
    assert retained.status_code == 200 and "night_access" in retained.json()["scenario_rules"]
    event = {"event_id":"evt_configured_scenario", "event_type":"ACCOUNT_ACTIVITY", "event_time":datetime.now(timezone.utc).isoformat(), "subscriber_id":"sub_configured"}
    evaluated = client.post("/api/events", headers=auth(token), json=event).json()["prediction"]
    findings = next(x for x in evaluated["evidence"] if x["signal"] == "location_travel_scenario")["findings"]
    assert any(x["code"] == "configured_scenario" and x["scenario"] == "night_access" for x in findings)
    assert client.post("/api/mlops/scenarios", headers=auth(token), json={"max_speed_kmh":5000}).status_code == 422


def test_delayed_label_monitor_generates_rolling_degradation_alert(client, token):
    with SessionLocal() as db:
        for index in range(40):
            event_id = f"evt_roll_{index:03d}"
            db.add(Event(event_id=event_id, event_type="CALL", event_time=datetime(2026, 1, 1, tzinfo=timezone.utc), subscriber_id="sub_roll"))
            db.flush()
            outcome = 1 if index < 20 else 0
            prediction = Prediction(event_id=event_id, model_version="roll-watch", probability=0.8 if index < 20 else 0.2, anomaly_score=0, graph_score=0, rule_score=0, risk_score=0, risk_band="Low", evidence=[], ground_truth_label=outcome, label_received_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
            db.add(prediction)
            db.flush()
            db.add(ModelObservation(prediction_id=prediction.id, model_version="roll-watch", serving_role="champion", probability=0.8 if index < 20 else 0.2, predicted_label=1 if index < 20 else 0, outcome_label=outcome, evaluated_at=datetime(2026, 2, 1, tzinfo=timezone.utc)+timedelta(minutes=index)))
        db.commit()
    monitoring = client.get("/api/mlops/monitoring", headers=auth(token)).json()
    assert monitoring["alert"] is True
    assert monitoring["models"]["roll-watch"]["pr_auc"] == 1.0
    assert monitoring["degradation_alerts"][0]["recent_20_recall"] == 0.0
    assert "roll back or retrain" in monitoring["degradation_alerts"][0]["action"]


def test_backend_rbac_and_audited_simulated_action(client, token, monkeypatch):
    # This test covers incident authorization and audited reversible actions, not
    # whether a lone SIM_CHANGE is fraudulent. Keep its risk fixture deterministic:
    # identity changes are legitimate lookalikes and must not be force-alerted.
    import app.main as main

    monkeypatch.setattr(main, "score", lambda *_args, **_kwargs: {
        "probability": 0.95, "anomaly_score": 0.8, "graph_score": 0.5,
        "rule_score": 1.0, "risk_score": 0.9, "risk_band": "Critical",
        "evidence": [{"signal": "synthetic_test_fixture", "value": 0.9}],
        "monitor_features": {}, "feature_version": "test-fixture-v1",
    })
    data = {
        "event_id": "evt_case_001",
        "event_type": "SIM_CHANGE",
        "event_time": datetime.now(timezone.utc).isoformat(),
        "subscriber_id": "sub_case",
        "device_id": "dev_case",
    }
    client.post("/api/events", json=data, headers=auth(token))
    cases = client.get("/api/incidents", headers=auth(token)).json()
    assert cases
    incident = cases[0]["id"]
    auditor = client.post(
        "/api/auth/login", json={"username": "auditor", "password": "test-password-123"}
    ).json()["access_token"]
    assert (
        client.patch(
            f"/api/incidents/{incident}",
            json={"status": "Resolved", "reason": "test"},
            headers=auth(auditor),
        ).status_code
        == 403
    )
    acted = client.post(
        f"/api/incidents/{incident}/actions",
        json={"action": "monitor", "reason": "test-only simulation"},
        headers=auth(token),
    )
    assert acted.status_code == 201 and acted.json()["simulation_only"]
    action_id = acted.json()["id"]
    reversed_action = client.post(
        f"/api/actions/{action_id}/reverse",
        json={"action": "reverse", "reason": "review complete"},
        headers=auth(token),
    )
    assert reversed_action.status_code == 201
    assert reversed_action.json()["reverses_id"] == action_id
    assert (
        client.post(
            f"/api/actions/{action_id}/reverse",
            json={"action": "reverse", "reason": "duplicate reversal"},
            headers=auth(token),
        ).status_code
        == 409
    )
    assert any(
        a["action"] == "simulated.monitor"
        for a in client.get("/api/audit", headers=auth(token)).json()
    )


def test_incident_resolution_provenance_search_and_assignment(client, token, monkeypatch):
    # The workflow assertions require a case to exist. Use an explicit high-risk
    # scoring fixture instead of relying on a model artifact's synthetic score for
    # an isolated identity-change event.
    import app.main as main

    monkeypatch.setattr(main, "score", lambda *_args, **_kwargs: {
        "probability": 0.95, "anomaly_score": 0.8, "graph_score": 0.5,
        "rule_score": 1.0, "risk_score": 0.9, "risk_band": "Critical",
        "evidence": [{"signal": "synthetic_test_fixture", "value": 0.9}],
        "monitor_features": {}, "feature_version": "test-fixture-v1",
    })
    event = {
        "event_id": "evt_resolution_case",
        "event_type": "SIM_CHANGE",
        "event_time": datetime.now(timezone.utc).isoformat(),
        "subscriber_id": "resolution_subscriber",
        "device_id": "resolution_device",
    }
    assert client.post("/api/events", json=event, headers=auth(token)).status_code == 201
    cases = client.get("/api/incidents?q=resolution_subscriber&limit=5", headers=auth(token))
    assert cases.status_code == 200 and len(cases.json()) == 1
    incident = cases.json()[0]
    assert client.patch(
        f"/api/incidents/{incident['id']}",
        headers=auth(token),
        json={"status": "Resolved", "reason": "insufficient evidence"},
    ).status_code == 422
    assert client.patch(
        f"/api/incidents/{incident['id']}",
        headers=auth(token),
        json={"status": "False Positive", "reason": "reviewed", "resolution_outcome": "inconclusive"},
    ).status_code == 422
    assert client.patch(
        f"/api/incidents/{incident['id']}",
        headers=auth(token),
        json={"assigned_to": "missing-user", "reason": "assignment"},
    ).status_code == 422
    created = client.post(
        "/api/auth/users",
        headers=auth(token),
        json={"username": "case_investigator", "password": "case-test-pass-123", "role": "Investigator"},
    )
    assert created.status_code == 201
    assigned = client.patch(
        f"/api/incidents/{incident['id']}",
        headers=auth(token),
        json={"assigned_to": "case_investigator", "reason": "assigned for review"},
    )
    assert assigned.status_code == 200
    resolved = client.patch(
        f"/api/incidents/{incident['id']}",
        headers=auth(token),
        json={"status": "Resolved", "reason": "synthetic evidence reviewed", "resolution_outcome": "confirmed_fraud"},
    )
    assert resolved.status_code == 200
    detail = client.get("/api/incidents?q=resolution_subscriber", headers=auth(token)).json()[0]
    assert detail["resolved_by"] == "admin"
    assert detail["resolution_outcome"] == "confirmed_fraud"
    assert detail["resolution_reason"] == "synthetic evidence reviewed"
    assert detail["history"] and detail["history"][0]["actor"] == "admin"
    assert client.get("/api/incidents?status=Resolved", headers=auth(token)).json()[0]["id"] == incident["id"]
    reopened = client.patch(
        f"/api/incidents/{incident['id']}",
        headers=auth(token),
        json={"status": "Investigating", "reason": "new evidence received"},
    )
    assert reopened.status_code == 200
    detail = client.get("/api/incidents?q=resolution_subscriber", headers=auth(token)).json()[0]
    assert detail["resolved_at"] is None and detail["resolution_outcome"] is None
    assert len(detail["history"]) >= 3


def test_feature_columns_exclude_label_scenario_and_future_context():
    base = {
        "subscriber_id": "sub_1",
        "event_type": "CALL",
        "duration_seconds": 20,
        "device_id": "dev_a",
        "network_token": "net_a",
        "event_time": "2026-01-01T00:00:00Z",
        "fraud_label": 1,
        "scenario_label": "fraud",
    }
    X = features([base, {**base, "event_id": "second", "event_time": "2026-01-01T00:05:00Z"}])
    assert list(X.columns) == FEATURES
    assert X.iloc[0]["device_reuse"] == 0 and X.iloc[1]["device_reuse"] == 1


def test_shap_explanation_maps_feature_contributions_to_actual_prediction(tmp_path):
    rows = [event.model_dump(mode="json") for event in generate_events(420, 78)]
    result = train_model(str(tmp_path / "model.joblib"), rows=rows)
    import joblib

    model = joblib.load(result["artifact_path"])
    explanation = explain_prediction(model, rows[-1], rows[:-1][-25:], model["explain_background"])
    assert explanation["model_version"] == result["version"]
    assert explanation["feature_version"] == model["explain_background_feature_version"]
    assert {item["feature"] for item in explanation["contributions"]} == set(FEATURES)
    assert all("shap_value" in item and "feature_value" in item for item in explanation["contributions"])
    assert abs(explanation["additivity_residual"]) < 1e-5
    assert explanation["output_scale"] in {"fraud_probability", "fraud_log_odds"}
    mismatched = {**model, "features": list(reversed(FEATURES))}
    with pytest.raises(ValueError, match="feature schema"):
        explain_prediction(mismatched, rows[-1], [], model["explain_background"])


def test_missing_trusted_model_artifact_is_downloaded_by_recorded_mlflow_run(tmp_path, monkeypatch):
    import joblib

    saved = tmp_path / "downloaded.joblib"
    joblib.dump({"version": "synthetic-test-v1"}, saved)
    calls = []

    class FakeClient:
        def download_artifacts(self, run_id, path):
            calls.append((run_id, path))
            return str(saved)

    import mlflow

    monkeypatch.setattr(mlflow, "MlflowClient", FakeClient)
    model_run = ModelRun(
        version="synthetic-test-v1",
        algorithm="RandomForestClassifier",
        dataset_version="baseline-v1",
        metrics={},
        artifact_path="/missing/fraud-model-synthetic-test-v1.joblib",
        mlflow_run_id="tracked-run-001",
    )
    assert load_model_run(model_run)["version"] == model_run.version
    assert calls == [("tracked-run-001", "fraud-model-synthetic-test-v1.joblib")]


def test_api_startup_recovers_active_champion_when_local_cache_is_empty(tmp_path, monkeypatch):
    import hashlib
    import joblib
    import mlflow
    from fastapi.testclient import TestClient
    from app.db import Base, engine
    from app.main import _load_local_artifact, app

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _load_local_artifact.cache_clear()
    artifact = tmp_path / "recovered-champion.joblib"
    joblib.dump({"version": "cold-start-champion-v1", "algorithm": "test-fixture"}, artifact)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    calls = []

    class FakeClient:
        def download_artifacts(self, run_id, path):
            calls.append((run_id, path))
            return str(artifact)

    monkeypatch.setattr(mlflow, "MlflowClient", FakeClient)
    with SessionLocal() as db:
        db.add(ModelRun(
            version="cold-start-champion-v1", algorithm="test-fixture",
            dataset_version="baseline-v1", metrics={"artifact_sha256": digest},
            artifact_path="/empty-cache/recovered-champion.joblib", mlflow_run_id="cold-run-1",
        ))
        db.add(MLOpsRecord(
            kind="active_model", version="cold-start-champion-v1",
            payload={"reason": "isolated cold-start recovery test"}, created_by="test",
        ))
        db.commit()

    try:
        with TestClient(app):
            assert app.state.model["version"] == "cold-start-champion-v1"
        assert calls == [("cold-run-1", "recovered-champion.joblib")]
        assert artifact.exists()
    finally:
        _load_local_artifact.cache_clear()
        Base.metadata.drop_all(engine)


def test_readiness_refreshes_model_after_another_worker_promotion(client, monkeypatch):
    import app.main as main

    version = "cross-worker-promoted-champion"
    with SessionLocal() as db:
        db.add(ModelRun(
            version=version, algorithm="fixture", dataset_version="fixture-v1",
            metrics={}, artifact_path="/tmp/cross-worker-champion.joblib",
        ))
        db.add(MLOpsRecord(
            kind="active_model", version=version,
            payload={"reason": "simulated promotion by another API worker"}, created_by="test",
        ))
        db.commit()

    monkeypatch.setattr(main, "load_model_run", lambda row: {"version": row.version})
    main.app.state.model = {"version": "stale-worker-champion"}
    ready = client.get("/api/ready")
    assert ready.status_code == 200
    assert main.app.state.model["version"] == version


def test_admin_user_creation_and_role_protection(client, token):
    created = client.post(
        "/api/auth/users",
        headers=auth(token),
        json={
            "username": "new_investigator",
            "password": "local-test-pass-123",
            "role": "Investigator",
        },
    )
    assert created.status_code == 201
    assert created.json()["role"] == "Investigator"
    auditor_token = client.post(
        "/api/auth/login",
        json={"username": "auditor", "password": "test-password-123"},
    ).json()["access_token"]
    assert client.get("/api/auth/users", headers=auth(auditor_token)).status_code == 403
    assert (
        client.post(
            "/api/auth/users",
            headers=auth(token),
            json={"username": "short", "password": "short", "role": "Administrator"},
        ).status_code
        == 422
    )


def test_training_run_persists_metrics_and_mlflow_tracking(client, token):
    response = client.post("/api/models/train", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["mlflow_run_id"]
    assert response.json()["metrics"]["model_comparison"]
    runs = client.get("/api/models", headers=auth(token)).json()
    assert any(
        run["version"] == response.json()["version"]
        and run["mlflow_run_id"] == response.json()["mlflow_run_id"]
        for run in runs
    )
    audit = client.get("/api/audit", headers=auth(token)).json()
    assert not any(row["action"] == "mlflow.unavailable" for row in audit)


def test_session_logout_revokes_server_side_token(client):
    token = client.post(
        "/api/auth/login", json={"username": "admin", "password": "test-password-123"}
    ).json()["access_token"]
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
    assert client.post("/api/auth/logout", headers=auth(token)).json()["revoked"]
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


def test_admin_role_management_revokes_disabled_user_and_protects_last_admin(client, token):
    session = client.post(
        "/api/auth/login", json={"username": "auditor", "password": "test-password-123"}
    ).json()["access_token"]
    changed = client.patch(
        "/api/auth/users/auditor", headers=auth(token), json={"role": "ML Engineer"}
    )
    assert changed.status_code == 200 and changed.json()["role"] == "ML Engineer"
    disabled = client.patch("/api/auth/users/auditor", headers=auth(token), json={"active": False})
    assert disabled.status_code == 200
    assert client.get("/api/auth/me", headers=auth(session)).status_code == 401
    assert (
        client.patch(
            "/api/auth/users/admin", headers=auth(token), json={"active": False}
        ).status_code
        == 409
    )


def test_mlops_drift_retraining_approval_and_rollback(client, token, monkeypatch):
    auditor = client.post(
        "/api/auth/login", json={"username": "auditor", "password": "test-password-123"}
    ).json()["access_token"]
    assert client.post("/api/mlops/initialize", headers=auth(auditor)).status_code == 403
    initialized = client.post("/api/mlops/initialize", headers=auth(token))
    assert initialized.status_code == 200
    champion = initialized.json()["active_model"]
    drift = client.post("/api/mlops/drift/simulate", headers=auth(token), json={"seed": 731})
    assert drift.status_code == 200
    assert drift.json()["modified_features"]
    report = client.post(
        "/api/mlops/drift/detect",
        headers=auth(token),
        json={
            "reference_version": "baseline-v1-seed-2026",
            "current_version": drift.json()["version"],
        },
    )
    assert report.status_code == 200
    assert report.json()["status"] == "drift_detected"
    assert "does not establish concept drift" in report.json()["interpretation"]
    assert any(
        feature["feature"] == "network_token" and feature["drifted"]
        for feature in report.json()["features"]
    )
    assert (
        client.post(
            "/api/mlops/retrain",
            headers=auth(auditor),
            json={"dataset_version": drift.json()["version"]},
        ).status_code
        == 403
    )
    trained = client.post(
        "/api/mlops/retrain",
        headers=auth(token),
        json={"dataset_version": drift.json()["version"], "reason": "test drift"},
    )
    assert trained.status_code == 200
    assert trained.json()["mlflow_run_id"]
    challenger = trained.json()["version"]
    compared = client.post(
        "/api/mlops/compare", headers=auth(token), json={"challenger_version": challenger}
    )
    assert compared.status_code == 200
    assert compared.json()["dataset_version"] == drift.json()["version"]
    configured = client.post("/api/mlops/serving", headers=auth(token), json={"mode":"shadow", "challenger_version":challenger})
    assert configured.status_code == 200
    shadow_event = {"event_id":"evt_shadow_check", "event_type":"CALL", "event_time":datetime.now(timezone.utc).isoformat(), "subscriber_id":"sub_shadow"}
    shadow_prediction = client.post("/api/events", headers=auth(token), json=shadow_event).json()["prediction"]
    assert shadow_prediction["model_version"] == champion
    observed = client.get("/api/mlops/monitoring", headers=auth(token)).json()
    assert observed["models"][champion]["predictions"] >= 1
    assert observed["models"][challenger]["predictions"] >= 1
    from app import main as app_main

    with monkeypatch.context() as patch:
        patch.setattr(app_main, "load_model_run", lambda _row: (_ for _ in ()).throw(RuntimeError("synthetic challenger load failure")))
        failed_event = {"event_id":"evt_challenger_failure", "event_type":"CALL", "event_time":datetime.now(timezone.utc).isoformat(), "subscriber_id":"sub_failure"}
        failed_prediction = client.post("/api/events", headers=auth(token), json=failed_event).json()["prediction"]
        assert failed_prediction["model_version"] == champion
    audit = client.get("/api/audit", headers=auth(token)).json()
    assert any(row["action"] == "model.challenger_failed" and row["details"].get("champion_retained") for row in audit)
    canary_config = client.post("/api/mlops/serving", headers=auth(token), json={"mode":"canary", "challenger_version":challenger, "canary_percent":10})
    assert canary_config.status_code == 200
    canary_start = datetime.now(timezone.utc) - timedelta(seconds=10_000)
    for batch_start in range(0, 10_000, 5_000):
        lines = ["event_id,event_type,event_time,subscriber_id,duration_seconds"]
        for index in range(batch_start, batch_start + 5_000):
            event_time = (canary_start + timedelta(seconds=index)).isoformat()
            lines.append(f"canary_release_{index:05d},CALL,{event_time},canary_shared_prefix_{index:05d},60")
        uploaded = client.post("/api/events/upload-csv", content="\n".join(lines),
                               headers={**auth(token), "Content-Type": "text/csv"})
        assert uploaded.status_code == 201
        assert uploaded.json()["created"] == uploaded.json()["predictions"] == 5_000
    canary_allocation = client.get("/api/mlops", headers=auth(token)).json()["canary_allocation"]
    assert canary_allocation["configured_percent"] == 10
    assert canary_allocation["events"] == canary_allocation["subscribers"] == 10_000
    assert 800 <= canary_allocation["assigned_subscribers"] <= 1_200
    assert canary_allocation["assigned_events"] == canary_allocation["served_events"]
    assert canary_allocation["fallback_events"] == 0
    from app.decision_policy import assigned_canary
    from app import main as app_main

    fallback_subscriber = next(
        f"fallback_canary_{index}" for index in range(10_000)
        if assigned_canary(f"fallback_canary_{index}", canary_config.json())
    )
    with monkeypatch.context() as patch:
        patch.setattr(app_main, "load_model_run",
                      lambda _row: (_ for _ in ()).throw(RuntimeError("synthetic canary artifact failure")))
        fallback_response = client.post("/api/events", headers=auth(token), json={
            "event_id": "evt_canary_fallback", "event_type": "CALL",
            "event_time": datetime.now(timezone.utc).isoformat(),
            "subscriber_id": fallback_subscriber,
        })
        assert fallback_response.status_code == 201
        assert fallback_response.json()["prediction"]["model_version"] == champion
    canary_fallbacks = client.get("/api/mlops", headers=auth(token)).json()["canary_allocation"]
    assert canary_fallbacks["fallback_events"] == 1
    assert client.post("/api/mlops/serving", headers=auth(token), json={"mode":"champion"}).status_code == 200
    assert (
        client.post(
            "/api/mlops/compare",
            headers=auth(auditor),
            json={"challenger_version": challenger},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/mlops/decisions/{challenger}",
            headers=auth(auditor),
            json={"decision": "approve"},
        ).status_code
        == 403
    )
    stale_release = f"concurrent-release-{challenger}"
    with SessionLocal() as db:
        db.add(MLOpsRecord(kind="active_model", version=stale_release,
                           payload={"reason": "stale approval regression"}, created_by="test"))
        db.commit()
    stale_decision = client.post(
        f"/api/mlops/decisions/{challenger}", headers=auth(token),
        json={"decision": "approve", "reason": "comparison was made against the previous champion"},
    )
    assert stale_decision.status_code == 409
    with SessionLocal() as db:
        db.query(MLOpsRecord).filter_by(kind="active_model", version=stale_release).delete()
        db.commit()
    decision = "approve" if compared.json()["passed"] else "reject"
    acted = client.post(
        f"/api/mlops/decisions/{challenger}",
        headers=auth(token),
        json={"decision": decision, "reason": "test gate decision"},
    )
    assert acted.status_code == 200
    assert acted.json()["active_model"] == (challenger if decision == "approve" else champion)
    if decision == "approve":
        rollback = client.post(
            "/api/mlops/rollback",
            headers=auth(token),
            json={"version": champion, "reason": "test rollback"},
        )
        assert rollback.status_code == 200
        assert rollback.json()["active_model"] == champion
    state = client.get("/api/mlops", headers=auth(token)).json()
    assert state["active_model"] == champion
    assert any(record["kind"] == "drift_report" for record in state["records"])
    assert any(
        record["kind"] in {"approved_model", "rejected_model"} for record in state["records"]
    )


def test_job_api_redacts_internal_failure_details(client, token):
    with SessionLocal() as db:
        db.add(MLOpsJob(
            id="redacted-job-fixture", kind="retrain_live", status="failed",
            requested_by="admin", arguments={}, error="/srv/app/secrets/password=private-token",
        ))
        db.commit()

    response = client.get("/api/jobs/redacted-job-fixture", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["error"] == (
        "Job failed. Contact an administrator with the job ID to review operational logs."
    )
    assert "private-token" not in response.text
    assert "/srv/app" not in response.text
    summary = client.get("/api/mlops", headers=auth(token))
    assert summary.status_code == 200
    assert "private-token" not in summary.text
