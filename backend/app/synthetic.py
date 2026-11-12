from datetime import datetime, timedelta, timezone
import random
from app.schemas import EventIn

SCENARIOS = [
    "sim_swap",
    "call_burst",
    "sim_farm",
    "coordinated_ring",
    "impossible_travel",
    "wangiri",
    "benign",
]


def generate_events(count: int = 300, seed: int = 42) -> list[EventIn]:
    if not 1 <= count <= 5000:
        raise ValueError("count must be between 1 and 5000")
    rng = random.Random(seed)
    # Fixed origin keeps a seed/configuration fully reproducible across runs.
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    events = []
    for i in range(count):
        scenario = SCENARIOS[(i // 12) % len(SCENARIOS)]
        within = i % 12
        fraud = int(scenario != "benign")
        burst = scenario in {"call_burst", "wangiri"}
        if scenario == "sim_swap" and within < 2:
            etype = "SIM_CHANGE" if within == 0 else "DEVICE_CHANGE"
        elif scenario == "sim_swap" and within == 2:
            etype = "ACCOUNT_ACTIVITY"
        elif scenario == "sim_farm" and within < 3:
            etype = "SIM_CHANGE"
        elif scenario == "coordinated_ring" and within < 4:
            etype = "NETWORK_ACTIVITY"
        elif scenario == "impossible_travel" and within < 4:
            etype = "LOCATION"
        elif scenario == "wangiri":
            etype = "CALL"
        else:
            etype = (
                "CALL"
                if burst or rng.random() < 0.58
                else rng.choice(
                    ["CALL", "SMS", "SIM_CHANGE", "DEVICE_CHANGE", "NETWORK_ACTIVITY", "LOCATION"]
                )
            )
        subscriber = f"sub_{i // 3:05d}"
        common_device = (
            f"dev_ring_{i // 5:03d}"
            if scenario in {"sim_farm", "coordinated_ring"}
            else f"dev_{i // 3:05d}"
        )
        common_net = (
            f"net_ring_{i // 5:03d}" if scenario == "coordinated_ring" else f"net_{i // 3:05d}"
        )
        events.append(
            EventIn(
                event_id=f"evt_{seed}_{i:06d}",
                event_type=etype,
                event_time=base + timedelta(minutes=i * 4 + rng.randrange(4)),
                subscriber_id=subscriber,
                source_token=f"src_{i // 2:05d}",
                destination_token=f"dst_{rng.randrange(1000):05d}",
                sim_id=f"sim_{i // 3:05d}",
                device_id=common_device,
                network_token=common_net,
                location_token=(
                    f"region_{within}"
                    if scenario == "impossible_travel"
                    else f"region_{rng.randrange(8)}"
                ),
                duration_seconds=rng.randrange(1, 900) if etype == "CALL" else None,
                scenario_label=scenario,
                fraud_label=fraud,
            )
        )
    return events
