"""Verify local acceptance records remain available after an API restart."""
import os

import httpx


def main():
    with httpx.Client(base_url=os.getenv("TG_ACCEPTANCE_API", "http://localhost:8000/api"), timeout=30) as client:
        response = client.post("/auth/login", json={"username": os.environ["TG_ADMIN_USERNAME"], "password": os.environ["TG_ADMIN_PASSWORD"]})
        response.raise_for_status()
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        state = client.get("/mlops", headers=headers)
        state.raise_for_status()
        payload = state.json()
        event_id = os.environ["TG_ACCEPTANCE_EVENT_ID"]
        events = client.get("/events?limit=500", headers=headers)
        events.raise_for_status()
        persisted = next((event for event in events.json() if event["event_id"] == event_id), None)
        assert persisted is not None
        assert persisted["prediction"]["policy_version"] == "risk-v2"
        assert payload["serving_config"]["mode"] == "champion"
        assert payload["scenario_config"]["max_speed_kmh"] == 800
        assert payload["label_monitoring"]["received_labels"] >= 1
        print("PASS after API restart: synthetic event, delayed label/model observations, scenario config and serving config persisted in PostgreSQL")


if __name__ == "__main__":
    main()
