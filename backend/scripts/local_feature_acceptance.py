"""Exercise context, shadow/canary, delayed labels and PostgreSQL persistence locally.

Requires the local Compose stack and TG_ADMIN_USERNAME/TG_ADMIN_PASSWORD in the environment.
Uses only generated synthetic identifiers, coordinates and events.
"""
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import httpx


API = os.getenv("TG_ACCEPTANCE_API", "http://localhost:8000/api")


def main():
    with httpx.Client(base_url=API, timeout=180) as client:
        login = client.post("/auth/login", json={"username": os.environ["TG_ADMIN_USERNAME"], "password": os.environ["TG_ADMIN_PASSWORD"]})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        state = client.get("/mlops", headers=headers)
        state.raise_for_status()
        state = state.json()
        active = state["active_model"]
        candidates = [m["version"] for m in state["models"] if m["version"] != active]
        if not candidates:
            trained = client.post("/models/train", headers=headers)
            trained.raise_for_status()
            candidates = [trained.json()["version"]]
        challenger = candidates[0]
        scenario_config = client.post("/mlops/scenarios", headers=headers, json={"max_speed_kmh": 800, "impossible_travel_minutes": 120, "risk_weight": 0.2})
        scenario_config.raise_for_status()
        client.post("/mlops/serving", headers=headers, json={"mode": "shadow", "challenger_version": challenger}).raise_for_status()
        prefix = "evt_accept_" + uuid4().hex[:10]
        now = datetime.now(timezone.utc)
        first = {"event_id": prefix+"a", "event_type": "LOCATION", "event_time": (now-timedelta(minutes=90)).isoformat(), "subscriber_id": "sub_accept_"+uuid4().hex[:8], "location_token": "loc_synthetic_west", "latitude": 19.076, "longitude": 72.877}
        second = {**first, "event_id": prefix+"b", "event_time": (now-timedelta(minutes=30)).isoformat(), "location_token": "loc_synthetic_east", "latitude": 28.613, "longitude": 77.209}
        first_result = client.post("/events", headers=headers, json=first)
        first_result.raise_for_status()
        shadow_result = client.post("/events", headers=headers, json=second)
        shadow_result.raise_for_status()
        shadow_prediction = shadow_result.json()["prediction"]
        finding = next(e for e in shadow_prediction["evidence"] if e["signal"] == "location_travel_scenario")
        assert any(x["code"] == "impossible_travel" for x in finding["findings"])
        assert shadow_prediction["model_version"] == active
        monitor = client.get("/mlops/monitoring", headers=headers).json()
        assert monitor["models"][challenger]["predictions"] >= 2

        client.post("/mlops/serving", headers=headers, json={"mode": "canary", "challenger_version": challenger, "canary_percent": 100}).raise_for_status()
        third = {**second, "event_id": prefix+"c", "event_time": now.isoformat(), "location_token": "loc_synthetic_third", "latitude": 12.972, "longitude": 77.594}
        canary_result = client.post("/events", headers=headers, json=third)
        canary_result.raise_for_status()
        assert canary_result.json()["prediction"]["model_version"] == challenger
        label = client.post(f"/predictions/{third['event_id']}/label", headers=headers, json={"label": 0, "source": "synthetic_acceptance_review"})
        label.raise_for_status()
        assert label.json()["status"] == "evaluated"
        duplicate = client.post(f"/predictions/{third['event_id']}/label", headers=headers, json={"label": 1})
        assert duplicate.status_code == 409
        client.post("/mlops/serving", headers=headers, json={"mode": "champion"}).raise_for_status()
        print(f"PASS scenario=impossible_travel shadow_champion={active} challenger={challenger} canary=100% delayed_label=received duplicate_label=409")
        print(f"PERSISTENCE event_id={third['event_id']} received_labels={label.json()['monitoring']['received_labels']} serving_mode=champion scenario_speed_kmh={scenario_config.json()['max_speed_kmh']}")


if __name__ == "__main__":
    main()
