"""Reproducible, seekable events and outcomes for a synthetic telecom population."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import sin, tau
from random import Random
import re

from app.schemas import EventIn

GENERATOR_VERSION = "synthetic-v3"
PHASES = ("reference", "shift", "adaptation", "recovery")
TRAIN_SCENARIOS = (
    "sim_swap", "call_burst", "sim_farm", "coordinated_ring", "impossible_travel", "wangiri",
)
HOLDOUT_SCENARIOS = (
    "delayed_takeover", "blended_burst", "distributed_sim_farm",
    "low_rate_ring", "roaming_impersonation", "mixed_callbacks",
)
PROFILES = ("commuter", "home", "business", "night", "traveler", "hybrid")
REGIONS = (
    (18.51, 73.85), (19.08, 72.88), (22.57, 88.36), (23.03, 72.58),
    (26.92, 75.79), (28.61, 77.21), (12.97, 77.59), (13.08, 80.27),
)
EVENT_TYPES = (
    "CALL", "SMS", "AUTHENTICATION", "OTP_REQUEST", "LOCATION",
    "NETWORK_ACTIVITY", "SIM_CHANGE", "DEVICE_CHANGE", "ACCOUNT_ACTIVITY",
)
NORMAL_WEIGHTS = (60, 13, 6, 3, 6, 7, 1, 1, 3)
FRAUD_WEIGHTS = {
    "sim_swap": (35, 10, 17, 10, 7, 6, 6, 4, 5),
    "call_burst": (80, 10, 2, 1, 2, 2, 1, 1, 1),
    "sim_farm": (62, 10, 6, 4, 3, 8, 2, 2, 3),
    "coordinated_ring": (60, 9, 5, 4, 5, 10, 2, 2, 3),
    "impossible_travel": (44, 9, 7, 4, 20, 8, 2, 2, 4),
    "wangiri": (83, 7, 2, 1, 2, 2, 1, 1, 1),
    "delayed_takeover": (47, 12, 14, 8, 6, 6, 2, 2, 3),
    "blended_burst": (76, 12, 3, 2, 2, 2, 1, 1, 1),
    "distributed_sim_farm": (60, 11, 7, 4, 3, 9, 2, 2, 2),
    "low_rate_ring": (63, 10, 5, 3, 6, 8, 1, 2, 2),
    "roaming_impersonation": (51, 10, 8, 6, 13, 7, 1, 1, 3),
    "mixed_callbacks": (74, 9, 4, 2, 3, 4, 1, 1, 2),
}
CAMPAIGN_EVENTS = 32
CAMPAIGN_PARTICIPATION = 0.4
DEFAULT_START = datetime(2025, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class TelecomConfig:
    seed: int
    namespace: str
    population: int = 2_000
    start: datetime = DEFAULT_START
    interval_seconds: int = 30
    prevalence: float = 0.02
    role: str = "live"

    def __post_init__(self):
        if not 0 <= self.seed <= 2**32 - 1:
            raise ValueError("seed must fit in an unsigned 32-bit integer")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", self.namespace):
            raise ValueError("namespace must contain 1–64 letters, digits, underscores or hyphens")
        if not 24 <= self.population <= 100_000:
            raise ValueError("virtual population must be between 24 and 100,000")
        if self.start.utcoffset() is None:
            raise ValueError("start must include a timezone offset")
        if not 1 <= self.interval_seconds <= 3_600:
            raise ValueError("interval must be between one second and one hour")
        if not 0.0 <= self.prevalence <= 0.20:
            raise ValueError("experimental fraud prevalence must be between 0 and 0.20")
        if self.role not in {"development", "independent", "drift", "live"}:
            raise ValueError("unsupported generation role")


@dataclass(frozen=True)
class SyntheticOutcome:
    event_id: str
    label: int
    scenario: str
    episode_id: str | None
    available_at: datetime
    phase: str


@dataclass(frozen=True)
class GeneratedRecord:
    event: EventIn
    outcome: SyntheticOutcome


@dataclass(frozen=True)
class SubscriberProfile:
    kind: str
    home: int
    contact_group: int
    activity: float
    call_duration: float


class TelecomGenerator:
    """A seekable generator with separate profile, event, campaign and outcome streams.

    State can be checkpointed as the next index plus the immutable configuration. A run
    may change phase on a previously unissued index. Replaying an issued index requires
    the original phase configuration.
    """

    def __init__(self, config: TelecomConfig):
        self.config = config
        self._prefix = f"{GENERATOR_VERSION}:{config.seed}:{config.namespace}".encode()
        self._profiles = tuple(self._profile(index) for index in range(config.population))

    def _rng(self, stream: str, index: int) -> Random:
        return Random(self._prefix + f":{stream}:{index}".encode())

    def _token(self, kind: str, key: str | int) -> str:
        value = sha256(self._prefix + f":{kind}:{key}".encode()).hexdigest()[:24]
        return f"{kind}_{value}"

    def _profile(self, index: int) -> SubscriberProfile:
        rng = self._rng("profiles", index)
        kind = rng.choices(PROFILES, weights=(28, 22, 20, 9, 11, 10))[0]
        if kind == "hybrid" and self.config.role == "development":
            kind = "commuter"
        return SubscriberProfile(
            kind, rng.randrange(len(REGIONS)), rng.randrange(max(8, self.config.population // 12)),
            rng.uniform(0.45, 1.0), rng.uniform(45.0, 280.0),
        )

    def _normal_subscriber(self, rng: Random, time: datetime) -> int:
        for _ in range(8):
            subscriber = rng.randrange(self.config.population)
            profile = self._profiles[subscriber]
            active_hour = time.hour < 7 if profile.kind == "night" else 7 <= time.hour <= 22
            weekend_business = time.weekday() >= 5 and profile.kind == "business"
            seasonal = 0.8 + 0.2 * sin(tau * time.timetuple().tm_yday / 365)
            activity = profile.activity * (1.0 if active_hour else 0.28) * seasonal
            if weekend_business:
                activity *= 0.6
            if rng.random() < activity:
                return subscriber
        return subscriber

    def _campaign(self, index: int, phase: str):
        block = index // CAMPAIGN_EVENTS
        rng = self._rng("campaign", block)
        prevalence_multiplier = {"reference": 1, "shift": 1.7, "adaptation": 1.7, "recovery": 1.1}
        probability = self.config.prevalence * prevalence_multiplier[phase] / CAMPAIGN_PARTICIPATION
        if rng.random() >= probability:
            return None
        holdout = self.config.role == "independent" or (
            self.config.role in {"drift", "live"} and phase != "reference"
        )
        scenario = rng.choice(HOLDOUT_SCENARIOS if holdout else TRAIN_SCENARIOS)
        # The virtual episode can span several synthetic subscribers sharing context.
        subscribers = rng.sample(range(self.config.population), k=rng.randint(2, 6))
        return block, scenario, subscribers

    def record(self, index: int, phase: str = "reference") -> GeneratedRecord:
        if index < 0:
            raise ValueError("event index must be non-negative")
        if phase not in PHASES:
            raise ValueError("unsupported simulation phase")
        schedule = self._rng("schedule", index)
        time = self.config.start.astimezone(timezone.utc) + timedelta(
            seconds=index * self.config.interval_seconds
            + schedule.randrange(self.config.interval_seconds),
        )
        rng = self._rng("event", index)
        campaign = self._campaign(index, phase)
        is_fraud = campaign is not None and rng.random() < CAMPAIGN_PARTICIPATION
        if campaign and (is_fraud or rng.random() < 0.14):
            subscriber = rng.choice(campaign[2])
        else:
            subscriber = self._normal_subscriber(rng, time)
        profile = self._profiles[subscriber]
        scenario = campaign[1] if is_fraud else self._benign_scenario(rng, profile)
        event_type = self._event_type(rng, scenario)
        values = self._event_values(rng, subscriber, profile, scenario, event_type, time, campaign, phase)
        event = EventIn(
            event_id=self._token("evt", index),
            event_type=event_type,
            event_time=time,
            subscriber_id=self._token("sub", subscriber),
            **values,
        )
        delays = self._rng("outcome", index)
        available = time + timedelta(seconds=delays.randint(2, 48) * 900)
        return GeneratedRecord(
            event,
            SyntheticOutcome(
                event.event_id, int(is_fraud), scenario,
                self._token("ep", campaign[0]) if is_fraud else None, available, phase,
            ),
        )

    @staticmethod
    def _benign_scenario(rng: Random, profile: SubscriberProfile) -> str:
        if rng.random() < 0.13:
            return rng.choice(("legitimate_sim_change", "business_call_burst", "normal_travel"))
        if profile.kind == "business" and rng.random() < 0.18:
            return "business_call_burst"
        return "benign"

    @staticmethod
    def _event_type(rng: Random, scenario: str) -> str:
        weights = FRAUD_WEIGHTS.get(scenario, NORMAL_WEIGHTS)
        if scenario == "legitimate_sim_change":
            weights = (48, 10, 8, 5, 5, 7, 8, 5, 4)
        elif scenario == "business_call_burst":
            weights = (77, 9, 3, 2, 3, 2, 1, 1, 2)
        elif scenario == "normal_travel":
            weights = (53, 10, 5, 3, 18, 7, 1, 1, 2)
        return rng.choices(EVENT_TYPES, weights=weights)[0]

    def _event_values(self, rng, subscriber, profile, scenario, kind, time, campaign, phase):
        day = (time.date() - DEFAULT_START.date()).days
        region = profile.home
        travel_cases = {"normal_travel", "impossible_travel", "roaming_impersonation"}
        travel = scenario in travel_cases or (profile.kind == "traveler" and rng.random() < 0.24)
        if travel and rng.random() < (0.80 if phase in {"shift", "adaptation"} else 0.55):
            region = rng.randrange(len(REGIONS))
        # Local shared networks and existing contacts are common among benign profiles too.
        network = f"{region}:{rng.randrange(10)}" if rng.random() < 0.75 else f"home:{subscriber}"
        if campaign and rng.random() < 0.25:
            network = f"shared:{campaign[0] % 53}"
        device = f"{subscriber}:{(day + subscriber) // 37}"
        sim = f"{subscriber}:{(day + subscriber) // 71}"
        values = {
            "source_token": self._token("src", subscriber),
            "destination_token": self._token("dst", f"{profile.contact_group}:{rng.randrange(18)}"),
            "sim_id": self._token("sim", sim),
            "device_id": self._token("dev", device),
            "network_token": self._token("net", network),
            "location_token": self._token("loc", region),
        }
        if rng.random() < (0.08 if phase in {"shift", "adaptation"} else 0.03):
            values[rng.choice(("destination_token", "device_id", "location_token"))] = None
        if kind == "LOCATION" and rng.random() < 0.85:
            lat, lon = REGIONS[region]
            values.update(latitude=lat + rng.uniform(-0.06, 0.06), longitude=lon + rng.uniform(-0.06, 0.06))
        if kind == "CALL":
            short_call = scenario in {"wangiri", "mixed_callbacks", "call_burst", "blended_burst"}
            duration = rng.lognormvariate(0.0, 0.82) * profile.call_duration
            if short_call and rng.random() < 0.56:
                duration *= 0.20
            if phase in {"shift", "adaptation"}:
                duration *= 1.21
            values.update(
                duration_seconds=int(min(duration, 7_200)),
                call_direction=rng.choice(("incoming", "outgoing")),
                call_status=rng.choices(
                    ("answered", "missed", "failed"), (60, 30, 10) if short_call else (81, 14, 5)
                )[0],
                is_international=rng.random() < (0.22 if travel or short_call else 0.065),
                is_roaming=rng.random() < (0.43 if travel else 0.06),
            )
        elif kind in {"SMS", "OTP_REQUEST"}:
            values["message_count"] = rng.randint(1, 4) if kind == "SMS" else 1
        if kind in {"AUTHENTICATION", "OTP_REQUEST"}:
            takeover = scenario in {"sim_swap", "delayed_takeover"}
            values["auth_outcome"] = "failed" if rng.random() < (0.36 if takeover else 0.14) else "success"
        return values
