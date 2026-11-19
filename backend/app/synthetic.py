"""Deterministic, chunkable synthetic telecom event generation."""

from datetime import datetime, timedelta, timezone
import random
from collections.abc import Iterator

from app.schemas import EventIn

GENERATOR_VERSION = "synthetic-v2"
MAX_GENERATED_EVENTS = 300_000
SCENARIOS = [
    "sim_swap",
    "call_burst",
    "sim_farm",
    "coordinated_ring",
    "impossible_travel",
    "wangiri",
    "benign",
    "legitimate_sim_change",
    "business_call_burst",
    "normal_travel",
]
FRAUD_SCENARIOS = {
    "sim_swap",
    "call_burst",
    "sim_farm",
    "coordinated_ring",
    "impossible_travel",
    "wangiri",
}


def _event(index: int, seed: int, rng: random.Random, event_prefix: str | None = None) -> EventIn:
    scenario = SCENARIOS[(index // 12) % len(SCENARIOS)]
    within = index % 12
    fraud = int(scenario in FRAUD_SCENARIOS)
    burst = scenario in {"call_burst", "wangiri", "business_call_burst"}

    if scenario == "sim_swap" and within < 2:
        event_type = "SIM_CHANGE" if within == 0 else "DEVICE_CHANGE"
    elif scenario == "sim_swap" and within == 2:
        event_type = "OTP_REQUEST"
    elif scenario == "sim_swap" and within == 3:
        event_type = "AUTHENTICATION"
    elif scenario == "sim_farm" and within < 3:
        event_type = "SIM_CHANGE"
    elif scenario == "coordinated_ring" and within < 4:
        event_type = "NETWORK_ACTIVITY"
    elif scenario in {"impossible_travel", "normal_travel"} and within < 4:
        event_type = "LOCATION"
    elif scenario in {"wangiri", "business_call_burst"}:
        event_type = "CALL"
    elif scenario == "legitimate_sim_change" and within < 2:
        event_type = "SIM_CHANGE" if within == 0 else "DEVICE_CHANGE"
    else:
        event_type = (
            "CALL"
            if burst or rng.random() < 0.58
            else rng.choice(
                ["CALL", "SMS", "SIM_CHANGE", "DEVICE_CHANGE", "NETWORK_ACTIVITY", "LOCATION"]
            )
        )

    subscriber = f"sub_{index // 3:06d}"
    device = (
        f"dev_ring_{index // 5:04d}"
        if scenario in {"sim_farm", "coordinated_ring"}
        else f"dev_{index // 3:06d}"
    )
    network = (
        f"net_ring_{index // 5:04d}"
        if scenario == "coordinated_ring"
        else f"net_{index // 3:06d}"
    )
    is_call = event_type == "CALL"
    duration = rng.randrange(1, 900) if is_call else None
    if scenario == "wangiri" and is_call:
        duration = rng.randrange(1, 8)
    if scenario == "business_call_burst" and is_call:
        duration = rng.randrange(90, 1800)

    coordinates = {}
    if event_type == "LOCATION" and scenario == "impossible_travel":
        coordinates = (
            {"latitude": 19.0760, "longitude": 72.8777}
            if within % 2 == 0
            else {"latitude": 28.6139, "longitude": 77.2090}
        )
    elif event_type == "LOCATION" and scenario == "normal_travel":
        coordinates = {
            "latitude": 19.0760 + within * 0.01,
            "longitude": 72.8777 + within * 0.01,
        }

    return EventIn(
        event_id=f"{event_prefix}_{index:06d}" if event_prefix else f"evt_{seed}_{index:06d}",
        event_type=event_type,
        event_time=datetime(2025, 1, 1, tzinfo=timezone.utc)
        + timedelta(minutes=index * 4 + rng.randrange(4)),
        subscriber_id=subscriber,
        source_token=f"src_{index // 2:06d}",
        destination_token=f"dst_{rng.randrange(2000):06d}",
        sim_id=f"sim_{index // 3:06d}",
        device_id=device,
        network_token=network,
        location_token=(
            f"region_{within % 8}"
            if scenario in {"impossible_travel", "normal_travel"}
            else f"region_{rng.randrange(8)}"
        ),
        duration_seconds=duration,
        call_direction=(rng.choice(["incoming", "outgoing"]) if is_call else None),
        call_status=(
            "missed" if scenario == "wangiri" else rng.choices(["answered", "missed", "failed"], [0.8, 0.15, 0.05])[0]
        )
        if is_call
        else None,
        is_international=(rng.random() < (0.35 if scenario == "wangiri" else 0.05))
        if is_call
        else None,
        is_roaming=(rng.random() < 0.08) if is_call else None,
        message_count=(rng.randrange(1, 5) if event_type == "SMS" else 1 if event_type == "OTP_REQUEST" else None),
        auth_outcome=("failed" if fraud and event_type == "AUTHENTICATION" else rng.choice(["success", "failed"]))
        if event_type in {"OTP_REQUEST", "AUTHENTICATION"}
        else None,
        **coordinates,
        scenario_label=scenario,
        fraud_label=fraud,
    )


def iter_event_batches(
    count: int = 300, seed: int = 42, batch_size: int = 2000,
    event_prefix: str | None = None,
) -> Iterator[list[EventIn]]:
    """Yield reproducible bounded batches; memory use is independent of total count."""
    if not 1 <= count <= MAX_GENERATED_EVENTS:
        raise ValueError(f"count must be between 1 and {MAX_GENERATED_EVENTS}")
    if not 1 <= batch_size <= 20_000:
        raise ValueError("batch_size must be between 1 and 20000")
    rng = random.Random(seed)
    batch: list[EventIn] = []
    for index in range(count):
        batch.append(_event(index, seed, rng, event_prefix))
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def generate_events(count: int = 300, seed: int = 42) -> list[EventIn]:
    """Compatibility wrapper for existing small scenario/API callers."""
    return [event for batch in iter_event_batches(count, seed, batch_size=min(count, 5000)) for event in batch]
