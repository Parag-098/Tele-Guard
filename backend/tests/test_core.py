from datetime import datetime, timezone
import pytest
from app.ml import features, FEATURES
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


def test_seeded_scenarios_are_reproducible_and_labeled():
    a = generate_events(30, 91)
    b = generate_events(30, 91)
    assert [x.model_dump() for x in a] == [x.model_dump() for x in b]
    assert {x.scenario_label for x in a} == {"sim_swap", "call_burst", "sim_farm"}


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
    assert "fraud_label" not in first.json()["event"]
    graph = client.get("/api/graph", headers=auth(token)).json()
    assert any(node["kind"] == "subscriber" for node in graph["nodes"])
    assert graph["edges"]
    again = client.post("/api/events", json=data, headers=auth(token))
    assert again.json()["duplicate"] is True
    assert client.get("/api/dashboard", headers=auth(token)).json()["events"] == 1


def test_backend_rbac_and_audited_simulated_action(client, token):
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
    assert response.json()["metrics"]["model_comparison"]
    runs = client.get("/api/models", headers=auth(token)).json()
    assert any(run["version"] == response.json()["version"] for run in runs)
    audit = client.get("/api/audit", headers=auth(token)).json()
    assert not any(row["action"] == "mlflow.unavailable" for row in audit)
